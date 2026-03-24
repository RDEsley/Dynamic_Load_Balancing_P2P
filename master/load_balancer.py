"""Dynamic load balancing orchestrator for Master nodes."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Tuple

from master.p2p_client import P2PClient
from master.server import MasterServer

LOGGER = logging.getLogger("master.load_balancer")


@dataclass(frozen=True)
class PeerMaster:
    server_uuid: str
    host: str
    port: int


class DynamicLoadBalancer:
    """
    Coordinates borrow/return negotiation with peer masters.

    Saturation policy:
    - If pending requests > saturation_threshold, attempt to borrow workers.
    - Borrow from the first peer that accepts.
    """

    def __init__(
        self,
        master_server: MasterServer,
        p2p_client: P2PClient,
        peers: List[PeerMaster],
        saturation_threshold: int = 10,
    ) -> None:
        self.master_server = master_server
        self.p2p_client = p2p_client
        self.peers = peers
        self.saturation_threshold = saturation_threshold
        self.active_leases: List[Tuple[PeerMaster, str, int]] = []

    async def rebalance_if_saturated(self, requested_count: int = 1) -> bool:
        if self.master_server.state.pending_requests <= self.saturation_threshold:
            return False

        for peer in self.peers:
            try:
                response = await self.p2p_client.request_borrow_workers(
                    peer.host,
                    peer.port,
                    count=requested_count,
                    lease_seconds=120,
                )
            except OSError as exc:
                LOGGER.warning("Failed to contact peer %s: %s", peer.server_uuid, exc)
                continue

            if response.get("RESPONSE") == "ACCEPTED":
                lease_id = str(response["LEASE_ID"])
                count = int(response.get("COUNT", requested_count))
                self.active_leases.append((peer, lease_id, count))
                self.master_server.state.borrowed_workers += count
                LOGGER.info(
                    "Borrowed %s worker(s) from %s with lease %s",
                    count,
                    peer.server_uuid,
                    lease_id,
                )
                return True

        LOGGER.info("No peer accepted borrow request")
        return False

    async def return_all_leases(self) -> None:
        for peer, lease_id, count in list(self.active_leases):
            response = await self.p2p_client.return_workers(peer.host, peer.port, lease_id=lease_id, count=count)
            if response.get("RESPONSE") == "OK":
                self.master_server.state.borrowed_workers = max(
                    self.master_server.state.borrowed_workers - count,
                    0,
                )
                self.active_leases.remove((peer, lease_id, count))
                LOGGER.info("Returned lease %s to %s", lease_id, peer.server_uuid)
