"""What one job directory holds, as read in one pass."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import resource
from .events import Claim, Closed, Event, Launched, Origin, Release, Reported, SessionsRemoved, StopIssued
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
    def stop_issued(self) -> bool:
        """``cure-job stop`` ran for the latest run."""
        return self.run > 0 and any(isinstance(event, StopIssued) and event.run == self.run for event in self.events)

    @property
    def sessions_removed(self) -> bool:
        """``cure-job remove-sessions`` left no session of the job listed."""
        return any(isinstance(event, SessionsRemoved) for event in self.events)

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
        """The handoff's repositories, every repository claim, and each short hold claimed and
        not released in the latest run while it has no result. A claim without a run counts for
        the whole job."""
        names = set(self.handoff.resources)
        for event in self.events:
            if isinstance(event, Claim) and self._claim_counts(event):
                names.add(event.resource)
            elif isinstance(event, Release) and resource.is_short_hold(event.resource):
                names.discard(event.resource)
        return frozenset(names)

    def _claim_counts(self, claim: Claim) -> bool:
        if claim.run is None or not resource.is_short_hold(claim.resource):
            return True
        return claim.run == self.run and self.result is None
