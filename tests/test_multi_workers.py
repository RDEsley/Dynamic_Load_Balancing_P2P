from __future__ import annotations

import asyncio
import unittest

from master.server import MasterServer
from worker.client import WorkerClient


class MultiWorkerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.master = MasterServer("Master_multi", "127.0.0.1", 0, total_workers=5)
        await self.master.start()

    async def asyncTearDown(self) -> None:
        await self.master.stop()

    async def test_master_handles_multiple_workers_concurrently(self) -> None:
        workers = [
            WorkerClient(
                server_uuid=f"Worker_{idx}",
                master_host="127.0.0.1",
                master_port=self.master.port,
                heartbeat_interval_seconds=0.01,
                connect_timeout_seconds=1.0,
            )
            for idx in range(8)
        ]

        responses = await asyncio.gather(*(worker.send_heartbeat_once() for worker in workers))
        self.assertEqual(len(responses), 8)
        self.assertTrue(all(response.get("RESPONSE") == "ALIVE" for response in responses))


if __name__ == "__main__":
    unittest.main()
