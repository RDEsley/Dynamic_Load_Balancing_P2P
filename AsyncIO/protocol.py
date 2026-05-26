"""Master-to-Master and control message protocol helpers (Sprint 03)."""
import json
import uuid
from typing import Any

VALID_REASONS = frozenset({"HIGH_LOAD", "NO_WORKERS_AVAILABLE", "REFUSED"})

M2M_TYPES = frozenset({
    "REQUEST_HELP",
    "RESPONSE_ACCEPTED",
    "RESPONSE_REJECTED",
    "COMMAND_REDIRECT",
    "REGISTER_TEMPORARY_WORKER",
    "COMMAND_RELEASE",
    "NOTIFY_WORKER_RETURNED",
})


def encode_line(message: dict) -> bytes:
    return (json.dumps(message) + "\n").encode("utf-8")


def decode_line(raw: bytes) -> dict:
    return json.loads(raw.decode("utf-8").strip())


def is_m2m_envelope(message: Any) -> bool:
    if not isinstance(message, dict):
        return False
    return "TYPE" in message or "type" in message


def get_message_type(message: dict) -> str | None:
    raw = message.get("TYPE") or message.get("type")
    if raw is None:
        return None
    return str(raw).upper()


def validate_envelope(message: Any, required_fields: set[str] | None = None) -> bool:
    if required_fields is None:
        required_fields = {"TYPE", "REQUEST_ID", "PAYLOAD"}
    if not isinstance(message, dict):
        return False
    normalized = {k.upper() for k in message.keys()}
    return all(field in normalized for field in required_fields)


def validate_payload(payload: Any, required_fields: set[str]) -> bool:
    if not isinstance(payload, dict):
        return False
    normalized = {k.upper() for k in payload.keys()}
    return all(field in normalized for field in required_fields)


def new_request_id() -> str:
    return str(uuid.uuid4()).upper()


def build_request_help(
    request_id: str,
    master_id: str,
    current_load: int,
    capacity: int,
    workers_needed: int,
) -> dict:
    return {
        "TYPE": "REQUEST_HELP",
        "REQUEST_ID": request_id,
        "PAYLOAD": {
            "MASTER_ID": master_id,
            "CURRENT_LOAD": current_load,
            "CAPACITY": capacity,
            "WORKERS_NEEDED": workers_needed,
        },
    }


def build_response_rejected(request_id: str, reason: str) -> dict:
    if reason not in VALID_REASONS:
        reason = "REFUSED"
    return {
        "TYPE": "RESPONSE_REJECTED",
        "REQUEST_ID": request_id,
        "PAYLOAD": {"REASON": reason},
    }


def build_response_accepted(request_id: str, worker_details: list[dict]) -> dict:
    normalized_details = []
    for detail in worker_details:
        worker_id = detail.get("ID") or detail.get("WORKER_ID")
        address = detail.get("ADDRESS")
        if worker_id and address:
            normalized_details.append({"ID": worker_id, "ADDRESS": address})
    return {
        "TYPE": "RESPONSE_ACCEPTED",
        "REQUEST_ID": request_id,
        "PAYLOAD": {
            "WORKERS_OFFERED": len(normalized_details),
            "WORKER_DETAILS": normalized_details,
        },
    }


def build_command_redirect(request_id: str, new_master_address: str) -> dict:
    return {
        "TYPE": "COMMAND_REDIRECT",
        "REQUEST_ID": request_id,
        "PAYLOAD": {"NEW_MASTER_ADDRESS": new_master_address},
    }


def build_register_temporary_worker(
    request_id: str,
    worker_id: str,
    original_master_address: str,
) -> dict:
    return {
        "TYPE": "REGISTER_TEMPORARY_WORKER",
        "REQUEST_ID": request_id,
        "PAYLOAD": {
            "WORKER_ID": worker_id,
            "ORIGINAL_MASTER_ADDRESS": original_master_address,
        },
    }


def build_command_release(request_id: str, original_master_address: str) -> dict:
    return {
        "TYPE": "COMMAND_RELEASE",
        "REQUEST_ID": request_id,
        "PAYLOAD": {"ORIGINAL_MASTER_ADDRESS": original_master_address},
    }


def build_release_request(request_id: str, worker_ids: list[str], original_master_address: str) -> dict:
    """Construir mensagem de pedido de devolução de workers emprestados."""
    return {
        "TYPE": "RELEASE_REQUEST",
        "REQUEST_ID": request_id,
        "PAYLOAD": {
            "WORKER_IDS": worker_ids,
            "ORIGINAL_MASTER_ADDRESS": original_master_address,
        },
    }


def build_notify_worker_returned(request_id: str, worker_id: str) -> dict:
    return {
        "TYPE": "NOTIFY_WORKER_RETURNED",
        "REQUEST_ID": request_id,
        "PAYLOAD": {"WORKER_ID": worker_id},
    }
