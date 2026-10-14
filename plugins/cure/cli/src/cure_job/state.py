"""Job states, derived and never stored.

This module holds the States table, the lock rule and the retention rule. No
lock file exists: the holder of a resource is the first open job in lock order
among those that name it. Lock order puts a job with a launched event first,
then ascending id.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Iterable, Mapping, Sequence

from .job import JobRecord
from .result import ResultStatus


class State(enum.Enum):
    QUEUED = "queued"
    HELD = "held"
    AWAITING_APPROVAL = "awaiting-approval"
    LAUNCHED = "launched"
    RUNNING = "running"
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
        return self in (State.LAUNCHED, State.RUNNING)

    @property
    def is_launchable(self) -> bool:
        return self in (State.AWAITING_APPROVAL, State.LOST, State.NEEDS_INPUT)


#: `claude --bg` returns before `claude agents` lists the session. For this
#: long after a launch, a session that is not listed is not yet lost.
LAUNCH_GRACE = timedelta(seconds=60)

RETENTION = {
    State.DONE: timedelta(days=14),
    State.FAILED: timedelta(days=30),
    State.ABANDONED: timedelta(days=30),
}

#: `prune` removes an interrupted `new`'s empty jobs/<id> or jobs/.new-* after
#: this long. An in-progress `new` owns them for milliseconds.
HALF_CREATED_AGE = timedelta(days=1)


@dataclass(frozen=True)
class JobView:
    record: JobRecord
    state: State
    blocked_by: tuple[str, ...]
    ended_at: datetime | None


def needs_sessions(records: Iterable[JobRecord]) -> bool:
    """True when the state of some record depends on the session list."""
    return any(record.launches and record.result is None and record.closed is None for record in records)


def lock_rank(record: JobRecord) -> tuple[bool, str]:
    """The lock order. A launched job is already using its resources; after a
    backward clock step it can sort above a newer job (local-time ids)."""
    return (not record.launches, record.id)


def holders(open_records: Iterable[JobRecord]) -> dict[str, str]:
    """Each resource an open job names, mapped to its holder: the first of the
    jobs that name it in lock order."""
    found: dict[str, str] = {}
    for record in sorted(open_records, key=lock_rank):
        for name in record.resources:
            found.setdefault(name, record.id)
    return found


def derive(records: Sequence[JobRecord], sessions: Mapping[str, bool], now: datetime) -> list[JobView]:
    """One view per record, ascending id. ``sessions`` maps a session name to alive."""
    ordered = sorted(records, key=lambda record: record.id)
    # Whether a job is open needs neither sessions nor locks, and the holders
    # need the open set, so the terminal states are settled first.
    terminal = {record.id: _terminal_state(record) for record in ordered}
    held = holders(record for record in ordered if terminal[record.id] is None)
    views = []
    for record in ordered:
        state = terminal[record.id]
        blocked_by: tuple[str, ...] = ()
        if state is None:
            blocked_by = tuple(sorted({held[name] for name in record.resources} - {record.id}))
            state = _open_state(record, sessions, now, blocked_by)
        views.append(JobView(record, state, blocked_by, _ended_at(record, state)))
    return views


def expired(view: JobView, now: datetime) -> bool:
    kept = RETENTION.get(view.state)
    return kept is not None and view.ended_at is not None and now - view.ended_at > kept


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


def _open_state(record: JobRecord, sessions: Mapping[str, bool], now: datetime,
                blocked_by: tuple[str, ...]) -> State:
    if record.result is not None:
        return State.NEEDS_INPUT
    launches = record.launches
    if launches:
        latest = launches[-1]
        alive = sessions.get(latest.session)
        if alive:
            return State.RUNNING
        if alive is None and now - latest.at <= LAUNCH_GRACE:
            return State.LAUNCHED
        return State.LOST
    if record.has_goal:
        return State.AWAITING_APPROVAL
    return State.HELD if blocked_by else State.QUEUED


def _ended_at(record: JobRecord, state: State) -> datetime | None:
    if state in (State.DONE, State.FAILED):
        return record.result_mtime
    if state is State.ABANDONED:
        return record.events_mtime
    return None
