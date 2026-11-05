"""The sessions of one job, folded from its events."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Sequence

from .events import WORK, Event, SessionStarted, SessionStopped


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
