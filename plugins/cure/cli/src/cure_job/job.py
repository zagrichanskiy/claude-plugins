"""What one job directory holds, as read in one pass."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from functools import cached_property
from pathlib import Path

from . import resource
from .events import WORK, Approved, Claim, Closed, Event, Origin, Release, Reported, SessionsRemoved
from .handoff import Handoff
from .result import Result
from .sessions import JobSession, fold


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

    @cached_property
    def sessions(self) -> tuple[JobSession, ...]:
        return fold(self.events, self.result is not None)

    def latest(self, kind: str) -> JobSession | None:
        return next((session for session in reversed(self.sessions) if session.kind == kind), None)

    def open_sessions(self) -> tuple[JobSession, ...]:
        """The latest session of each kind, where it has not ended."""
        latest = {session.kind: session for session in self.sessions}
        return tuple(session for session in latest.values() if not session.ended)

    def restarts(self, kind: str) -> int:
        """The starts of ``kind`` that followed a session of ``kind`` that had not ended."""
        tail = 0
        for session in self.sessions:
            if session.kind == kind:
                tail = 0 if session.ended else tail + 1
        return max(tail - 1, 0)

    @property
    def run(self) -> int:
        """The number of work sessions."""
        return sum(1 for session in self.sessions if session.kind == WORK)

    @property
    def session(self) -> str | None:
        latest = self.latest(WORK)
        return latest.name if latest is not None else None

    @property
    def session_names(self) -> tuple[str, ...]:
        """The name of every session of every kind, in first-seen order, without repeats.

        A resumed run records the session of the run before it, so a name can repeat."""
        return tuple(dict.fromkeys(session.name for session in self.sessions))

    @property
    def reported(self) -> bool:
        """The origin session was told of the latest run's result."""
        return self.run > 0 and any(isinstance(event, Reported) and event.run == self.run for event in self.events)

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
