import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "AsyncIO"))

import protocol  # noqa: E402
from worker import build_alive_payload, parse_host_port  # noqa: E402


class TestWorkerHeartbeat(unittest.TestCase):
    def test_build_heartbeat_request(self):
        msg = protocol.build_heartbeat_request("Master_A")
        self.assertEqual(msg, {"SERVER_UUID": "Master_A", "TASK": "HEARTBEAT"})


class TestWorkerRedirect(unittest.TestCase):
    def test_build_register_temporary_worker_payload(self):
        msg = protocol.build_register_temporary_worker(
            "REQ-REDIRECT-1",
            "B1",
            "192.168.0.1:8001",
        )
        self.assertEqual(msg["TYPE"], "REGISTER_TEMPORARY_WORKER")
        self.assertEqual(msg["REQUEST_ID"], "REQ-REDIRECT-1")
        self.assertEqual(msg["PAYLOAD"]["WORKER_ID"], "B1")
        self.assertEqual(msg["PAYLOAD"]["ORIGINAL_MASTER_ADDRESS"], "192.168.0.1:8001")

    def test_alive_local_without_server_uuid(self):
        payload = build_alive_payload(False, None)
        self.assertEqual(payload["WORKER"], "ALIVE")
        self.assertNotIn("SERVER_UUID", payload)

    def test_alive_borrowed_with_server_uuid(self):
        payload = build_alive_payload(True, "Master_B")
        self.assertEqual(payload["SERVER_UUID"], "Master_B")

    def test_parse_host_port(self):
        host, port = parse_host_port("10.62.217.31:8000")
        self.assertEqual(host, "10.62.217.31")
        self.assertEqual(port, 8000)


if __name__ == "__main__":
    unittest.main()
