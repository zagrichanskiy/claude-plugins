"""The events of ``dispatch.jsonl``, one compact JSON object per line."""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Union

from .clock import format_local, parse_local


#: The kind of the session a ``launch`` or ``resume`` starts.
WORK = "work"


@dataclass(frozen=True)
class SessionStarted:
    """A session of kind ``kind`` started as its ``n``-th. ``run`` is the work run current at the start."""
    kind: str
    n: int
    session: str
    at: datetime
    run: int
    #: The input copies in the job directory.
    inputs: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        # A work start is stored as a ``launched`` line, which holds neither a separate n nor inputs.
        if self.kind == WORK and (self.n != self.run or self.inputs):
            raise ValueError(f"a work session needs n == run and no inputs: n {self.n}, run {self.run}, "
                             f"inputs {list(self.inputs)}")


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
class SessionStopped:
    """``cure-job stop`` ran for session ``n`` of kind ``kind``. The launch grace no longer applies to it."""
    kind: str
    n: int
    at: datetime


@dataclass(frozen=True)
class SessionEnded:
    """Session ``n`` of kind ``kind`` reported its end with ``summary``. A work session ends with ``result.md``."""
    kind: str
    n: int
    summary: tuple[str, ...]
    at: datetime

    def __post_init__(self) -> None:
        if self.kind == WORK:
            raise ValueError("a work session ends with result.md, not an event")


@dataclass(frozen=True)
class SessionsRemoved:
    """``cure-job remove-sessions`` left no session of the job listed."""
    at: datetime


Event = Union[SessionStarted, Claim, Release, Approved, Closed, Origin, Reported, SessionStopped, SessionEnded,
              SessionsRemoved]

_LAUNCHED = "launched"
_CLAIM = "claim"
_RELEASE = "release"
_APPROVED = "approved"
_CLOSED = "closed"
_ORIGIN = "origin"
_REPORTED = "reported"
_STOPPED = "stopped"
_SESSIONS_REMOVED = "sessions-removed"
#: The tags of a session of a kind other than work. A work session keeps ``launched`` and ``stopped``,
#: which an older version reads.
_SESSION_STARTED = "session-started"
_SESSION_STOPPED = "session-stopped"
_SESSION_ENDED = "session-ended"


def encode(event: Event) -> str:
    if isinstance(event, SessionStarted) and event.kind == WORK:
        fields = {"event": _LAUNCHED, "run": event.run, "session": event.session, "at": format_local(event.at)}
    elif isinstance(event, SessionStarted):
        fields = {"event": _SESSION_STARTED, "kind": event.kind, "n": event.n, "session": event.session,
                  "run": event.run, "inputs": list(event.inputs), "at": format_local(event.at)}
    elif isinstance(event, SessionStopped) and event.kind == WORK:
        fields = {"event": _STOPPED, "run": event.n, "at": format_local(event.at)}
    elif isinstance(event, SessionStopped):
        fields = {"event": _SESSION_STOPPED, "kind": event.kind, "n": event.n, "at": format_local(event.at)}
    elif isinstance(event, SessionEnded):
        fields = {"event": _SESSION_ENDED, "kind": event.kind, "n": event.n, "summary": list(event.summary),
                  "at": format_local(event.at)}
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
        run = _int(fields, "run")
        return SessionStarted(WORK, run, _text(fields, "session"), parse_local(_text(fields, "at")), run)
    if kind == _REPORTED:
        return Reported(_int(fields, "run"), parse_local(_text(fields, "at")))
    if kind == _STOPPED:
        return SessionStopped(WORK, _int(fields, "run"), parse_local(_text(fields, "at")))
    if kind == _SESSIONS_REMOVED:
        return SessionsRemoved(parse_local(_text(fields, "at")))
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
    if kind == _SESSION_STARTED:
        return SessionStarted(_session_kind(fields), _int(fields, "n"), _text(fields, "session"),
                              parse_local(_text(fields, "at")), _int(fields, "run"), _texts(fields, "inputs"))
    if kind == _SESSION_STOPPED:
        return SessionStopped(_session_kind(fields), _int(fields, "n"), parse_local(_text(fields, "at")))
    if kind == _SESSION_ENDED:
        return SessionEnded(_session_kind(fields), _int(fields, "n"), _texts(fields, "summary"),
                            parse_local(_text(fields, "at")))
    return None


def _int(fields: dict, key: str) -> int:
    value = fields.get(key)
    # bool is an int subclass, and `true` is not a number.
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{key} is missing or not an integer")
    return value


def _session_kind(fields: dict) -> str:
    kind = _text(fields, "kind")
    if kind == WORK:
        raise ValueError(f"a work session is never stored as {fields['event']}")
    return kind


def _texts(fields: dict, key: str) -> tuple[str, ...]:
    values = fields.get(key)
    if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
        raise ValueError(f"{key} is missing or not a list of strings")
    return tuple(values)


def _text(fields: dict, key: str) -> str:
    value = fields.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{key} is missing or not a string")
    return value
