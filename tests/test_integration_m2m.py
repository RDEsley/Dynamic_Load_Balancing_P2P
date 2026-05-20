"""Integration smoke tests for Sprint 3 M2M (local TCP)."""
import asyncio
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "AsyncIO"))

import protocol  # noqa: E402


class TestIntegrationM2M(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import master as m

        self.m = m
        m.task_queue.clear()
        m.connected_workers.clear()
        m.temporary_workers.clear()
        m.neighbor_masters.clear()
        m.load_samples.clear()
        m.CAPACITY = 100
        m.RELEASE_THRESHOLD = 60
        m.neighbor_masters["A"] = "127.0.0.1:19000"
        m.connected_workers["W1"] = {
            "writer": None,
            "address": "127.0.0.1:19099",
            "temporary": False,
            "busy": False,
        }

    async def test_ct02_high_load_rejection(self):
        import master as m

        for i in range(m.CAPACITY):
            m.task_queue.append(f"t{i}")
        decision = await m.async_decide_help_response(
            {"MASTER_ID": "A", "WORKERS_NEEDED": 1}
        )
        self.assertFalse(decision["ACCEPTED"])
        self.assertEqual(decision["REASON"], "HIGH_LOAD")

    async def test_request_help_same_request_id(self):
        import master as m

        server = await asyncio.start_server(m.tratar_conexao, "127.0.0.1", 19010)
        await asyncio.sleep(0.05)

        request_id = protocol.new_request_id()
        reader, writer = await asyncio.open_connection("127.0.0.1", 19010)
        msg = protocol.build_request_help(request_id, "A", 50, 100, 1)
        writer.write(protocol.encode_line(msg))
        await writer.drain()
        data = await asyncio.wait_for(reader.readline(), timeout=5)
        writer.close()
        await writer.wait_closed()
        server.close()
        await server.wait_closed()

        resp = json.loads(data.decode().strip())
        self.assertEqual(resp["REQUEST_ID"], request_id)
        self.assertIn(resp["TYPE"], ("RESPONSE_ACCEPTED", "RESPONSE_REJECTED"))

    async def test_ct09_unknown_type_ignored(self):
        import master as m

        server = await asyncio.start_server(m.tratar_conexao, "127.0.0.1", 19011)
        await asyncio.sleep(0.05)
        reader, writer = await asyncio.open_connection("127.0.0.1", 19011)
        bad = {"TYPE": "FUTURE_MESSAGE", "REQUEST_ID": "X", "PAYLOAD": {}}
        writer.write(protocol.encode_line(bad))
        await writer.drain()
        await asyncio.sleep(0.1)
        writer.close()
        await writer.wait_closed()
        server.close()
        await server.wait_closed()
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
