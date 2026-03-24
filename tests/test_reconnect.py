from __future__ import annotations

import asyncio
import unittest

from master.server import MasterServer
from tests.util import get_free_port
from worker.client import WorkerClient


class ReconnectTests(unittest.IsolatedAsyncioTestCase):
    async def test_worker_reconnects_after_master_is_available(self) -> None:
        # Pick a fixed test port. The worker starts before master to force OFFLINE state first.
        port = get_free_port()
        worker = WorkerClient(
            server_uuid="Worker_reconnect",
            master_host="127.0.0.1",
            master_port=port,
            heartbeat_interval_seconds=0.02,
            connect_timeout_seconds=0.1,
            reconnect_initial_delay_seconds=0.05,
            reconnect_max_delay_seconds=0.05,
        )

        with self.assertLogs("worker", level="INFO") as logs:
            task = asyncio.create_task(worker.run_cycles(4))
            await asyncio.sleep(0.08)

            master = MasterServer("Master_reconnect", "127.0.0.1", port, total_workers=2)
            await master.start()
            try:
                await task
            finally:
                await master.stop()

        full_log = "\n".join(logs.output)
        self.assertIn("OFFLINE - Tentando Reconectar", full_log)
        self.assertIn("Status: ALIVE", full_log)


if __name__ == "__main__":
    unittest.main()
