"""Master server implementation with heartbeat and P2P negotiation handlers."""

from __future__ import annotations

import asyncio
import json
import logging
import socket
import uuid
from dataclasses import dataclass
from typing import Any, Dict

from protocol.constants import (
    ERROR_INSUFFICIENT_WORKERS,
    ERROR_INVALID_JSON,
    ERROR_INVALID_PAYLOAD,
    ERROR_LEASE_NOT_FOUND,
    ERROR_UNKNOWN_TASK,
    RESPONSE_ACCEPTED,
    RESPONSE_OK,
    RESPONSE_REJECTED,
    TASK_BORROW_WORKER_REQUEST,
    TASK_BORROW_WORKER_RESPONSE,
    TASK_HEARTBEAT,
    TASK_LOAD_STATUS_REQUEST,
    TASK_LOAD_STATUS_RESPONSE,
    TASK_RETURN_WORKER_REQUEST,
    TASK_RETURN_WORKER_RESPONSE,
)
from protocol.framing import read_json_line, write_json_line
from protocol.messages import (
    build_error_response,
    build_heartbeat_response,
    ensure_request_id,
    validate_base_message,
    validate_heartbeat_request,
)

LOGGER = logging.getLogger("master")


@dataclass
class MasterState:
    total_workers: int = 3
    borrowed_workers: int = 0
    pending_requests: int = 0
    lent_workers: int = 0

    @property
    def available_workers(self) -> int:
        return max(self.total_workers - self.lent_workers, 0)


class MasterServer:
    def __init__(self, server_uuid: str, host: str, port: int, total_workers: int = 3):
        self.server_uuid = server_uuid
        self.machine_name = socket.gethostname()
        self.host = host
        self.port = port
        self.state = MasterState(total_workers=total_workers)
        self._server: asyncio.AbstractServer | None = None
        self._lock = asyncio.Lock()
        self._leases: Dict[str, int] = {}

    async def start(self) -> None:
        self._server = await asyncio.start_server(self._handle_client, self.host, self.port)
        if self.port == 0 and self._server.sockets:
            self.port = int(self._server.sockets[0].getsockname()[1])
        LOGGER.info(
            "[MASTER %s@%s] Ativo em %s:%s | capacidade_workers=%s",
            self.server_uuid,
            self.machine_name,
            self.host,
            self.port,
            self.state.total_workers,
        )

    async def stop(self) -> None:
        if self._server is None:
            return
        self._server.close()
        await self._server.wait_closed()
        self._server = None
        LOGGER.info("[MASTER %s@%s] Encerrado.", self.server_uuid, self.machine_name)

    async def serve_forever(self) -> None:
        if self._server is None:
            await self.start()
        assert self._server is not None
        async with self._server:
            await self._server.serve_forever()

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        peer = writer.get_extra_info("peername")
        LOGGER.info("[CONEXAO] Worker conectado em %s -> Master=%s", peer, self.server_uuid)
        try:
            while True:
                try:
                    payload = await read_json_line(reader)
                except json.JSONDecodeError:  # type: ignore[name-defined]
                    LOGGER.warning("Invalid JSON received | master=%s peer=%s", self.server_uuid, peer)
                    await write_json_line(
                        writer,
                        build_error_response(
                            self.server_uuid,
                            ERROR_INVALID_JSON,
                            "Invalid JSON payload",
                        ),
                    )
                    continue
                except ConnectionError:
                    LOGGER.info("[CONEXAO] Worker desconectou %s -> Master=%s", peer, self.server_uuid)
                    break
                except ValueError as exc:
                    LOGGER.warning(
                        "Invalid payload framing | master=%s peer=%s reason=%s",
                        self.server_uuid,
                        peer,
                        exc,
                    )
                    await write_json_line(
                        writer,
                        build_error_response(self.server_uuid, ERROR_INVALID_PAYLOAD, str(exc)),
                    )
                    continue

                LOGGER.info(
                    "[MENSAGEM de %s] origem=%s task=%s request_id=%s",
                    peer,
                    payload.get("SERVER_UUID", "unknown"),
                    payload.get("TASK", "unknown"),
                    payload.get("REQUEST_ID", "-"),
                )
                response = await self._dispatch(payload)
                await write_json_line(writer, response)
                LOGGER.info(
                    "[RESPOSTA] Master=%s -> destino=%s task=%s response=%s request_id=%s",
                    self.server_uuid,
                    payload.get("SERVER_UUID", "unknown"),
                    response.get("TASK", "unknown"),
                    response.get("RESPONSE", "-"),
                    response.get("REQUEST_ID", "-"),
                )
        finally:
            writer.close()
            await writer.wait_closed()
            LOGGER.info("[CONEXAO] Encerrada com %s", peer)

    async def _dispatch(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        ok, error = validate_base_message(payload)
        if not ok:
            return build_error_response(self.server_uuid, ERROR_INVALID_PAYLOAD, error or "Invalid payload")

        task = payload.get("TASK")
        if task == TASK_HEARTBEAT:
            return self._handle_heartbeat(payload)
        if task == TASK_LOAD_STATUS_REQUEST:
            return self._handle_load_status(payload)
        if task == TASK_BORROW_WORKER_REQUEST:
            return await self._handle_borrow_request(payload)
        if task == TASK_RETURN_WORKER_REQUEST:
            return await self._handle_return_request(payload)
        return build_error_response(
            self.server_uuid,
            ERROR_UNKNOWN_TASK,
            f"Unsupported task: {task}",
            request_id=payload.get("REQUEST_ID"),
        )

    def _handle_heartbeat(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        ok, error = validate_heartbeat_request(payload)
        if not ok:
            return build_error_response(self.server_uuid, ERROR_INVALID_PAYLOAD, error or "Invalid heartbeat")
        LOGGER.info(
            "[HEARTBEAT] Master=%s recebeu de Worker=%s e respondeu ALIVE",
            self.server_uuid,
            payload.get("SERVER_UUID", "unknown"),
        )
        return build_heartbeat_response(self.server_uuid, request_id=payload.get("REQUEST_ID"))

    def _handle_load_status(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        request_id = ensure_request_id(payload)
        return {
            "SERVER_UUID": self.server_uuid,
            "TASK": TASK_LOAD_STATUS_RESPONSE,
            "REQUEST_ID": request_id,
            "RESPONSE": RESPONSE_OK,
            "AVAILABLE_WORKERS": self.state.available_workers,
            "BORROWED_WORKERS": self.state.borrowed_workers,
            "PENDING_REQUESTS": self.state.pending_requests,
        }

    async def _handle_borrow_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        request_id = ensure_request_id(payload)
        requested_count = int(payload.get("COUNT", 1))
        lease_seconds = int(payload.get("LEASE_SECONDS", 60))
        requester = payload.get("SERVER_UUID", "unknown")

        async with self._lock:
            if requested_count <= 0:
                return build_error_response(
                    self.server_uuid,
                    ERROR_INVALID_PAYLOAD,
                    "COUNT must be >= 1",
                    request_id=request_id,
                )

            if self.state.available_workers < requested_count:
                LOGGER.info(
                    "[P2P] Emprestimo NEGADO | lender=%s requester=%s solicitado=%s disponivel=%s",
                    self.server_uuid,
                    requester,
                    requested_count,
                    self.state.available_workers,
                )
                return {
                    "SERVER_UUID": self.server_uuid,
                    "TASK": TASK_BORROW_WORKER_RESPONSE,
                    "REQUEST_ID": request_id,
                    "RESPONSE": RESPONSE_REJECTED,
                    "ERROR_CODE": ERROR_INSUFFICIENT_WORKERS,
                    "ERROR_MESSAGE": "No spare workers available",
                }

            lease_id = f"lease-{uuid.uuid4()}"
            self._leases[lease_id] = requested_count
            self.state.lent_workers += requested_count
            LOGGER.info(
                "[P2P] Emprestimo ACEITO | lender=%s requester=%s lease_id=%s count=%s lease_seconds=%s disponivel_apos=%s",
                self.server_uuid,
                requester,
                lease_id,
                requested_count,
                lease_seconds,
                self.state.available_workers,
            )

            return {
                "SERVER_UUID": self.server_uuid,
                "TASK": TASK_BORROW_WORKER_RESPONSE,
                "REQUEST_ID": request_id,
                "RESPONSE": RESPONSE_ACCEPTED,
                "LEASE_ID": lease_id,
                "COUNT": requested_count,
                "LEASE_SECONDS": lease_seconds,
            }

    async def _handle_return_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        request_id = ensure_request_id(payload)
        lease_id = payload.get("LEASE_ID")
        if not lease_id:
            return build_error_response(
                self.server_uuid,
                ERROR_INVALID_PAYLOAD,
                "Missing LEASE_ID",
                request_id=request_id,
            )

        async with self._lock:
            count = self._leases.pop(lease_id, None)
            if count is None:
                return build_error_response(
                    self.server_uuid,
                    ERROR_LEASE_NOT_FOUND,
                    "Unknown LEASE_ID",
                    request_id=request_id,
                )

            self.state.lent_workers = max(self.state.lent_workers - count, 0)
            LOGGER.info(
                "[P2P] Lease devolvida | lender=%s requester=%s lease_id=%s count=%s disponivel_apos=%s",
                self.server_uuid,
                payload.get("SERVER_UUID", "unknown"),
                lease_id,
                count,
                self.state.available_workers,
            )
            return {
                "SERVER_UUID": self.server_uuid,
                "TASK": TASK_RETURN_WORKER_RESPONSE,
                "REQUEST_ID": request_id,
                "RESPONSE": RESPONSE_OK,
                "LEASE_ID": lease_id,
                "COUNT": count,
            }
