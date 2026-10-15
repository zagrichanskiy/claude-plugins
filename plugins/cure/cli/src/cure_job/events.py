"""The events of ``dispatch.jsonl``, one compact JSON object per line."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Union

from .clock import format_local, parse_local


@dataclass(frozen=True)
class Launched:
    run: int
    session: str
    at: datetime


@dataclass(frozen=True)
class Claim:
    resource: str


@dataclass(frozen=True)
class Closed:
    reason: str


@dataclass(frozen=True)
class Origin:
    """The session a job reports back to. The latest one wins."""
    address: str
    at: datetime


Event = Union[Launched, Claim, Closed, Origin]

_LAUNCHED = "launched"
_CLAIM = "claim"
_CLOSED = "closed"
_ORIGIN = "origin"


def encode(event: Event) -> str:
    if isinstance(event, Launched):
        fields = {"event": _LAUNCHED, "run": event.run, "session": event.session, "at": format_local(event.at)}
    elif isinstance(event, Claim):
        fields = {"event": _CLAIM, "resource": event.resource}
    elif isinstance(event, Origin):
        fields = {"event": _ORIGIN, "address": event.address, "at": format_local(event.at)}
    else:
        fields = {"event": _CLOSED, "reason": event.reason}
    return json.dumps(fields, separators=(",", ":"))


def decode(line: str) -> Event | None:
    """The event on ``line``, or ``None`` for an event type this version does not know."""
    fields = json.loads(line)
    if not isinstance(fields, dict):
        raise ValueError("not a JSON object")
    kind = fields.get("event")
    if kind == _LAUNCHED:
        run = fields.get("run")
        # bool is an int subclass, and `true` is not a run number.
        if not isinstance(run, int) or isinstance(run, bool):
            raise ValueError("run is missing or not an integer")
        return Launched(run, _text(fields, "session"), parse_local(_text(fields, "at")))
    if kind == _CLAIM:
        return Claim(_text(fields, "resource"))
    if kind == _CLOSED:
        return Closed(_text(fields, "reason"))
    if kind == _ORIGIN:
        return Origin(_text(fields, "address"), parse_local(_text(fields, "at")))
    return None


def _text(fields: dict, key: str) -> str:
    value = fields.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{key} is missing or not a string")
    return value
