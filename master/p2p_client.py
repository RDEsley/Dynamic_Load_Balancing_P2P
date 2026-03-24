"""Master-to-Master protocol client helpers."""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any, Dict

from protocol.constants import (
    TASK_BORROW_WORKER_REQUEST,
    TASK_LOAD_STATUS_REQUEST,
    TASK_RETURN_WORKER_REQUEST,
)
from protocol.framing import read_json_line, write_json_line

LOGGER = logging.getLogger("master.p2p_client")


class P2PClient:
    def __init__(self, server_uuid: str, timeout_seconds: float = 5.0):
        self.server_uuid = server_uuid
        self.timeout_seconds = timeout_seconds

    async def request_load_status(self, host: str, port: int) -> Dict[str, Any]:
        payload = {
            "SERVER_UUID": self.server_uuid,
            "TASK": TASK_LOAD_STATUS_REQUEST,
            "REQUEST_ID": str(uuid.uuid4()),
        }
        return await self._send_and_receive(host, port, payload)

    async def request_borrow_workers(
        self,
        host: str,
        port: int,
        count: int,
        lease_seconds: int = 120,
    ) -> Dict[str, Any]:
        payload = {
            "SERVER_UUID": self.server_uuid,
            "TASK": TASK_BORROW_WORKER_REQUEST,
            "REQUEST_ID": str(uuid.uuid4()),
            "COUNT": count,
            "LEASE_SECONDS": lease_seconds,
        }
        return await self._send_and_receive(host, port, payload)

    async def return_workers(self, host: str, port: int, lease_id: str, count: int) -> Dict[str, Any]:
        payload = {
            "SERVER_UUID": self.server_uuid,
            "TASK": TASK_RETURN_WORKER_REQUEST,
            "REQUEST_ID": str(uuid.uuid4()),
            "LEASE_ID": lease_id,
            "COUNT": count,
        }
        return await self._send_and_receive(host, port, payload)

    async def _send_and_receive(self, host: str, port: int, payload: Dict[str, Any]) -> Dict[str, Any]:
        LOGGER.info(
            "[P2P-ENVIO] Master=%s -> %s:%s | task=%s request_id=%s",
            self.server_uuid,
            host,
            port,
            payload.get("TASK", "unknown"),
            payload.get("REQUEST_ID", "-"),
        )
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=self.timeout_seconds,
        )
        try:
            await asyncio.wait_for(write_json_line(writer, payload), timeout=self.timeout_seconds)
            response = await asyncio.wait_for(read_json_line(reader), timeout=self.timeout_seconds)
            LOGGER.info(
                "[P2P-RESPOSTA] Master=%s <- %s:%s | task=%s response=%s request_id=%s",
                self.server_uuid,
                host,
                port,
                response.get("TASK", "unknown"),
                response.get("RESPONSE", "-"),
                response.get("REQUEST_ID", "-"),
            )
            return response
        finally:
            writer.close()
            await writer.wait_closed()
