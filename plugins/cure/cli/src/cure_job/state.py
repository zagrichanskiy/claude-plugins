"""Job states, derived and never stored.

This module holds the States table, the lock rule and the retention rule. An
open draft (a goal-writer session ``cure-job drafted`` has not ended) gives the
job a draft state, unless a run is launched, running, stalled or blocked. No
lock file exists. Lock order puts a job with a launched event first, then
ascending id. In lock order, a launched open job holds each resource it names
that no job before it holds. A ready job (see :func:`is_ready`) whose
``after`` predecessor, if any, is done holds every resource it names when no
job before it holds any of them, else none. Every other job holds nothing.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import AbstractSet, Iterable, Mapping, Sequence

from .claude import SessionStatus
from .config import DEFAULTS, Config
from .job import JobRecord
from .result import ResultStatus


class State(enum.Enum):
    QUEUED = "queued"
    HELD = "held"
    AWAITING_APPROVAL = "awaiting-approval"
    APPROVED = "approved"
    LAUNCHED = "launched"
    RUNNING = "running"
    STALLED = "stalled"
    BLOCKED = "blocked"
    LOST = "lost"
    NEEDS_INPUT = "needs-input"
    DONE = "done"
    FAILED = "failed"
    ABANDONED = "abandoned"
    DRAFTING = "drafting"
    DRAFT_BLOCKED = "draft-blocked"
    DRAFT_LOST = "draft-lost"

    @property
    def is_open(self) -> bool:
        return self not in (State.DONE, State.FAILED, State.ABANDONED)

    @property
    def has_session(self) -> bool:
        """The job's session may be alive, so the job cannot be closed or launched."""
        return self in (State.LAUNCHED, State.RUNNING, State.STALLED, State.BLOCKED)

    @property
    def is_launchable(self) -> bool:
        return self in (State.APPROVED, State.LOST, State.NEEDS_INPUT)

    @property
    def is_draftable(self) -> bool:
        """``cure-job draft`` may start a goal-writer session."""
        return self in (State.QUEUED, State.HELD, State.AWAITING_APPROVAL, State.APPROVED, State.LAUNCHED,
                        State.RUNNING, State.BLOCKED, State.STALLED, State.NEEDS_INPUT, State.LOST, State.DRAFT_LOST)


#: `claude --bg` returns before `claude agents` lists the session as live. For
#: this long after a launch or a resume, a session that is not listed, or is
#: listed stopped and was not stopped by `cure-job stop`, is not yet lost, and
#: an idle session is not yet stalled. Measured on Claude Code 2.1.300: listed
#: within 0.255 seconds. On 2.1.301 a fresh launch still read lost at once.
LAUNCH_GRACE = timedelta(seconds=DEFAULTS["launch-grace-seconds"])

_RETENTION_KEYS = {State.FAILED: "prune.failed-days"}


def retention(config: Config) -> dict[State, timedelta]:
    return {state: timedelta(days=config[key]) for state, key in _RETENTION_KEYS.items()}


RETENTION = retention(Config())

#: `prune` removes an interrupted `new`'s empty jobs/<id> or jobs/.new-* after
#: this long. An in-progress `new` owns them for milliseconds.
HALF_CREATED_AGE = timedelta(days=1)


class PredecessorGone(enum.Enum):
    """The state of an ``after`` predecessor that derives no :class:`State`."""
    #: No job directory holds a ``handoff.md`` for the id.
    MISSING = "missing"
    #: The predecessor's files do not read.
    INVALID = "invalid"


@dataclass(frozen=True)
class After:
    """The ``after`` predecessor of a job and its state."""
    id: str
    state: State | PredecessorGone
    #: The predecessor has a goal and no open draft. False when it has no readable record.
    goal: bool

    @property
    def satisfied(self) -> bool:
        return self.state is State.DONE


@dataclass(frozen=True)
class JobView:
    record: JobRecord
    state: State
    #: The holders of the resources the job names. An unsatisfied ``after`` is not among them.
    blocked_by: tuple[str, ...]
    ended_at: datetime | None
    after: After | None
    #: The draft state of an open draft, whatever the job state; ``None`` without one.
    draft: State | None = None


def needs_sessions(records: Iterable[JobRecord]) -> bool:
    """True when the state of some record depends on the session list."""
    return any((record.launches and record.result is None or record.draft_open) and is_open(record)
               for record in records)


def is_open(record: JobRecord) -> bool:
    """The job is not done, failed or abandoned. Needs no session list."""
    return _terminal_state(record) is None


def lock_rank(record: JobRecord) -> tuple[bool, str]:
    """The lock order. A launched job is already using its resources; after a
    backward clock step it can sort above a newer job (local-time ids)."""
    return (not record.launches, record.id)


def is_ready(record: JobRecord) -> bool:
    """The open job may start its first run: unlaunched, no result, and an approval of its current goal.

    The run-1 launch test, and with the ``after`` test the lock rule's test for an unlaunched job."""
    return not record.launches and record.result is None and record.approved


def holders(records: Iterable[JobRecord]) -> dict[str, str]:
    """Each held resource mapped to its holder, by the lock rule.

    ``records`` are every readable job, the ended ones included: an ``after`` needs its predecessor."""
    records = list(records)
    return _holders(records, {record.id: _terminal_state(record) for record in records})


def derive(records: Sequence[JobRecord], sessions: Mapping[str, SessionStatus], now: datetime,
           invalid_ids: AbstractSet[str], launch_grace: timedelta = LAUNCH_GRACE) -> list[JobView]:
    """One view per record, ascending id. ``sessions`` maps a session name to its status.
    ``invalid_ids`` names the jobs whose files do not read."""
    ordered = sorted(records, key=lambda record: record.id)
    # Whether a job is open needs neither sessions nor locks, and the holders
    # need the open set and the done predecessors, so the terminal states are settled first.
    terminal = {record.id: _terminal_state(record) for record in ordered}
    held = _holders(ordered, terminal)
    by_id = {record.id: record for record in ordered}
    states: dict[str, State] = {}
    blocked: dict[str, tuple[str, ...]] = {}
    drafts: dict[str, State | None] = {}
    for record in ordered:
        state = terminal[record.id]
        blocked_by: tuple[str, ...] = ()
        draft = None
        if state is None:
            blocked_by = tuple(sorted({held.get(name) for name in record.resources} - {None, record.id}))
            draft = _draft_state(record, sessions, now, launch_grace)
            state = _open_state(record, sessions, now, blocked_by, _waits(record, terminal), launch_grace, draft)
        states[record.id] = state
        blocked[record.id] = blocked_by
        drafts[record.id] = draft
    return [JobView(record, states[record.id], blocked[record.id], _ended_at(record, states[record.id]),
                    _after(record, by_id, states, invalid_ids), drafts[record.id])
            for record in ordered]


def expired(view: JobView, now: datetime, kept_for: Mapping[State, timedelta] = RETENTION) -> bool:
    """A done job expires once reported with its sessions removed, an abandoned one once its sessions are
    removed, and a job of a state in ``kept_for`` once ended for longer than its period."""
    if view.state is State.DONE:
        return view.record.reported and view.record.sessions_removed
    if view.state is State.ABANDONED:
        return view.record.sessions_removed
    kept = kept_for.get(view.state)
    return kept is not None and view.ended_at is not None and now - view.ended_at > kept


def _holders(records: Iterable[JobRecord], terminal: Mapping[str, State | None]) -> dict[str, str]:
    found: dict[str, str] = {}
    for record in sorted((record for record in records if terminal[record.id] is None), key=lock_rank):
        if record.launches:
            for name in record.resources:
                found.setdefault(name, record.id)
        elif is_ready(record) and not _waits(record, terminal) and not found.keys() & record.resources:
            found.update(dict.fromkeys(record.resources, record.id))
    return found


def _waits(record: JobRecord, terminal: Mapping[str, State | None]) -> bool:
    """The unlaunched job's ``after`` predecessor is not done. A missing or invalid one is not done."""
    after = record.handoff.after
    return after is not None and not record.launches and terminal.get(after) is not State.DONE


def _after(record: JobRecord, records: Mapping[str, JobRecord], states: Mapping[str, State],
           invalid_ids: AbstractSet[str]) -> After | None:
    after = record.handoff.after
    if after is None:
        return None
    if after in states:
        return After(after, states[after], records[after].has_goal and not records[after].draft_open)
    return After(after, PredecessorGone.INVALID if after in invalid_ids else PredecessorGone.MISSING, False)


def _terminal_state(record: JobRecord) -> State | None:
    if record.closed is not None:
        return State.ABANDONED
    if record.result is None:
        return None
    if record.result.status is ResultStatus.FAILED:
        return State.FAILED
    if record.result.status is ResultStatus.DONE and not record.result.unproven:
        return State.DONE
    return None


class _Liveness(enum.Enum):
    """What the session list and the grace say of a session that has not ended its work."""
    BUSY = "busy"
    WAITING = "waiting"
    IDLE_FRESH = "idle-fresh"
    IDLE_STALE = "idle-stale"
    STARTING = "starting"
    GONE = "gone"


_RUN_STATES = {_Liveness.BUSY: State.RUNNING, _Liveness.WAITING: State.BLOCKED, _Liveness.IDLE_FRESH: State.RUNNING,
               _Liveness.IDLE_STALE: State.STALLED, _Liveness.STARTING: State.LAUNCHED, _Liveness.GONE: State.LOST}
_DRAFT_STATES = {_Liveness.BUSY: State.DRAFTING, _Liveness.WAITING: State.DRAFT_BLOCKED,
                 _Liveness.IDLE_FRESH: State.DRAFTING, _Liveness.IDLE_STALE: State.DRAFT_LOST,
                 _Liveness.STARTING: State.DRAFTING, _Liveness.GONE: State.DRAFT_LOST}


def _liveness(status: SessionStatus | None, within_grace: bool, stop_issued: bool) -> _Liveness:
    if status is SessionStatus.BUSY:
        return _Liveness.BUSY
    # A session that waits for a permission or an answer needs the user
    # now, so no grace applies.
    if status is SessionStatus.WAITING:
        return _Liveness.WAITING
    if status is SessionStatus.IDLE:
        return _Liveness.IDLE_FRESH if within_grace else _Liveness.IDLE_STALE
    # A session can be listed without a pid while it starts or resumes.
    # After `cure-job stop`, a session listed stopped is down for good and
    # gets no grace. An unlisted session keeps the grace.
    starting = status is None or (status is SessionStatus.STOPPED and not stop_issued)
    return _Liveness.STARTING if starting and within_grace else _Liveness.GONE


def _draft_state(record: JobRecord, sessions: Mapping[str, SessionStatus], now: datetime,
                 launch_grace: timedelta) -> State | None:
    if not record.draft_open:
        return None
    draft = record.draft
    return _DRAFT_STATES[_liveness(sessions.get(draft.session), now - draft.at <= launch_grace, False)]


def _open_state(record: JobRecord, sessions: Mapping[str, SessionStatus], now: datetime,
                blocked_by: tuple[str, ...], waits: bool, launch_grace: timedelta, draft: State | None) -> State:
    run = None
    if record.launches and record.result is None:
        latest = record.launches[-1]
        run = _RUN_STATES[_liveness(sessions.get(latest.session), now - latest.at <= launch_grace,
                                    record.stop_issued)]
        if run is not State.LOST:
            return run
    if draft is not None:
        return draft
    if record.result is not None:
        return State.NEEDS_INPUT
    if run is not None:
        return run
    if blocked_by or waits:
        return State.HELD
    if not record.has_goal:
        return State.QUEUED
    return State.APPROVED if is_ready(record) else State.AWAITING_APPROVAL


def _ended_at(record: JobRecord, state: State) -> datetime | None:
    if state in (State.DONE, State.FAILED):
        return record.result_mtime
    if state is State.ABANDONED:
        return record.events_mtime
    return None
