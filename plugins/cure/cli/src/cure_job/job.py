"""What one job directory holds, as read in one pass."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from . import resource
from .events import (Approved, Claim, Closed, DraftEnded, DraftMode, DraftStarted, Event, Launched, Origin, Release,
                     Reported, SessionsRemoved, StopIssued)
from .handoff import Handoff
from .result import Result, ResultStatus


def answers_name(n: int) -> str:
    """The file in the job directory that holds the answers draft ``n`` applies."""
    return f"answers-{n}.md"


def draft_session_name(job_id: str, n: int) -> str:
    return f"draft-{job_id}-{n}"


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
    def draft(self) -> DraftStarted | None:
        """The latest draft."""
        return next((event for event in reversed(self.events) if isinstance(event, DraftStarted)), None)

    @property
    def draft_end(self) -> DraftEnded | None:
        """The end of the latest draft, or ``None`` while it is open."""
        draft = self.draft
        if draft is None:
            return None
        return next((event for event in self.events if isinstance(event, DraftEnded) and event.n == draft.n), None)

    @property
    def draft_open(self) -> bool:
        """A draft started and ``cure-job drafted`` has not ended it."""
        return self.draft is not None and self.draft_end is None

    @property
    def drafts_unended(self) -> int:
        """The drafts started since the last ``cure-job drafted``."""
        count = 0
        for event in self.events:
            if isinstance(event, DraftStarted):
                count += 1
            elif isinstance(event, DraftEnded):
                count = 0
        return count

    @property
    def answers_applied(self) -> bool:
        """An apply draft that started after the needs-input result was recorded has ended."""
        if self.result is None or self.result.status is not ResultStatus.NEEDS_INPUT or self.result_mtime is None:
            return False
        ended = {event.n for event in self.events if isinstance(event, DraftEnded)}
        return any(isinstance(event, DraftStarted) and event.mode is DraftMode.APPLY and event.n in ended
                   and event.at > self.result_mtime for event in self.events)

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
