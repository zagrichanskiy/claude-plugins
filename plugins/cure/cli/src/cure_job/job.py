"""What one job directory holds, as read in one pass."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .events import Claim, Closed, Event, Launched
from .handoff import Handoff
from .result import Result


@dataclass(frozen=True)
class JobRecord:
    id: str
    dir: Path
    handoff: Handoff
    has_goal: bool
    events: tuple[Event, ...]
    result: Result | None
    result_mtime: datetime | None
    events_mtime: datetime | None

    @property
    def launches(self) -> tuple[Launched, ...]:
        return tuple(event for event in self.events if isinstance(event, Launched))

    @property
    def run(self) -> int:
        return len(self.launches)

    @property
    def session(self) -> str | None:
        launches = self.launches
        return launches[-1].session if launches else None

    @property
    def closed(self) -> Closed | None:
        return next((event for event in self.events if isinstance(event, Closed)), None)

    @property
    def resources(self) -> frozenset[str]:
        claimed = {event.resource for event in self.events if isinstance(event, Claim)}
        return self.handoff.resources | claimed
