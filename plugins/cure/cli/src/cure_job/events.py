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
    #: The run that claimed. ``None`` marks a claim written before run-scoped claims.
    run: int | None = None


@dataclass(frozen=True)
class Release:
    """``cure-job release`` ended the job's short hold on ``resource``."""
    resource: str


@dataclass(frozen=True)
class Closed:
    reason: str


@dataclass(frozen=True)
class Origin:
    """The session a job reports back to. The latest one wins."""
    address: str
    at: datetime


@dataclass(frozen=True)
class Reported:
    """The origin session was told of the result of run ``run``."""
    run: int
    at: datetime


@dataclass(frozen=True)
class StopIssued:
    """``cure-job stop`` ran for run ``run``. The launch grace no longer applies to that run."""
    run: int
    at: datetime


@dataclass(frozen=True)
class SessionsRemoved:
    """``cure-job remove-sessions`` left no session of the job listed."""
    at: datetime


Event = Union[Launched, Claim, Release, Closed, Origin, Reported, StopIssued, SessionsRemoved]

_LAUNCHED = "launched"
_CLAIM = "claim"
_RELEASE = "release"
_CLOSED = "closed"
_ORIGIN = "origin"
_REPORTED = "reported"
_STOPPED = "stopped"
_SESSIONS_REMOVED = "sessions-removed"


def encode(event: Event) -> str:
    if isinstance(event, Launched):
        fields = {"event": _LAUNCHED, "run": event.run, "session": event.session, "at": format_local(event.at)}
    elif isinstance(event, Claim):
        fields = {"event": _CLAIM, "resource": event.resource}
        if event.run is not None:
            fields["run"] = event.run
    elif isinstance(event, Release):
        fields = {"event": _RELEASE, "resource": event.resource}
    elif isinstance(event, Origin):
        fields = {"event": _ORIGIN, "address": event.address, "at": format_local(event.at)}
    elif isinstance(event, Reported):
        fields = {"event": _REPORTED, "run": event.run, "at": format_local(event.at)}
    elif isinstance(event, StopIssued):
        fields = {"event": _STOPPED, "run": event.run, "at": format_local(event.at)}
    elif isinstance(event, SessionsRemoved):
        fields = {"event": _SESSIONS_REMOVED, "at": format_local(event.at)}
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
        return Launched(_run(fields), _text(fields, "session"), parse_local(_text(fields, "at")))
    if kind == _REPORTED:
        return Reported(_run(fields), parse_local(_text(fields, "at")))
    if kind == _STOPPED:
        return StopIssued(_run(fields), parse_local(_text(fields, "at")))
    if kind == _SESSIONS_REMOVED:
        return SessionsRemoved(parse_local(_text(fields, "at")))
    if kind == _CLAIM:
        return Claim(_text(fields, "resource"), None if "run" not in fields else _run(fields))
    if kind == _RELEASE:
        return Release(_text(fields, "resource"))
    if kind == _CLOSED:
        return Closed(_text(fields, "reason"))
    if kind == _ORIGIN:
        return Origin(_text(fields, "address"), parse_local(_text(fields, "at")))
    return None


def _run(fields: dict) -> int:
    run = fields.get("run")
    # bool is an int subclass, and `true` is not a run number.
    if not isinstance(run, int) or isinstance(run, bool):
        raise ValueError("run is missing or not an integer")
    return run


def _text(fields: dict, key: str) -> str:
    value = fields.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{key} is missing or not a string")
    return value
