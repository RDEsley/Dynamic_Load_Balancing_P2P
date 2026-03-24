from __future__ import annotations

import unittest

from master.server import MasterServer
from worker.client import WorkerClient


class HeartbeatIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.master = MasterServer("Master_A", "127.0.0.1", 0, total_workers=3)
        await self.master.start()

    async def asyncTearDown(self) -> None:
        await self.master.stop()

    async def test_worker_receives_alive(self) -> None:
        worker = WorkerClient(
            server_uuid="Worker_1",
            master_host="127.0.0.1",
            master_port=self.master.port,
            heartbeat_interval_seconds=0.01,
            connect_timeout_seconds=1.0,
        )

        response = await worker.send_heartbeat_once()

        self.assertEqual(response["TASK"], "HEARTBEAT")
        self.assertEqual(response["RESPONSE"], "ALIVE")


if __name__ == "__main__":
    unittest.main()
