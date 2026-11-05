"""The fourteen job operations.

Every operation except ``new``, ``approve``, ``finish``, ``reported`` and ``release``
reads one snapshot of the state root, derives the job states from it and makes its
writes. ``approve``, ``finish``, ``reported`` and ``release`` read only their own job.
``claim`` runs its check and its write under :meth:`JobStore.locked` and reads
no session list. No other operation holds the lock, so their check and write
are not atomic across processes.

A job whose stored files do not read is invalid. ``list`` shows it, ``prune``
skips it, and every other operation refuses it by id. Its resources and its
launched events are unknown, so it may hold any resource whatever its id:
``launch``, ``resume`` and ``claim`` of every other job refuse while it exists.
The other operations name no resource, so they do not.
"""
from __future__ import annotations

import functools
import os
import time
from datetime import timedelta
from pathlib import Path
from typing import Callable, Mapping, NamedTuple, NoReturn, Sequence

from .. import resource as resource_names
from ..claude import Claude, Session
from ..clock import Clock
from ..config import Config
from ..errors import CureJobError, HandoffError, JobStateError, ResourceHeld, StoreError, UnknownJob
from ..events import Approved, Claim, Closed, Origin, Release, Reported
from ..goal import PLUGIN_ROOT
from ..handoff import parse_submitted, stamp
from ..job_id import make_id
from ..result import Report, render_result
from ..job import JobRecord
from ..kinds import KINDS, SessionKind
from ..kinds import WORK as WORK_KIND
from ..rules import Check, Op, check
from ..runner import Continuation, SessionRunner, Stopped
from ..state import HALF_CREATED_AGE, JobView, derive, expired, holders, is_open, lock_rank, needs_sessions, retention
from ..store import InvalidJob, JobStore, Snapshot


class Listing(NamedTuple):
    views: list[JobView]
    invalid: list[InvalidJob]


#: The longest ``claim --wait`` fits one foreground Bash call under its 600 s
#: cap. A waiting claim polls the store this often.
CLAIM_WAIT_MAX_SECONDS = 540
CLAIM_POLL_SECONDS = 10.0


class JobsProvider:
    def __init__(self, store: JobStore, claude: Claude, clock: Clock, plugin_root: Path = PLUGIN_ROOT,
                 sleep: Callable[[float], None] = time.sleep, monotonic: Callable[[], float] = time.monotonic,
                 config: Config = Config()):
        self.store = store
        self.config = config
        self.claude = claude
        self.clock = clock
        # The wait of ``claim --wait``; a test passes a fake pair so that it never waits.
        self.sleep = sleep
        self.monotonic = monotonic
        self.runner = SessionRunner(store, claude, clock, plugin_root, sleep, monotonic)

    def new(self, text: str, slug: str, origin: str | None = None, ticket_summary: str | None = None) -> str:
        """Queue the handoff ``text`` as a new job reporting back to ``origin`` and return the job id.
        ``ticket_summary``, when given, replaces the handoff's ``ticket-summary``."""
        handoff = parse_submitted(text)
        if handoff.after is not None:
            snapshot = self.store.snapshot()
            if handoff.after not in {job.id for job in [*snapshot.records, *snapshot.invalid]}:
                raise UnknownJob(f"after: unknown job {handoff.after}: "
                                 f"{self.store.job_dir(handoff.after)} holds no handoff.md")
        created = self.clock()
        try:
            base = make_id(created, os.path.basename(handoff.launch_dir), slug)
        except ValueError as e:
            raise HandoffError(f"cannot build a job id: {e}") from e
        return self.store.create(base, lambda job_id: stamp(text, job_id, created, origin, ticket_summary))

    def views(self) -> list[JobView]:
        return self.listing().views

    def listing(self) -> Listing:
        """The views of the readable jobs and the invalid jobs, from one snapshot."""
        snapshot = self.store.snapshot()
        # The session list costs one run of the binary, so it is read only
        # when the state of some job depends on it.
        sessions = self.claude.sessions() if needs_sessions(snapshot.records) else {}
        return self._listing(snapshot, sessions)

    def _listing(self, snapshot: Snapshot, sessions: Mapping[str, Session]) -> Listing:
        invalid_ids = {job.id for job in snapshot.invalid}
        return Listing(derive(snapshot.records, sessions, self.clock(), invalid_ids,
                              timedelta(seconds=self.config["launch-grace-seconds"])), snapshot.invalid)

    def launch(self, job_id: str, claude_args: Sequence[str] = ()) -> str:
        """Start the next run of ``job_id`` and return the session name."""
        listing = self.listing()
        view = self._find(listing, job_id)
        record = view.record
        check(Op.START, self._check(listing, view, "launch", functools.cache(self.claude.sessions), WORK_KIND))
        return self.runner.start(record, WORK_KIND, "launch", claude_args)

    def resume(self, job_id: str, claude_args: Sequence[str] = ()) -> str:
        """Continue the session of a needs-input job as its next run and return the session name.

        The session keeps its name, so the new run records the same session. A
        session that is no longer listed raises :class:`SessionGone`: the caller
        starts a new run with ``launch`` instead.
        """
        snapshot = self.store.snapshot()
        sessions = self.claude.sessions()
        listing = self._listing(snapshot, sessions)
        view = self._find(listing, job_id)
        record = view.record
        check(Op.CONTINUE, self._check(listing, view, "resume", lambda: sessions, WORK_KIND))
        name = record.session
        return self.runner.start(record, WORK_KIND, "resume", claude_args, Continuation(name, sessions[name]))

    def _check(self, listing: Listing, view: JobView, operation: str,
               sessions: Callable[[], Mapping[str, Session]] | None = None, kind: SessionKind | None = None) -> Check:
        return Check(view.record, operation, view=view, views=listing.views, invalid=listing.invalid,
                     sessions=sessions, kind=kind, kinds=KINDS)

    def approve(self, job_id: str, by: str = "user") -> None:
        """Record the approval of the current ``goal.md`` of an unlaunched job without open items.

        Reads only this job. A second call for the same goal writes nothing.
        """
        record = self.store.load(job_id)
        check(Op.APPROVE, Check(record, "approve"))
        if record.approved:
            return
        self.store.append_event(job_id, Approved(record.goal_digest, by, self.clock()))

    def claim(self, job_id: str, names: Sequence[str], wait: float = 0) -> None:
        """Add ``names`` to the resources ``job_id`` names. Returns when the job holds every one.

        Every name is granted or none. A held resource is polled for up to ``wait`` seconds, then raises
        :class:`ResourceHeld`. Each poll takes and drops the store lock; no sleep runs under it.
        Only short holds are waited for, and a run that holds a short hold claims nothing new,
        so no two runs wait for each other.
        """
        if not 0 <= wait <= CLAIM_WAIT_MAX_SECONDS:
            raise ValueError(f"wait {wait} is outside 0..{CLAIM_WAIT_MAX_SECONDS}")
        if wait:
            repos = [name for name in names if not resource_names.is_short_hold(name)]
            if repos:
                raise CureJobError(f"{repos[0]} is a repository; claim --wait accepts only device: and build:")
        deadline = self.monotonic() + wait
        while True:
            with self.store.locked():
                held = self._claim_once(job_id, names)
            if held is None:
                return
            remaining = deadline - self.monotonic()
            if remaining <= 0:
                raise ResourceHeld(*held)
            self.sleep(min(CLAIM_POLL_SECONDS, remaining))

    def _claim_once(self, job_id: str, names: Sequence[str]) -> tuple[str, str] | None:
        """Append the claims and return ``None``, or return the first held resource and its holder."""
        snapshot = self.store.snapshot()
        record = self._find_record(snapshot, job_id)
        check(Op.CLAIM, Check(record, "claim", invalid=snapshot.invalid, names=names))
        # Holders need only the records: a lost holder keeps its holds.
        open_records = {other.id: other for other in snapshot.records if is_open(other)}
        held = holders(snapshot.records)
        for name in names:
            holder = held.get(name)
            if holder not in (None, job_id):
                other = open_records[holder]
                # A launched holder keeps the resource even against a lower id.
                if other.run > 0 or lock_rank(other) < lock_rank(record):
                    return name, holder
        self.store.append_events(job_id, [Claim(name, record.run) for name in dict.fromkeys(names)
                                          if name not in record.resources])
        return None

    def release(self, job_id: str, name: str) -> None:
        """End the short hold of ``job_id`` on ``name``. Returns when the job does not hold it.

        Reads only this job. A repository is held until the job ends.
        An abandoned job holds nothing, so a release has nothing to end and gets no write.
        """
        if not resource_names.is_short_hold(name):
            raise CureJobError(f"{name} is a repository; it is held until the job ends")
        record = self.store.load(job_id)
        if record.closed is None and name in record.resources:
            self.store.append_event(job_id, Release(name))

    def close(self, job_id: str, reason: str = "") -> None:
        """Abandon ``job_id``. A job with a session must be stopped first."""
        listing = self.listing()
        check(Op.CLOSE, self._check(listing, self._find(listing, job_id), "close"))
        self.store.append_event(job_id, Closed(reason))

    def set_origin(self, job_id: str, address: str) -> None:
        """Record ``address`` as the session ``job_id`` reports back to.

        Refused once the job has an origin, and once it has a launched run: the run reads its origin at start.
        """
        listing = self.listing()
        check(Op.ORIGIN, self._check(listing, self._find(listing, job_id), "origin"))
        self.store.append_event(job_id, Origin(address, self.clock()))

    def stop(self, job_id: str) -> Stopped:
        """Stop the live session of the latest run of ``job_id``.

        Returns when the binary lists no live entry under the session name. A
        session that is already not live is not an error: relaunch and abandon
        of a lost job start with ``stop``.
        """
        snapshot = self.store.snapshot()
        # Always read: the answer is about the session, whatever the job state.
        sessions = self.claude.sessions()
        listing = self._listing(snapshot, sessions)
        view = self._find(listing, job_id)
        check(Op.STOP, self._check(listing, view, "stop", lambda: sessions))
        return self.runner.stop(view.record, [WORK_KIND], sessions)[0]

    def remove_sessions(self, job_id: str) -> list[str]:
        """Stop and delete the session of every run of a done or abandoned job and return the deleted names.

        A failed job keeps its sessions for the user, and an open job may still use them.
        Records ``sessions-removed`` once no session of the job is listed.
        """
        snapshot = self.store.snapshot()
        sessions = self.claude.sessions()
        listing = self._listing(snapshot, sessions)
        view = self._find(listing, job_id)
        check(Op.REMOVE_SESSIONS, self._check(listing, view, "remove-sessions", lambda: sessions))
        return self.runner.remove_all(view.record, sessions)

    def mark_reported(self, job_id: str) -> None:
        """Record that the origin session was told of the latest run's result.

        Reads only this job. A second call for the same run writes nothing.
        """
        record = self.store.load(job_id)
        check(Op.REPORTED, Check(record, "reported"))
        if record.reported:
            return
        self.store.append_event(job_id, Reported(record.run, self.clock()))

    def finish(self, job_id: str, report: Report) -> Path:
        """Write ``report`` as the ``result.md`` of a launched job and return its path.

        Reads only this job: no session list, no other job's files, no clock.
        """
        record = self.store.load(job_id)
        path = self.store.result_path(job_id)
        check(Op.END, Check(record, "finish", kind=WORK_KIND))
        if not self.store.write_result(job_id, render_result(report)):
            raise JobStateError(f"job {job_id} already has {path}")
        return path

    def prune_half_created(self) -> list[Path]:
        """Remove the directories an interrupted ``new`` left, after one day. Return their paths."""
        now = self.clock()
        return [entry.path for entry in self.store.half_created()
                if now - entry.mtime > HALF_CREATED_AGE and self.store.remove_half_created(entry)]

    def prune(self) -> list[str]:
        """Remove every :func:`expired` job that no open job names as ``after``. Return the removed ids."""
        now = self.clock()
        kept_for = retention(self.config)
        views = self.views()
        predecessors = {view.after.id for view in views if view.after is not None and view.state.is_open}
        removed = []
        for view in views:
            if expired(view, now, kept_for) and view.record.id not in predecessors:
                self.store.remove(view.record.id)
                removed.append(view.record.id)
        return removed

    def _find(self, listing: Listing, job_id: str) -> JobView:
        for view in listing.views:
            if view.record.id == job_id:
                return view
        self._refuse_missing(listing.invalid, job_id)

    def _find_record(self, snapshot: Snapshot, job_id: str) -> JobRecord:
        for record in snapshot.records:
            if record.id == job_id:
                return record
        self._refuse_missing(snapshot.invalid, job_id)

    def _refuse_missing(self, invalid_jobs: Sequence[InvalidJob], job_id: str) -> NoReturn:
        for invalid in invalid_jobs:
            if invalid.id == job_id:
                raise StoreError(f"job {job_id} is invalid: {invalid.problem}")
        raise UnknownJob(f"unknown job {job_id}: {self.store.job_dir(job_id)} holds no handoff.md")
