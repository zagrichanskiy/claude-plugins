"""The events of ``dispatch.jsonl``, one compact JSON object per line."""
from __future__ import annotations

import enum
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


#: The values of ``Approved.by``: the user answered, or the dispatcher's auto-approve rule applied.
APPROVERS = ("user", "auto")


@dataclass(frozen=True)
class Approved:
    """``cure-job approve`` approved the goal whose bytes have the digest ``goal``."""
    goal: str
    by: str
    at: datetime


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


class DraftMode(enum.Enum):
    """What a goal-writer session does: write ``goal.md``, or apply the user's answers to it."""
    WRITE = "write"
    APPLY = "apply"


@dataclass(frozen=True)
class DraftStarted:
    """``cure-job draft`` started goal-writer session ``session`` as draft ``n`` of the job."""
    n: int
    session: str
    mode: DraftMode
    at: datetime


@dataclass(frozen=True)
class DraftEnded:
    """``cure-job drafted`` ended draft ``n`` with ``open`` items under ``## Open`` and a 3-line summary."""
    n: int
    open: int
    summary: tuple[str, ...]
    at: datetime


Event = Union[Launched, Claim, Release, Approved, Closed, Origin, Reported, StopIssued, SessionsRemoved,
              DraftStarted, DraftEnded]

_LAUNCHED = "launched"
_CLAIM = "claim"
_RELEASE = "release"
_APPROVED = "approved"
_CLOSED = "closed"
_ORIGIN = "origin"
_REPORTED = "reported"
_STOPPED = "stopped"
_SESSIONS_REMOVED = "sessions-removed"
_DRAFT_STARTED = "draft-started"
_DRAFT_ENDED = "draft-ended"


def encode(event: Event) -> str:
    if isinstance(event, Launched):
        fields = {"event": _LAUNCHED, "run": event.run, "session": event.session, "at": format_local(event.at)}
    elif isinstance(event, Claim):
        fields = {"event": _CLAIM, "resource": event.resource}
        if event.run is not None:
            fields["run"] = event.run
    elif isinstance(event, Release):
        fields = {"event": _RELEASE, "resource": event.resource}
    elif isinstance(event, Approved):
        fields = {"event": _APPROVED, "goal": event.goal, "by": event.by, "at": format_local(event.at)}
    elif isinstance(event, Origin):
        fields = {"event": _ORIGIN, "address": event.address, "at": format_local(event.at)}
    elif isinstance(event, Reported):
        fields = {"event": _REPORTED, "run": event.run, "at": format_local(event.at)}
    elif isinstance(event, StopIssued):
        fields = {"event": _STOPPED, "run": event.run, "at": format_local(event.at)}
    elif isinstance(event, SessionsRemoved):
        fields = {"event": _SESSIONS_REMOVED, "at": format_local(event.at)}
    elif isinstance(event, DraftStarted):
        fields = {"event": _DRAFT_STARTED, "n": event.n, "session": event.session, "mode": event.mode.value,
                  "at": format_local(event.at)}
    elif isinstance(event, DraftEnded):
        fields = {"event": _DRAFT_ENDED, "n": event.n, "open": event.open, "summary": list(event.summary),
                  "at": format_local(event.at)}
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
        return Launched(_int(fields, "run"), _text(fields, "session"), parse_local(_text(fields, "at")))
    if kind == _REPORTED:
        return Reported(_int(fields, "run"), parse_local(_text(fields, "at")))
    if kind == _STOPPED:
        return StopIssued(_int(fields, "run"), parse_local(_text(fields, "at")))
    if kind == _SESSIONS_REMOVED:
        return SessionsRemoved(parse_local(_text(fields, "at")))
    if kind == _DRAFT_STARTED:
        try:
            mode = DraftMode(fields.get("mode"))
        except ValueError:
            raise ValueError("mode is missing or not one of " + ", ".join(m.value for m in DraftMode)) from None
        return DraftStarted(_int(fields, "n"), _text(fields, "session"), mode, parse_local(_text(fields, "at")))
    if kind == _DRAFT_ENDED:
        summary = fields.get("summary")
        if not isinstance(summary, list) or not all(isinstance(line, str) for line in summary):
            raise ValueError("summary is missing or not a list of strings")
        return DraftEnded(_int(fields, "n"), _int(fields, "open"), tuple(summary), parse_local(_text(fields, "at")))
    if kind == _CLAIM:
        return Claim(_text(fields, "resource"), None if "run" not in fields else _int(fields, "run"))
    if kind == _RELEASE:
        return Release(_text(fields, "resource"))
    if kind == _APPROVED:
        return Approved(_text(fields, "goal"), _text(fields, "by"), parse_local(_text(fields, "at")))
    if kind == _CLOSED:
        return Closed(_text(fields, "reason"))
    if kind == _ORIGIN:
        return Origin(_text(fields, "address"), parse_local(_text(fields, "at")))
    return None


def _int(fields: dict, key: str) -> int:
    value = fields.get(key)
    # bool is an int subclass, and `true` is not a number.
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{key} is missing or not an integer")
    return value


def _text(fields: dict, key: str) -> str:
    value = fields.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{key} is missing or not a string")
    return value
