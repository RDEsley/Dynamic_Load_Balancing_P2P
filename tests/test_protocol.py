import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "AsyncIO"))

import protocol  # noqa: E402


class TestProtocol(unittest.TestCase):
    def test_validate_request_help_requires_fields(self):
        msg = {
            "TYPE": "REQUEST_HELP",
            "REQUEST_ID": "REQ1",
            "PAYLOAD": {
                "MASTER_ID": "A",
                "CURRENT_LOAD": 120,
                "CAPACITY": 100,
                "WORKERS_NEEDED": 2,
            },
        }
        self.assertTrue(protocol.validate_envelope(msg))
        self.assertTrue(
            protocol.validate_payload(
                msg["PAYLOAD"],
                {"MASTER_ID", "CURRENT_LOAD", "CAPACITY", "WORKERS_NEEDED"},
            )
        )

    def test_validate_payload_missing_required_fails(self):
        payload = {"MASTER_ID": "A", "CAPACITY": 100}
        self.assertFalse(
            protocol.validate_payload(
                payload,
                {"MASTER_ID", "CURRENT_LOAD", "CAPACITY", "WORKERS_NEEDED"},
            )
        )

    def test_build_response_rejected(self):
        msg = protocol.build_response_rejected("REQ-1", "HIGH_LOAD")
        self.assertEqual(msg["TYPE"], "RESPONSE_REJECTED")
        self.assertEqual(msg["REQUEST_ID"], "REQ-1")
        self.assertEqual(msg["PAYLOAD"]["REASON"], "HIGH_LOAD")

    def test_is_m2m_envelope(self):
        self.assertTrue(protocol.is_m2m_envelope({"TYPE": "REQUEST_HELP"}))
        self.assertFalse(protocol.is_m2m_envelope({"WORKER": "ALIVE"}))

    def test_encode_decode_line(self):
        raw = protocol.encode_line({"TYPE": "TEST", "X": 1})
        decoded = protocol.decode_line(raw)
        self.assertEqual(decoded["TYPE"], "TEST")


if __name__ == "__main__":
    unittest.main()
