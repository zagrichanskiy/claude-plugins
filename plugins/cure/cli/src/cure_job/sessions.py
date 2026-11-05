"""The sessions of one job, folded from its events."""
from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Sequence

from .claude import Session, SessionStatus
from .events import WORK, Event, SessionStarted, SessionStopped


class Liveness(enum.Enum):
    STARTING = "starting"
    BUSY = "busy"
    WAITING = "waiting"
    #: Idle within the launch grace.
    IDLE = "idle"
    STALLED = "stalled"
    GONE = "gone"
    ENDED = "ended"

    @property
    def is_live(self) -> bool:
        return self not in (Liveness.GONE, Liveness.ENDED)


@dataclass(frozen=True)
class JobSession:
    kind: str
    n: int
    name: str
    #: The work run current at the start; ``n`` for a work session.
    run: int
    started_at: datetime
    inputs: tuple[str, ...]
    ended: bool
    summary: tuple[str, ...]
    #: ``cure-job stop`` ran for this session. The launch grace no longer applies to it.
    stop_recorded: bool


def fold(events: Sequence[Event], has_result: bool) -> tuple[JobSession, ...]:
    """Every session the events start, in start order.

    A work session ends when a later work session starts, or when it is the latest and ``result.md``
    exists (``has_result``). A session of any other kind has no end yet."""
    starts = [event for event in events if isinstance(event, SessionStarted)]
    stops = {(event.kind, event.n) for event in events if isinstance(event, SessionStopped)}
    last_work = max((index for index, start in enumerate(starts) if start.kind == WORK), default=None)
    return tuple(
        JobSession(kind=start.kind, n=start.n, name=start.session, run=start.run, started_at=start.at,
                   inputs=start.inputs, ended=start.kind == WORK and (index != last_work or has_result),
                   summary=(), stop_recorded=(start.kind, start.n) in stops)
        for index, start in enumerate(starts))


def listed_live(listed: Session | None) -> bool:
    """The listing has a live entry for the session."""
    return listed is not None and listed.status is not SessionStatus.STOPPED


def liveness(session: JobSession, listed: Session | None, now: datetime, grace: timedelta) -> Liveness:
    """The liveness of ``session``, listed as ``listed`` at ``now``. ``grace`` follows its start."""
    if session.ended:
        return Liveness.ENDED
    status = listed.status if listed is not None else None
    within_grace = now - session.started_at <= grace
    if status is SessionStatus.BUSY:
        return Liveness.BUSY
    # A session that waits for a permission or an answer needs the user now, so no grace applies.
    if status is SessionStatus.WAITING:
        return Liveness.WAITING
    if status is SessionStatus.IDLE:
        return Liveness.IDLE if within_grace else Liveness.STALLED
    # A session can be listed without a pid while it starts or resumes. After `cure-job stop`, a
    # session listed stopped is down for good and gets no grace. An unlisted session keeps the grace.
    starting = status is None or (status is SessionStatus.STOPPED and not session.stop_recorded)
    return Liveness.STARTING if starting and within_grace else Liveness.GONE
