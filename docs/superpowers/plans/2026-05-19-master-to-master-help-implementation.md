# Master-to-Master Help Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Sprint 03 Master-to-Master help flow in AsyncIO, including help request/response correlation, worker redirection, temporary registration, and worker return when load normalizes.

**Architecture:** Keep a single AsyncIO server in `AsyncIO/master.py` that accepts both Worker and Master control envelopes. Add focused protocol helpers in a new module for message framing/validation and add explicit Master runtime state for temporary workers and in-flight help requests. Extend `AsyncIO/worker.py` to process redirect/release commands and reconnect to target masters while preserving the existing heartbeat and task cycle.

**Tech Stack:** Python 3.13, asyncio, json, socket/TCP, unittest (standard library)

---

## File Structure

- Modify: `AsyncIO/master.py`
  - Add Master-to-Master message handling (`REQUEST_HELP`, `RESPONSE_*`, `NOTIFY_WORKER_RETURNED`)
  - Add policy decisions (`HIGH_LOAD`, `NO_WORKERS_AVAILABLE`, `REFUSED`)
  - Add temporary worker tracking and release behavior (`COMMAND_RELEASE`)
- Modify: `AsyncIO/worker.py`
  - Add control flow for `COMMAND_REDIRECT` and `COMMAND_RELEASE`
  - Add `REGISTER_TEMPORARY_WORKER` handshake with target master
- Create: `AsyncIO/protocol.py`
  - Envelope parsing/validation helpers with tolerant unknown fields
  - `\n`-delimited JSON serializer/parser utilities
- Create: `tests/test_protocol.py`
  - Unit tests for envelope validation and required fields behavior
- Create: `tests/test_master_m2m.py`
  - Async tests for help request acceptance/rejection and same `REQUEST_ID` correlation
- Create: `tests/test_worker_redirect.py`
  - Async tests for redirect/release worker behavior and registration payload

## Task 1: Add Protocol Utilities and Validation

**Files:**
- Create: `AsyncIO/protocol.py`
- Test: `tests/test_protocol.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_protocol.py
import unittest
from AsyncIO import protocol

class TestProtocol(unittest.TestCase):
    def test_validate_request_help_requires_fields(self):
        msg = {
            "TYPE": "REQUEST_HELP",
            "REQUEST_ID": "REQ1",
            "PAYLOAD": {"MASTER_ID": "A", "CURRENT_LOAD": 120, "CAPACITY": 100, "WORKERS_NEEDED": 2},
        }
        self.assertTrue(protocol.validate_envelope(msg, {"TYPE", "REQUEST_ID", "PAYLOAD"}))
        self.assertTrue(protocol.validate_payload(msg["PAYLOAD"], {"MASTER_ID", "CURRENT_LOAD", "CAPACITY", "WORKERS_NEEDED"}))

    def test_validate_payload_missing_required_fails(self):
        payload = {"MASTER_ID": "A", "CAPACITY": 100}
        self.assertFalse(protocol.validate_payload(payload, {"MASTER_ID", "CURRENT_LOAD", "CAPACITY", "WORKERS_NEEDED"}))

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_protocol.py -v`
Expected: FAIL with import error for `AsyncIO.protocol`

- [ ] **Step 3: Write minimal implementation**

```python
# AsyncIO/protocol.py
import json
from typing import Any


def validate_envelope(message: Any, required_fields: set[str]) -> bool:
    if not isinstance(message, dict):
        return False
    return all(field in message for field in required_fields)


def validate_payload(payload: Any, required_fields: set[str]) -> bool:
    if not isinstance(payload, dict):
        return False
    return all(field in payload for field in required_fields)


def encode_line(message: dict) -> bytes:
    return (json.dumps(message) + "\n").encode("utf-8")


def decode_line(raw: bytes) -> dict:
    return json.loads(raw.decode("utf-8").strip())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests/test_protocol.py -v`
Expected: PASS for 2 tests

- [ ] **Step 5: Commit**

```bash
git add AsyncIO/protocol.py tests/test_protocol.py
git commit -m "test/protocol: add envelope validation helpers"
```

## Task 2: Add Master-to-Master Help Request/Response in Master

**Files:**
- Modify: `AsyncIO/master.py`
- Test: `tests/test_master_m2m.py`

- [ ] **Step 1: Write the failing async test**

```python
# tests/test_master_m2m.py
import unittest

from AsyncIO import master

class TestMasterM2M(unittest.IsolatedAsyncioTestCase):
    async def test_build_rejected_response_keeps_request_id(self):
        request_id = "REQ-ABC"
        msg = master.build_response_rejected(request_id, "HIGH_LOAD")
        self.assertEqual(msg["TYPE"], "RESPONSE_REJECTED")
        self.assertEqual(msg["REQUEST_ID"], request_id)
        self.assertEqual(msg["PAYLOAD"]["REASON"], "HIGH_LOAD")

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_master_m2m.py -v`
Expected: FAIL with `AttributeError: module 'AsyncIO.master' has no attribute 'build_response_rejected'`

- [ ] **Step 3: Write minimal implementation in master**

```python
# Add in AsyncIO/master.py

VALID_REASONS = {"HIGH_LOAD", "NO_WORKERS_AVAILABLE", "REFUSED"}


def build_response_rejected(request_id: str, reason: str) -> dict:
    if reason not in VALID_REASONS:
        reason = "REFUSED"
    return {
        "TYPE": "RESPONSE_REJECTED",
        "REQUEST_ID": request_id,
        "PAYLOAD": {"REASON": reason},
    }


def build_response_accepted(request_id: str, worker_details: list[dict]) -> dict:
    return {
        "TYPE": "RESPONSE_ACCEPTED",
        "REQUEST_ID": request_id,
        "PAYLOAD": {
            "WORKERS_OFFERED": len(worker_details),
            "WORKER_DETAILS": worker_details,
        },
    }
```

- [ ] **Step 4: Add message branch for `REQUEST_HELP`**

```python
# Inside tratar_worker/read loop branch in AsyncIO/master.py
elif payload.get("TYPE") == "REQUEST_HELP":
    if not validar_payload(payload, {"TYPE", "REQUEST_ID", "PAYLOAD"}):
        print(f"[ERRO] REQUEST_HELP inválido de {addr}: campos obrigatórios ausentes")
        continue

    req_payload = payload.get("PAYLOAD", {})
    if not validar_payload(req_payload, {"MASTER_ID", "CURRENT_LOAD", "CAPACITY", "WORKERS_NEEDED"}):
        print(f"[ERRO] REQUEST_HELP inválido de {addr}: PAYLOAD incompleto")
        continue

    request_id = payload["REQUEST_ID"]
    decision = decide_help_response(req_payload)
    if decision["accepted"]:
        response = build_response_accepted(request_id, decision["worker_details"])
    else:
        response = build_response_rejected(request_id, decision["reason"])

    writer.write((json.dumps(response) + "\n").encode())
    await writer.drain()
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m unittest tests/test_master_m2m.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add AsyncIO/master.py tests/test_master_m2m.py
git commit -m "feat(master): add REQUEST_HELP response builders and validation"
```

## Task 3: Add Worker Redirect and Temporary Registration

**Files:**
- Modify: `AsyncIO/worker.py`
- Test: `tests/test_worker_redirect.py`

- [ ] **Step 1: Write failing test for registration payload**

```python
# tests/test_worker_redirect.py
import unittest
from AsyncIO import worker

class TestWorkerRedirect(unittest.TestCase):
    def test_build_register_temporary_worker_payload(self):
        msg = worker.build_register_temporary_worker(
            request_id="REQ-REDIRECT-1",
            worker_id="B1",
            original_master_address="IP_MASTER_B:PORT",
        )
        self.assertEqual(msg["TYPE"], "REGISTER_TEMPORARY_WORKER")
        self.assertEqual(msg["REQUEST_ID"], "REQ-REDIRECT-1")
        self.assertEqual(msg["PAYLOAD"]["WORKER_ID"], "B1")

if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_worker_redirect.py -v`
Expected: FAIL with missing `build_register_temporary_worker`

- [ ] **Step 3: Write minimal worker implementation**

```python
# Add in AsyncIO/worker.py


def build_register_temporary_worker(request_id: str, worker_id: str, original_master_address: str) -> dict:
    return {
        "TYPE": "REGISTER_TEMPORARY_WORKER",
        "REQUEST_ID": request_id,
        "PAYLOAD": {
            "WORKER_ID": worker_id,
            "ORIGINAL_MASTER_ADDRESS": original_master_address,
        },
    }


def parse_host_port(address: str) -> tuple[str, int]:
    host, port = address.rsplit(":", 1)
    return host, int(port)
```

- [ ] **Step 4: Handle `COMMAND_REDIRECT` and `COMMAND_RELEASE` in heartbeat loop**

```python
# Add branch after reading response in enviar_heartbeat()
elif res.get("TYPE") == "COMMAND_REDIRECT":
    redirect_address = res.get("PAYLOAD", {}).get("NEW_MASTER_ADDRESS")
    if not redirect_address:
        print("[WORKER] COMMAND_REDIRECT inválido: NEW_MASTER_ADDRESS ausente")
    else:
        new_host, new_port = parse_host_port(redirect_address)
        writer.close()
        await writer.wait_closed()

        r2, w2 = await asyncio.open_connection(new_host, new_port)
        register_msg = build_register_temporary_worker(
            request_id=res.get("REQUEST_ID", "REQUEST_ID_NOVO"),
            worker_id=WORKER_UUID,
            original_master_address=f"{HOST}:{PORT}",
        )
        w2.write((json.dumps(register_msg) + "\n").encode())
        await w2.drain()
        data2 = await asyncio.wait_for(r2.readline(), timeout=5)
        if data2:
            print(f"[WORKER] Registro temporário aceito: {data2.decode().strip()}")
        w2.close()
        await w2.wait_closed()

elif res.get("TYPE") == "COMMAND_RELEASE":
    original_address = res.get("PAYLOAD", {}).get("ORIGINAL_MASTER_ADDRESS")
    print(f"[WORKER] Recebido COMMAND_RELEASE para {original_address}")
    if original_address:
        HOST_RELEASE, PORT_RELEASE = parse_host_port(original_address)
        # atualizar destino para próximo ciclo
        globals()["HOST"] = HOST_RELEASE
        globals()["PORT"] = PORT_RELEASE
```

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m unittest tests/test_worker_redirect.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add AsyncIO/worker.py tests/test_worker_redirect.py
git commit -m "feat(worker): add redirect and temporary registration flow"
```

## Task 4: Implement Worker Release and Notification in Master A

**Files:**
- Modify: `AsyncIO/master.py`
- Test: `tests/test_master_m2m.py`

- [ ] **Step 1: Write failing test for release command builder**

```python
# append in tests/test_master_m2m.py
    async def test_build_command_release_payload(self):
        msg = master.build_command_release("REQ-REL-1", "IP_MASTER_B:PORT")
        self.assertEqual(msg["TYPE"], "COMMAND_RELEASE")
        self.assertEqual(msg["PAYLOAD"]["ORIGINAL_MASTER_ADDRESS"], "IP_MASTER_B:PORT")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests/test_master_m2m.py -v`
Expected: FAIL with missing `build_command_release`

- [ ] **Step 3: Add release/notify builders in master**

```python
# Add in AsyncIO/master.py

def build_command_release(request_id: str, original_master_address: str) -> dict:
    return {
        "TYPE": "COMMAND_RELEASE",
        "REQUEST_ID": request_id,
        "PAYLOAD": {"ORIGINAL_MASTER_ADDRESS": original_master_address},
    }


def build_notify_worker_returned(request_id: str, worker_id: str) -> dict:
    return {
        "TYPE": "NOTIFY_WORKER_RETURNED",
        "REQUEST_ID": request_id,
        "PAYLOAD": {"WORKER_ID": worker_id},
    }
```

- [ ] **Step 4: Add normalized-load release policy hook**

```python
# Add in AsyncIO/master.py

def is_normalized(load_samples: list[int], threshold: int) -> bool:
    if len(load_samples) < 3:
        return False
    return all(sample < threshold for sample in load_samples[-3:])
```

- [ ] **Step 5: Run tests to verify pass**

Run: `python -m unittest tests/test_master_m2m.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add AsyncIO/master.py tests/test_master_m2m.py
git commit -m "feat(master): add worker release and return notification payloads"
```

## Task 5: End-to-End AsyncIO Smoke Tests and Regression

**Files:**
- Modify: `tests/test_master_m2m.py`
- Modify: `tests/test_worker_redirect.py`

- [ ] **Step 1: Add integration-style async tests for correlation**

```python
# Example additional test in tests/test_master_m2m.py
    async def test_response_accepted_keeps_same_request_id(self):
        req_id = "REQ-777"
        response = master.build_response_accepted(req_id, [{"ID": "B1", "ADDRESS": "IP:PORT_WORKER_B1"}])
        self.assertEqual(response["REQUEST_ID"], req_id)
```

- [ ] **Step 2: Run targeted tests**

Run: `python -m unittest tests/test_master_m2m.py tests/test_worker_redirect.py -v`
Expected: PASS

- [ ] **Step 3: Run full suite**

Run: `python -m unittest discover -s tests -v`
Expected: PASS

- [ ] **Step 4: Manual smoke run (2 masters + 1 worker)**

Run:

```bash
# Terminal 1
set HOST=127.0.0.1
python AsyncIO/master.py

# Terminal 2 (simulated second master with different port, after adding config support)
set PORT=8001
python AsyncIO/master.py

# Terminal 3
python AsyncIO/worker.py
```

Expected:
- Master A logs `REQUEST_HELP` / `RESPONSE_*`
- Redirect command observed
- Worker sends `REGISTER_TEMPORARY_WORKER`
- Master A later emits `COMMAND_RELEASE` and `NOTIFY_WORKER_RETURNED`

- [ ] **Step 5: Commit**

```bash
git add tests/test_master_m2m.py tests/test_worker_redirect.py
git commit -m "test: add sprint 03 m2m and redirect regression coverage"
```

## Task 6: Documentation and Compatibility Notes

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Write failing doc check (manual)**

Run: `rg "REQUEST_HELP|COMMAND_REDIRECT|REGISTER_TEMPORARY_WORKER|COMMAND_RELEASE|NOTIFY_WORKER_RETURNED" README.md`
Expected: no matches before update

- [ ] **Step 2: Add protocol section in README**

```markdown
### Master-to-Master (Sprint 03)

Envelope padrão:

```json
{
  "TYPE": "...",
  "REQUEST_ID": "REQUEST_ID_UNICO",
  "PAYLOAD": { }
}
```

Mensagens:
- `REQUEST_HELP`
- `RESPONSE_ACCEPTED`
- `RESPONSE_REJECTED` (`HIGH_LOAD`, `NO_WORKERS_AVAILABLE`, `REFUSED`)
- `COMMAND_REDIRECT`
- `REGISTER_TEMPORARY_WORKER`
- `COMMAND_RELEASE`
- `NOTIFY_WORKER_RETURNED`
```

- [ ] **Step 3: Verify docs contain new protocol names**

Run: `rg "REQUEST_HELP|COMMAND_REDIRECT|REGISTER_TEMPORARY_WORKER|COMMAND_RELEASE|NOTIFY_WORKER_RETURNED" README.md`
Expected: each token appears at least once

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: describe sprint 03 master-to-master protocol"
```

## Self-Review Checklist Results

- Spec coverage: all required message types, same-connection response for help, `REQUEST_ID` correlation, reject reasons, redirect/register/release/notify, and parser behavior are mapped to tasks 1-5.
- Placeholder scan: no `TODO`/`TBD` placeholders in tasks.
- Type consistency: control fields use uppercase (`TYPE`, `REQUEST_ID`, `PAYLOAD`, `REASON`, `WORKER_ID`, addresses). Same-`REQUEST_ID` requirement is enforced in tests.
