"""What one job directory holds, as read in one pass."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .events import Claim, Closed, Event, Launched, Origin, Reported
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
    def reported(self) -> bool:
        """The origin session was told of the latest run's result."""
        return self.run > 0 and any(isinstance(event, Reported) and event.run == self.run for event in self.events)

    @property
    def closed(self) -> Closed | None:
        return next((event for event in self.events if isinstance(event, Closed)), None)

    @property
    def origin(self) -> str | None:
        """The latest origin event's address, else the handoff's ``origin``."""
        origins = [event for event in self.events if isinstance(event, Origin)]
        return origins[-1].address if origins else self.handoff.origin

    @property
    def resources(self) -> frozenset[str]:
        claimed = {event.resource for event in self.events if isinstance(event, Claim)}
        return self.handoff.resources | claimed
