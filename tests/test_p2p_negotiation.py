from __future__ import annotations

import unittest

from master.p2p_client import P2PClient
from master.server import MasterServer


class P2PNegotiationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.lender = MasterServer("Master_B", "127.0.0.1", 0, total_workers=2)
        await self.lender.start()
        self.borrower_client = P2PClient(server_uuid="Master_A")

    async def asyncTearDown(self) -> None:
        await self.lender.stop()

    async def test_borrow_and_return_workers(self) -> None:
        status = await self.borrower_client.request_load_status("127.0.0.1", self.lender.port)
        self.assertEqual(status["RESPONSE"], "OK")
        self.assertEqual(status["AVAILABLE_WORKERS"], 2)

        borrow = await self.borrower_client.request_borrow_workers(
            "127.0.0.1",
            self.lender.port,
            count=1,
            lease_seconds=60,
        )
        self.assertEqual(borrow["RESPONSE"], "ACCEPTED")
        lease_id = borrow["LEASE_ID"]

        status_after_borrow = await self.borrower_client.request_load_status("127.0.0.1", self.lender.port)
        self.assertEqual(status_after_borrow["AVAILABLE_WORKERS"], 1)

        returned = await self.borrower_client.return_workers("127.0.0.1", self.lender.port, lease_id, count=1)
        self.assertEqual(returned["RESPONSE"], "OK")

        status_after_return = await self.borrower_client.request_load_status("127.0.0.1", self.lender.port)
        self.assertEqual(status_after_return["AVAILABLE_WORKERS"], 2)

    async def test_reject_when_insufficient_workers(self) -> None:
        borrow = await self.borrower_client.request_borrow_workers(
            "127.0.0.1",
            self.lender.port,
            count=3,
            lease_seconds=60,
        )
        self.assertEqual(borrow["RESPONSE"], "REJECTED")
        self.assertEqual(borrow["ERROR_CODE"], "INSUFFICIENT_WORKERS")


if __name__ == "__main__":
    unittest.main()
