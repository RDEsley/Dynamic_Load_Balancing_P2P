from __future__ import annotations

import argparse
import asyncio
import logging
import socket

from master.server import MasterServer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run master server")
    parser.add_argument("--uuid", default="Master_A", help="Master server UUID")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host")
    parser.add_argument("--port", type=int, default=9000, help="Bind port")
    parser.add_argument("--workers", type=int, default=3, help="Initial worker capacity")
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
    logging.getLogger("master.bootstrap").info(
        "[BOOT] Master inicializando | maquina=%s uuid=%s bind=%s:%s",
        socket.gethostname(),
        args.uuid,
        args.host,
        args.port,
    )
    server = MasterServer(args.uuid, args.host, args.port, total_workers=args.workers)
    await server.start()
    await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(_main())
