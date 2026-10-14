"""The seven job operations.

Every operation except ``new`` and ``finish`` reads one snapshot of the state
root, derives the job states from it and makes its writes. No operation holds a
lock, so a check and its write are not atomic across processes.

A job whose stored files do not read is invalid. ``list`` shows it, ``prune``
skips it, and ``launch``, ``claim`` and ``close`` refuse it by id. Its resources
and its launched events are unknown, so it may hold any resource whatever its
id: ``launch`` and ``claim`` of every other job refuse while it exists.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import NamedTuple, Sequence

from ..claude import Claude
from ..clock import Clock
from ..errors import (ClaudeError, ClaudeOutcomeUnknown, HandoffError, JobStateError, ResourceHeld, StoreError,
                      UnknownJob)
from ..events import Claim, Closed, Launched
from ..goal import PLUGIN_ROOT, retarget
from ..handoff import parse_handoff, stamp
from ..job_id import make_id, session_name
from ..result import Report, render_result
from ..state import HALF_CREATED_AGE, JobView, State, derive, expired, holders, lock_rank, needs_sessions
from ..store import InvalidJob, JobStore


class Listing(NamedTuple):
    views: list[JobView]
    invalid: list[InvalidJob]


class JobsProvider:
    def __init__(self, store: JobStore, claude: Claude, clock: Clock, plugin_root: Path = PLUGIN_ROOT):
        self.store = store
        self.claude = claude
        self.clock = clock
        self.plugin_root = plugin_root

    def new(self, text: str, slug: str) -> str:
        """Queue the handoff ``text`` as a new job and return the job id."""
        handoff = parse_handoff(text)
        created = self.clock()
        try:
            base = make_id(created, os.path.basename(handoff.launch_dir), slug)
        except ValueError as e:
            raise HandoffError(f"cannot build a job id: {e}") from e
        return self.store.create(base, lambda job_id: stamp(text, job_id, created))

    def views(self) -> list[JobView]:
        return self.listing().views

    def listing(self) -> Listing:
        """The views of the readable jobs and the invalid jobs, from one snapshot."""
        snapshot = self.store.snapshot()
        # The session list costs one run of the binary, so it is read only
        # when the state of some job depends on it.
        sessions = self.claude.sessions() if needs_sessions(snapshot.records) else {}
        return Listing(derive(snapshot.records, sessions, self.clock()), snapshot.invalid)

    def launch(self, job_id: str, claude_args: Sequence[str] = ()) -> str:
        """Start the next run of ``job_id`` and return the session name."""
        listing = self.listing()
        view = self._find(listing, job_id)
        record = view.record
        if not view.state.is_launchable:
            raise JobStateError(f"job {job_id} is {view.state.value}; launch needs "
                                + ", ".join(state.value for state in State if state.is_launchable))
        goal = self.store.goal_path(job_id)
        if not record.has_goal:
            raise JobStateError(f"job {job_id} has no goal file: {goal} does not exist")
        if view.blocked_by:
            held = _holders(listing.views)
            name = next(name for name in sorted(record.resources) if held[name] != job_id)
            raise ResourceHeld(name, held[name])
        _refuse_invalid(listing, "launch")
        self.store.rewrite_goal(job_id, lambda text: retarget(text, self.plugin_root))
        # result-<run>.md takes the number of the run that wrote it.
        archived = self.store.archive_result(job_id, record.run)
        run = record.run + 1
        session = session_name(job_id, run)
        unknown = None
        try:
            self.claude.start(session, record.handoff.launch_dir, f"/goal @{goal}", claude_args)
        except ClaudeOutcomeUnknown as e:
            # The session may exist. Recorded, it derives launched, then
            # running or lost, and the lock rule covers it.
            unknown = e
        except ClaudeError:
            # Put result.md back, so a retry sees the same state and uses the
            # same run number and session name.
            if archived:
                self.store.restore_result(job_id, record.run)
            raise
        try:
            self.store.append_event(job_id, Launched(run, session, self.clock()))
        except StoreError as e:
            raise StoreError(f"job {job_id}: session {session} may be running and is not recorded; "
                             f"stop it before a retry: {e}") from e
        if unknown is not None:
            raise ClaudeOutcomeUnknown(f"{unknown}; recorded as run {run}, session {session}: "
                                       "list shows it launched, then running or lost") from unknown
        return session

    def claim(self, job_id: str, resource: str) -> None:
        """Add ``resource`` to the resources ``job_id`` names. Returns when the job holds it."""
        listing = self.listing()
        view = self._find(listing, job_id)
        if not view.state.is_open:
            raise JobStateError(f"job {job_id} is {view.state.value}; claim needs an open job")
        open_records = {other.record.id: other.record for other in listing.views if other.state.is_open}
        holder = holders(open_records.values()).get(resource)
        if holder not in (None, job_id):
            other = open_records[holder]
            # A launched holder keeps the resource even against a lower id.
            if other.launches or lock_rank(other) < lock_rank(view.record):
                raise ResourceHeld(resource, holder)
        _refuse_invalid(listing, "claim")
        if resource not in view.record.resources:
            self.store.append_event(job_id, Claim(resource))

    def close(self, job_id: str, reason: str = "") -> None:
        """Abandon ``job_id``. A job with a session must be stopped first."""
        view = self._find(self.listing(), job_id)
        if view.state.has_session:
            raise JobStateError(f"job {job_id} is {view.state.value}; stop session "
                                f"{view.record.session} first")
        if not view.state.is_open:
            raise JobStateError(f"job {job_id} is {view.state.value}; close needs an open job")
        self.store.append_event(job_id, Closed(reason))

    def finish(self, job_id: str, report: Report) -> Path:
        """Write ``report`` as the ``result.md`` of a launched job and return its path.

        Reads only this job: no session list, no other job's files, no clock.
        """
        record = self.store.load(job_id)
        path = self.store.result_path(job_id)
        # The order of derive: closed, then result.md, then launched.
        if record.closed is not None:
            raise JobStateError(f"job {job_id} is abandoned; finish needs an open launched job")
        if record.result is not None:
            raise JobStateError(f"job {job_id} already has {path}")
        if not record.launches:
            raise JobStateError(f"job {job_id} has no launched event; finish needs a launched job")
        if not self.store.write_result(job_id, render_result(report)):
            raise JobStateError(f"job {job_id} already has {path}")
        return path

    def prune_half_created(self) -> list[Path]:
        """Remove the directories an interrupted ``new`` left, after one day. Return their paths."""
        now = self.clock()
        return [entry.path for entry in self.store.half_created()
                if now - entry.mtime > HALF_CREATED_AGE and self.store.remove_half_created(entry)]

    def prune(self) -> list[str]:
        """Remove every job past its retention period and return the removed ids."""
        now = self.clock()
        removed = []
        for view in self.views():
            if expired(view, now):
                self.store.remove(view.record.id)
                removed.append(view.record.id)
        return removed

    def _find(self, listing: Listing, job_id: str) -> JobView:
        for view in listing.views:
            if view.record.id == job_id:
                return view
        for invalid in listing.invalid:
            if invalid.id == job_id:
                raise StoreError(f"job {job_id} is invalid: {invalid.problem}")
        raise UnknownJob(f"unknown job {job_id}: {self.store.job_dir(job_id)} holds no handoff.md")


def _holders(views: list[JobView]) -> dict[str, str]:
    return holders(view.record for view in views if view.state.is_open)


def _refuse_invalid(listing: Listing, operation: str) -> None:
    if listing.invalid:
        invalid = listing.invalid[0]
        raise StoreError(f"{operation} refused: job {invalid.id} is invalid and may hold any resource; "
                         f"fix or remove {invalid.dir}: {invalid.problem}")
