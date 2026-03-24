"""Worker client that sends periodic heartbeat messages."""

from __future__ import annotations

import asyncio
import logging
import socket
from typing import Any, Dict

from protocol.constants import RESPONSE_ALIVE
from protocol.framing import read_json_line, write_json_line
from protocol.messages import build_heartbeat_request

LOGGER = logging.getLogger("worker")


class WorkerClient:
    def __init__(
        self,
        server_uuid: str,
        master_host: str,
        master_port: int,
        heartbeat_interval_seconds: float = 10.0,
        connect_timeout_seconds: float = 5.0,
        reconnect_initial_delay_seconds: float = 1.0,
        reconnect_max_delay_seconds: float = 10.0,
    ) -> None:
        self.server_uuid = server_uuid
        self.machine_name = socket.gethostname()
        self.master_host = master_host
        self.master_port = master_port
        self.heartbeat_interval_seconds = heartbeat_interval_seconds
        self.connect_timeout_seconds = connect_timeout_seconds
        self.reconnect_initial_delay_seconds = reconnect_initial_delay_seconds
        self.reconnect_max_delay_seconds = reconnect_max_delay_seconds

    async def run(self) -> None:
        LOGGER.info(
            "[WORKER %s@%s] Iniciado. Destino Master=%s:%s | Heartbeat a cada %.1fs",
            self.server_uuid,
            self.machine_name,
            self.master_host,
            self.master_port,
            self.heartbeat_interval_seconds,
        )
        backoff_seconds = self.reconnect_initial_delay_seconds
        while True:
            backoff_seconds = await self._run_single_cycle(backoff_seconds)

    async def run_cycles(self, cycles: int) -> None:
        backoff_seconds = self.reconnect_initial_delay_seconds
        for _ in range(cycles):
            backoff_seconds = await self._run_single_cycle(backoff_seconds)

    async def _run_single_cycle(self, backoff_seconds: float) -> float:
        try:
            LOGGER.info(
                "[WORKER %s] Heartbeat enviado para %s:%s ...",
                self.server_uuid,
                self.master_host,
                self.master_port,
            )
            await self.send_heartbeat_once()
            await asyncio.sleep(self.heartbeat_interval_seconds)
            return self.reconnect_initial_delay_seconds
        except (ConnectionError, TimeoutError, asyncio.TimeoutError, OSError):
            LOGGER.warning(
                "[STATUS] OFFLINE - Tentando Reconectar | worker=%s | proxima tentativa em %.1fs",
                self.server_uuid,
                backoff_seconds,
            )
            await asyncio.sleep(backoff_seconds)
            return min(backoff_seconds * 2, self.reconnect_max_delay_seconds)

    async def send_heartbeat_once(self) -> Dict[str, Any]:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(self.master_host, self.master_port),
            timeout=self.connect_timeout_seconds,
        )
        try:
            payload = build_heartbeat_request(self.server_uuid)
            await asyncio.wait_for(write_json_line(writer, payload), timeout=self.connect_timeout_seconds)
            response = await asyncio.wait_for(read_json_line(reader), timeout=self.connect_timeout_seconds)
            if response.get("RESPONSE") == RESPONSE_ALIVE:
                LOGGER.info(
                    "[STATUS] ALIVE | Status: ALIVE | worker=%s | confirmado_por=%s | maquina=%s",
                    self.server_uuid,
                    response.get("SERVER_UUID", "unknown"),
                    self.machine_name,
                )
            else:
                LOGGER.warning("[STATUS] RESPOSTA_DESCONHECIDA | worker=%s | payload=%s", self.server_uuid, response)
            return response
        finally:
            writer.close()
            await writer.wait_closed()
