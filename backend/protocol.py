"""Newline-delimited JSON protocol for the Omarchy Adoption Tracker daemon socket.

Not an Omarchy-documented convention: this is our own small request/response +
push-event protocol, modeled after nothing more than "one JSON object per line."
"""

from __future__ import annotations

import json
from typing import Any

PROTOCOL_VERSION = 1


def dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def parse_line(line: str) -> dict[str, Any] | None:
    text = (line or "").strip()
    if not text:
        return None
    try:
        message = json.loads(text)
    except json.JSONDecodeError:
        return None
    return message if isinstance(message, dict) else None


def response(request_id: Any, ok: bool, result: dict[str, Any] | None = None,
             code: str = "", message: str = "") -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": "response",
        "v": PROTOCOL_VERSION,
        "id": request_id,
        "ok": ok,
    }
    if ok:
        payload["result"] = result or {}
    else:
        payload["error"] = {
            "code": code or "invalid_request",
            "message": message or "Request failed",
        }
    return payload


def event(name: str, state: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "event",
        "v": PROTOCOL_VERSION,
        "event": name,
        "state": state,
    }
