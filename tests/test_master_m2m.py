import os
import sys
import unittest
from unittest.mock import AsyncMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "AsyncIO"))

import protocol  # noqa: E402


class TestMasterM2MBuilders(unittest.TestCase):
    def test_build_response_rejected_keeps_request_id(self):
        msg = protocol.build_response_rejected("REQ-ABC", "HIGH_LOAD")
        self.assertEqual(msg["TYPE"], "RESPONSE_REJECTED")
        self.assertEqual(msg["REQUEST_ID"], "REQ-ABC")

    def test_build_response_accepted_worker_details(self):
        details = [{"ID": "W1", "ADDRESS": "127.0.0.1:9001"}]
        msg = protocol.build_response_accepted("REQ-2", details)
        self.assertEqual(msg["PAYLOAD"]["WORKERS_OFFERED"], 1)
        self.assertEqual(msg["PAYLOAD"]["WORKER_DETAILS"][0]["ID"], "W1")

    def test_build_command_release(self):
        msg = protocol.build_command_release("REQ-REL", "10.0.0.1:8001")
        self.assertEqual(msg["TYPE"], "COMMAND_RELEASE")
        self.assertEqual(msg["PAYLOAD"]["ORIGINAL_MASTER_ADDRESS"], "10.0.0.1:8001")

    def test_build_request_help(self):
        msg = protocol.build_request_help("R1", "A", 150, 100, 2)
        self.assertEqual(msg["TYPE"], "REQUEST_HELP")
        self.assertEqual(msg["PAYLOAD"]["WORKERS_NEEDED"], 2)


class TestMasterHelpers(unittest.IsolatedAsyncioTestCase):
    async def test_async_decide_help_response_high_load(self):
        import master as m

        m.task_queue.clear()
        m.neighbor_masters.clear()
        m.connected_workers.clear()
        for i in range(m.CAPACITY):
            m.task_queue.append(f"t{i}")

        decision = await m.async_decide_help_response(
            {"MASTER_ID": "A", "WORKERS_NEEDED": 1}
        )
        self.assertFalse(decision["ACCEPTED"])
        self.assertEqual(decision["REASON"], "HIGH_LOAD")

    async def test_async_decide_help_response_accepts_idle_worker(self):
        import master as m

        m.task_queue.clear()
        m.neighbor_masters["A"] = "127.0.0.1:8000"
        m.connected_workers.clear()
        m.connected_workers["W1"] = {
            "address": "127.0.0.1:9000",
            "temporary": False,
            "busy": False,
            "writer": object(),
        }

        decision = await m.async_decide_help_response(
            {"MASTER_ID": "A", "WORKERS_NEEDED": 1}
        )
        self.assertTrue(decision["ACCEPTED"])
        self.assertEqual(len(decision["WORKER_DETAILS"]), 1)

    def test_is_normalized_hysteresis(self):
        import master as m

        self.assertFalse(m.is_normalized([70, 65], m.RELEASE_THRESHOLD))
        self.assertTrue(m.is_normalized([50, 55, 58], m.RELEASE_THRESHOLD))

    async def test_normalized_load_releases_idle_temporary_worker(self):
        import master as m

        class DummyWriter:
            def __init__(self):
                self.buffer = []

            def write(self, data):
                self.buffer.append(data)

            async def drain(self):
                return None

            def get_extra_info(self, _name):
                return ("127.0.0.1", 9999)

        m.task_queue.clear()
        m.connected_workers.clear()
        m.temporary_workers.clear()
        m.load_samples.clear()
        m.load_samples.extend([50, 55, 58])

        writer = DummyWriter()
        worker_id = "WB1"
        m.connected_workers[worker_id] = {
            "reader": object(),
            "writer": writer,
            "address": "127.0.0.1:9001",
            "temporary": True,
            "busy": False,
            "peer": ("127.0.0.1", 9001),
        }
        m.temporary_workers[worker_id] = "127.0.0.1:8001"

        original_release = m.maybe_release_temporary_worker
        release_spy = AsyncMock()
        m.maybe_release_temporary_worker = release_spy
        try:
            await m.release_normalized_temporary_workers()
        finally:
            m.maybe_release_temporary_worker = original_release

        release_spy.assert_awaited_once_with(worker_id, writer)

    async def test_alive_does_not_overwrite_original_address_from_register(self):
        """
        Regression: if a temporary worker registers with ORIGINAL_MASTER_ADDRESS (host:port),
        subsequent ALIVE payloads that include SERVER_UUID must not overwrite that address.
        Otherwise COMMAND_RELEASE may carry an invalid value (e.g. "B") and the worker can't return.
        """
        import master as m

        class DummyWriter:
            def __init__(self):
                self.buffer = []

            def write(self, data):
                self.buffer.append(data)

            async def drain(self):
                return None

            def get_extra_info(self, _name):
                return ("127.0.0.1", 9999)

        m.task_queue.clear()
        m.connected_workers.clear()
        m.temporary_workers.clear()
        m.neighbor_masters.clear()

        worker_id = "WB1"
        original_address = "192.168.0.10:8001"
        m.temporary_workers[worker_id] = original_address
        # Different address than the one registered (simulates ambiguous neighbor mapping);
        # ALIVE must NOT overwrite the address we got from REGISTER_TEMPORARY_WORKER.
        m.neighbor_masters["B"] = "10.0.0.1:8001"

        reader = object()
        writer = DummyWriter()
        addr = ("127.0.0.1", 9001)

        alive = {"WORKER": "ALIVE", "WORKER_UUID": worker_id, "SERVER_UUID": "B"}
        await m.tratar_sprint02(alive, reader, writer, addr)

        self.assertEqual(m.temporary_workers.get(worker_id), original_address)

    async def test_borrowed_worker_not_released_after_task(self):
        """PDF CT06: devolução só quando carga normaliza (histerese), não após cada tarefa."""
        import master as m

        class DummyWriter:
            def __init__(self):
                self.buffer = []

            def write(self, data):
                self.buffer.append(data)

            async def drain(self):
                return None

            def get_extra_info(self, _name):
                return ("127.0.0.1", 9999)

        m.temporary_workers.clear()
        m.connected_workers.clear()
        worker_id = "WB1"
        m.temporary_workers[worker_id] = "127.0.0.1:8001"
        m.connected_workers[worker_id] = {
            "writer": DummyWriter(),
            "busy": True,
        }

        release_spy = AsyncMock()
        original_release = m.maybe_release_temporary_worker
        m.maybe_release_temporary_worker = release_spy
        try:
            payload = {
                "STATUS": "OK",
                "TASK": "QUERY",
                "WORKER_UUID": worker_id,
            }
            await m.tratar_sprint02(
                payload, object(), m.connected_workers[worker_id]["writer"], ("127.0.0.1", 9001)
            )
        finally:
            m.maybe_release_temporary_worker = original_release

        release_spy.assert_not_awaited()
        self.assertIn(worker_id, m.temporary_workers)

    async def test_ack_payload_pdf_format(self):
        import master as m

        class DummyWriter:
            def __init__(self):
                self.buffer = []

            def write(self, data):
                self.buffer.append(data)

            async def drain(self):
                return None

        writer = DummyWriter()
        payload = {"STATUS": "OK", "TASK": "QUERY", "WORKER_UUID": "W1"}
        await m.tratar_sprint02(payload, object(), writer, ("127.0.0.1", 9001))

        import json

        sent = json.loads(writer.buffer[-1].decode().strip())
        self.assertEqual(sent, {"STATUS": "ACK"})


if __name__ == "__main__":
    unittest.main()
