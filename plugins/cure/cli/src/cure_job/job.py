"""What one job directory holds, as read in one pass."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import resource
from .events import Approved, Claim, Closed, Event, Launched, Origin, Release, Reported, SessionsRemoved, StopIssued
from .handoff import Handoff
from .result import Result


@dataclass(frozen=True)
class JobRecord:
    id: str
    dir: Path
    handoff: Handoff
    #: The digest of ``goal.md`` as read, or ``None`` when it does not exist.
    goal_digest: str | None
    events: tuple[Event, ...]
    result: Result | None
    result_mtime: datetime | None
    events_mtime: datetime | None
    #: The run numbers of the ``result-<run>.md`` files.
    archived_runs: frozenset[int] = frozenset()
    #: The ``## Open`` items of ``goal.md`` as read with ``goal_digest``; 0 without a goal.
    open_items: int = 0

    @property
    def has_goal(self) -> bool:
        return self.goal_digest is not None

    @property
    def approved(self) -> bool:
        """An ``approved`` event names the digest of the current ``goal.md``."""
        return self.has_goal and any(isinstance(event, Approved) and event.goal == self.goal_digest
                                     for event in self.events)

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
        """The handoff's resources, held to job end, and the claimed ones. A short-hold claim
        counts while its run is the latest and has no result, current or archived, until a
        release. A claim without a run counts for the whole job."""
        claimed: set[str] = set()
        for event in self.events:
            if isinstance(event, Claim) and self._claim_counts(event):
                claimed.add(event.resource)
            elif isinstance(event, Release) and resource.is_short_hold(event.resource):
                claimed.discard(event.resource)
        return self.handoff.resources | claimed

    def _claim_counts(self, claim: Claim) -> bool:
        if claim.run is None or not resource.is_short_hold(claim.resource):
            return True
        # A relaunch archives result.md before it records the next run.
        return claim.run == self.run and self.result is None and claim.run not in self.archived_runs
