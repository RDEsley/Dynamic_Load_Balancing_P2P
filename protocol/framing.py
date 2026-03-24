"""JSON line framing helpers for TCP streams."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict


async def read_json_line(reader: asyncio.StreamReader) -> Dict[str, Any]:
    raw = await reader.readline()
    if not raw:
        raise ConnectionError("Connection closed by peer")

    text = raw.decode("utf-8").strip()
    if not text:
        raise ValueError("Empty message")

    return json.loads(text)


async def write_json_line(writer: asyncio.StreamWriter, payload: Dict[str, Any]) -> None:
    message = json.dumps(payload, separators=(",", ":")) + "\n"
    writer.write(message.encode("utf-8"))
    await writer.drain()
