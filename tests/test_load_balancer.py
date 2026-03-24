from __future__ import annotations

import unittest

from master.load_balancer import DynamicLoadBalancer, PeerMaster
from master.p2p_client import P2PClient
from master.server import MasterServer


class LoadBalancerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.borrower_master = MasterServer("Master_A", "127.0.0.1", 0, total_workers=2)
        self.lender_master = MasterServer("Master_B", "127.0.0.1", 0, total_workers=2)
        await self.borrower_master.start()
        await self.lender_master.start()

    async def asyncTearDown(self) -> None:
        await self.borrower_master.stop()
        await self.lender_master.stop()

    async def test_rebalance_and_return_leases(self) -> None:
        client = P2PClient(server_uuid="Master_A")
        balancer = DynamicLoadBalancer(
            master_server=self.borrower_master,
            p2p_client=client,
            peers=[PeerMaster("Master_B", "127.0.0.1", self.lender_master.port)],
            saturation_threshold=3,
        )

        self.borrower_master.state.pending_requests = 5
        borrowed = await balancer.rebalance_if_saturated(requested_count=1)
        self.assertTrue(borrowed)
        self.assertEqual(self.borrower_master.state.borrowed_workers, 1)
        self.assertEqual(len(balancer.active_leases), 1)

        await balancer.return_all_leases()
        self.assertEqual(self.borrower_master.state.borrowed_workers, 0)
        self.assertEqual(len(balancer.active_leases), 0)


if __name__ == "__main__":
    unittest.main()
