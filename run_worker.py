from __future__ import annotations

import argparse
import asyncio
import logging
import socket

from worker.client import WorkerClient


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run worker client")
    parser.add_argument("--uuid", default="Worker_1", help="Worker UUID")
    parser.add_argument("--master-host", default="127.0.0.1", help="Master host")
    parser.add_argument("--master-port", type=int, default=9000, help="Master port")
    parser.add_argument("--interval", type=float, default=10.0, help="Heartbeat interval in seconds")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )
    return parser.parse_args()


async def _main() -> None:
    args = parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s | %(message)s",
    )
    logging.getLogger("worker.bootstrap").info(
        "[BOOT] Worker inicializando | maquina=%s uuid=%s master=%s:%s",
        socket.gethostname(),
        args.uuid,
        args.master_host,
        args.master_port,
    )
    worker = WorkerClient(
        server_uuid=args.uuid,
        master_host=args.master_host,
        master_port=args.master_port,
        heartbeat_interval_seconds=args.interval,
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(_main())
