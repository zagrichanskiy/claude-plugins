"""Job states, derived and never stored.

This module holds the States table, the lock rule and the retention rule. No
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

from .claude import Session
from .config import DEFAULTS, Config
from .events import WORK
from .job import JobRecord
from .result import ResultStatus
from .sessions import JobSession, Liveness, liveness


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


class Phase(enum.Enum):
    """Where a job stands, from its files and events alone."""
    QUEUED = "queued"
    AWAITING_APPROVAL = "awaiting-approval"
    APPROVED = "approved"
    WORKING = "working"
    NEEDS_INPUT = "needs-input"
    DONE = "done"
    FAILED = "failed"
    ABANDONED = "abandoned"

    @property
    def is_terminal(self) -> bool:
        return self in (Phase.DONE, Phase.FAILED, Phase.ABANDONED)


_PRE_LAUNCH = (Phase.QUEUED, Phase.AWAITING_APPROVAL, Phase.APPROVED)

_WORKING_STATES = {Liveness.STARTING: State.LAUNCHED, Liveness.BUSY: State.RUNNING, Liveness.IDLE: State.RUNNING,
                   Liveness.WAITING: State.BLOCKED, Liveness.STALLED: State.STALLED, Liveness.GONE: State.LOST}


def phase_of(record: JobRecord) -> Phase:
    if record.closed is not None:
        return Phase.ABANDONED
    if record.result is not None:
        if record.result.status is ResultStatus.FAILED:
            return Phase.FAILED
        if record.result.status is ResultStatus.DONE and not record.result.unproven:
            return Phase.DONE
        return Phase.NEEDS_INPUT
    if record.run > 0:
        return Phase.WORKING
    if not record.has_goal:
        return Phase.QUEUED
    return Phase.APPROVED if record.approved else Phase.AWAITING_APPROVAL


def project(phase: Phase, held: bool, work: Liveness | None) -> State:
    """The ``list --json`` state: the work liveness in ``WORKING``, ``held`` before a launch, else the phase."""
    if phase is Phase.WORKING:
        if work is None or work is Liveness.ENDED:
            raise AssertionError(f"a working job has work liveness {work}")
        return _WORKING_STATES[work]
    if held and phase in _PRE_LAUNCH:
        return State.HELD
    return State(phase.value)


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
    #: The predecessor has a goal. False when it has no readable record.
    goal: bool

    @property
    def satisfied(self) -> bool:
        return self.state is State.DONE


@dataclass(frozen=True)
class SessionView:
    session: JobSession
    #: ``None`` when the job's phase is done, failed or abandoned.
    liveness: Liveness | None
    #: The listed ``waitingFor`` of a waiting session.
    waiting_for: str | None


@dataclass(frozen=True)
class JobView:
    record: JobRecord
    phase: Phase
    #: The latest session of each kind.
    sessions: Mapping[str, SessionView]
    #: The holders of the resources the job names. An unsatisfied ``after`` is not among them.
    blocked_by: tuple[str, ...]
    #: Another job holds a resource the job names, or the job's ``after`` predecessor is not done.
    held: bool
    after: After | None
    ended_at: datetime | None

    @property
    def state(self) -> State:
        work = self.sessions.get(WORK)
        return project(self.phase, self.held, work.liveness if work is not None else None)


def needs_sessions(records: Iterable[JobRecord]) -> bool:
    """True when the view of some record depends on the session list."""
    return any(record.open_sessions() and not phase_of(record).is_terminal for record in records)


def is_open(record: JobRecord) -> bool:
    """The job is not done, failed or abandoned. Needs no session list."""
    return not phase_of(record).is_terminal


def lock_rank(record: JobRecord) -> tuple[bool, str]:
    """The lock order. A launched job is already using its resources; after a
    backward clock step it can sort above a newer job (local-time ids)."""
    return (record.run == 0, record.id)


def is_ready(record: JobRecord) -> bool:
    """The open job may start its first run: unlaunched, no result, and an approval of its current goal.

    The run-1 launch test, and with the ``after`` test the lock rule's test for an unlaunched job."""
    return record.run == 0 and record.result is None and record.approved


def holders(records: Iterable[JobRecord]) -> dict[str, str]:
    """Each held resource mapped to its holder, by the lock rule.

    ``records`` are every readable job, the ended ones included: an ``after`` needs its predecessor."""
    records = list(records)
    return _holders(records, {record.id: _terminal_state(record) for record in records})


def derive(records: Sequence[JobRecord], sessions: Mapping[str, Session], now: datetime,
           invalid_ids: AbstractSet[str], launch_grace: timedelta = LAUNCH_GRACE) -> list[JobView]:
    """One view per record, ascending id. ``sessions`` maps a session name to its listing.
    ``invalid_ids`` names the jobs whose files do not read."""
    ordered = sorted(records, key=lambda record: record.id)
    # Whether a job is open needs neither sessions nor locks, and the holders
    # need the open set and the done predecessors, so the terminal states are settled first.
    terminal = {record.id: _terminal_state(record) for record in ordered}
    holding = _holders(ordered, terminal)
    by_id = {record.id: record for record in ordered}
    parts: dict[str, tuple[Phase, dict[str, SessionView], tuple[str, ...], bool]] = {}
    states: dict[str, State] = {}
    for record in ordered:
        phase = phase_of(record)
        views = _session_views(record, phase, sessions, now, launch_grace)
        blocked_by: tuple[str, ...] = ()
        held = False
        if not phase.is_terminal:
            blocked_by = tuple(sorted({holding.get(name) for name in record.resources} - {None, record.id}))
            held = bool(blocked_by) or _waits(record, terminal)
        parts[record.id] = (phase, views, blocked_by, held)
        work = views.get(WORK)
        states[record.id] = project(phase, held, work.liveness if work is not None else None)
    return [JobView(record, *parts[record.id], _after(record, by_id, states, invalid_ids),
                    _ended_at(record, states[record.id]))
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
        if record.run > 0:
            for name in record.resources:
                found.setdefault(name, record.id)
        elif is_ready(record) and not _waits(record, terminal) and not found.keys() & record.resources:
            found.update(dict.fromkeys(record.resources, record.id))
    return found


def _waits(record: JobRecord, terminal: Mapping[str, State | None]) -> bool:
    """The unlaunched job's ``after`` predecessor is not done. A missing or invalid one is not done."""
    after = record.handoff.after
    return after is not None and record.run == 0 and terminal.get(after) is not State.DONE


def _after(record: JobRecord, records: Mapping[str, JobRecord], states: Mapping[str, State],
           invalid_ids: AbstractSet[str]) -> After | None:
    after = record.handoff.after
    if after is None:
        return None
    if after in states:
        return After(after, states[after], records[after].has_goal)
    return After(after, PredecessorGone.INVALID if after in invalid_ids else PredecessorGone.MISSING, False)


def _terminal_state(record: JobRecord) -> State | None:
    phase = phase_of(record)
    return State(phase.value) if phase.is_terminal else None


def _session_views(record: JobRecord, phase: Phase, sessions: Mapping[str, Session], now: datetime,
                   grace: timedelta) -> dict[str, SessionView]:
    found: dict[str, SessionView] = {}
    for session in {session.kind: session for session in record.sessions}.values():
        listed = sessions.get(session.name)
        state = None if phase.is_terminal else liveness(session, listed, now, grace)
        waiting_for = listed.waiting_for if state is Liveness.WAITING and listed is not None else None
        found[session.kind] = SessionView(session, state, waiting_for)
    return found


def _ended_at(record: JobRecord, state: State) -> datetime | None:
    if state in (State.DONE, State.FAILED):
        return record.result_mtime
    if state is State.ABANDONED:
        return record.events_mtime
    return None
