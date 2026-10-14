"""The seven job operations.

Every operation except ``new`` and ``finish`` reads one snapshot of the state
root, derives the job states from it and makes its writes. No operation holds a
lock, so a check and its write are not atomic across processes.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Sequence

from ..claude import Claude
from ..clock import Clock
from ..errors import ClaudeError, HandoffError, JobStateError, ResourceHeld, StoreError, UnknownJob
from ..events import Claim, Closed, Launched
from ..handoff import parse_handoff, stamp
from ..job_id import make_id, session_name
from ..result import Report, render_result
from ..state import HALF_CREATED_AGE, JobView, State, derive, expired, needs_sessions
from ..store import JobStore

_LAUNCHABLE = (State.AWAITING_APPROVAL, State.LOST, State.NEEDS_INPUT)
_HAS_SESSION = (State.LAUNCHED, State.RUNNING)


class JobsProvider:
    def __init__(self, store: JobStore, claude: Claude, clock: Clock):
        self.store = store
        self.claude = claude
        self.clock = clock

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
        records = self.store.load_all()
        # The session list costs one run of the binary, so it is read only
        # when the state of some job depends on it.
        sessions = self.claude.sessions() if needs_sessions(records) else {}
        return derive(records, sessions, self.clock())

    def launch(self, job_id: str, claude_args: Sequence[str] = ()) -> str:
        """Start the next run of ``job_id`` and return the session name."""
        views = self.views()
        view = self._find(views, job_id)
        record = view.record
        if view.state not in _LAUNCHABLE:
            raise JobStateError(f"job {job_id} is {view.state.value}; launch needs "
                                + ", ".join(state.value for state in _LAUNCHABLE))
        goal = self.store.goal_path(job_id)
        if not record.has_goal:
            raise JobStateError(f"job {job_id} has no goal file: {goal} does not exist")
        for name in sorted(record.resources):
            holder = _holder(views, job_id, name)
            if holder is not None:
                raise ResourceHeld(name, holder)
        # result-<run>.md takes the number of the run that wrote it.
        archived = self.store.archive_result(job_id, record.run)
        run = record.run + 1
        session = session_name(job_id, run)
        try:
            self.claude.start(session, record.handoff.launch_dir, f"/goal @{goal}", claude_args)
        except ClaudeError:
            # Put result.md back, so a retry sees the same state and uses the
            # same run number and session name.
            if archived:
                self.store.restore_result(job_id, record.run)
            raise
        try:
            self.store.append_event(job_id, Launched(run, session, self.clock()))
        except StoreError as e:
            raise StoreError(f"job {job_id}: session {session} is started but not recorded; "
                             f"stop it before a retry: {e}") from e
        return session

    def claim(self, job_id: str, resource: str) -> None:
        """Add ``resource`` to the resources ``job_id`` names. Returns when the job holds it."""
        views = self.views()
        view = self._find(views, job_id)
        if not view.state.is_open:
            raise JobStateError(f"job {job_id} is {view.state.value}; claim needs an open job")
        holder = _holder(views, job_id, resource)
        if holder is not None:
            raise ResourceHeld(resource, holder)
        if resource not in view.record.resources:
            self.store.append_event(job_id, Claim(resource))

    def close(self, job_id: str, reason: str = "") -> None:
        """Abandon ``job_id``. A job with a session must be stopped first."""
        view = self._find(self.views(), job_id)
        if view.state in _HAS_SESSION:
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

    def _find(self, views: list[JobView], job_id: str) -> JobView:
        for view in views:
            if view.record.id == job_id:
                return view
        raise UnknownJob(f"unknown job {job_id}: {self.store.job_dir(job_id)} holds no handoff.md")


def _holder(views: list[JobView], job_id: str, resource: str) -> str | None:
    """Another open job that holds ``resource`` against ``job_id``: one with a lower id, or one with
    a launched event, whatever its id. ``views`` is in ascending id order."""
    for view in views:
        other = view.record
        if other.id == job_id or not view.state.is_open or resource not in other.resources:
            continue
        # A launched job is already using the resource. After a backward
        # clock step it can sort above a newer job (local-time ids).
        if other.id < job_id or other.launches:
            return other.id
    return None
