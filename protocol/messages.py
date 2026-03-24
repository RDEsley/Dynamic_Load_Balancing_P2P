"""Message builders and validators for protocol tasks."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Dict, Tuple

from protocol.constants import (
    ERROR_INVALID_PAYLOAD,
    PROTOCOL_VERSION,
    RESPONSE_ALIVE,
    RESPONSE_ERROR,
    TASK_ERROR,
    TASK_HEARTBEAT,
)


def _timestamp() -> str:
    return datetime.now(UTC).isoformat()


def _base(server_uuid: str, task: str, request_id: str | None = None) -> Dict[str, Any]:
    message: Dict[str, Any] = {
        "SERVER_UUID": server_uuid,
        "TASK": task,
        "PROTOCOL_VERSION": PROTOCOL_VERSION,
        "TIMESTAMP": _timestamp(),
    }
    if request_id:
        message["REQUEST_ID"] = request_id
    return message


def build_heartbeat_request(server_uuid: str) -> Dict[str, Any]:
    return _base(server_uuid, TASK_HEARTBEAT)


def build_heartbeat_response(server_uuid: str, request_id: str | None = None) -> Dict[str, Any]:
    payload = _base(server_uuid, TASK_HEARTBEAT, request_id=request_id)
    payload["RESPONSE"] = RESPONSE_ALIVE
    return payload


def build_error_response(
    server_uuid: str,
    error_code: str,
    error_message: str,
    request_id: str | None = None,
) -> Dict[str, Any]:
    payload = _base(server_uuid, TASK_ERROR, request_id=request_id)
    payload["RESPONSE"] = RESPONSE_ERROR
    payload["ERROR_CODE"] = error_code
    payload["ERROR_MESSAGE"] = error_message
    return payload


def ensure_request_id(payload: Dict[str, Any]) -> str:
    return str(payload.get("REQUEST_ID") or uuid.uuid4())


def validate_base_message(payload: Dict[str, Any]) -> Tuple[bool, str | None]:
    if not isinstance(payload, dict):
        return False, "Payload must be an object"
    if "SERVER_UUID" not in payload or not payload["SERVER_UUID"]:
        return False, "Missing required field: SERVER_UUID"
    if "TASK" not in payload or not payload["TASK"]:
        return False, "Missing required field: TASK"
    return True, None


def validate_heartbeat_request(payload: Dict[str, Any]) -> Tuple[bool, str | None]:
    ok, message = validate_base_message(payload)
    if not ok:
        return False, message
    if payload.get("TASK") != TASK_HEARTBEAT:
        return False, f"Invalid TASK for heartbeat: {payload.get('TASK')}"
    return True, None


def invalid_payload_response(server_uuid: str, validation_error: str) -> Dict[str, Any]:
    return build_error_response(
        server_uuid=server_uuid,
        error_code=ERROR_INVALID_PAYLOAD,
        error_message=validation_error,
    )
