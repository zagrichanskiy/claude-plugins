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

import os
import time
from datetime import timedelta
from pathlib import Path
from typing import Callable, Mapping, NamedTuple, NoReturn, Sequence

from .. import resource as resource_names
from ..claude import Claude, Session, SessionStatus
from ..clock import Clock
from ..config import Config
from ..errors import (ClaudeError, ClaudeOutcomeUnknown, CureJobError, HandoffError, JobStateError, PluginError,
                      ResourceHeld, SessionGone, StoreError, UnknownJob)
from ..events import Approved, Claim, Closed, Launched, Origin, Release, Reported, SessionsRemoved, StopIssued
from ..goal import PLUGIN_ROOT, RULES, missing_paths, retarget, tier
from ..handoff import parse_submitted, stamp
from ..job_id import make_id, session_name
from ..result import Report, render_result
from ..job import JobRecord
from ..state import (HALF_CREATED_AGE, JobView, State, derive, expired, holders, is_open, is_ready, lock_rank,
                     needs_sessions, retention)
from ..store import InvalidJob, JobStore, Snapshot
from ..worker import WorkerSettings


class Listing(NamedTuple):
    views: list[JobView]
    invalid: list[InvalidJob]
    #: The session list the views were derived from; empty when it was not read.
    sessions: Mapping[str, Session]


class Stopped(NamedTuple):
    session: str
    #: False when the session was already not live and nothing was stopped.
    was_live: bool


#: How long ``stop`` waits for the listing to drop a stopped session, and how
#: often it reads the listing meanwhile.
STOP_TIMEOUT_SECONDS = 15.0
STOP_POLL_SECONDS = 0.5

#: The longest ``claim --wait`` fits one foreground Bash call under its 600 s
#: cap. A waiting claim polls the store this often.
CLAIM_WAIT_MAX_SECONDS = 540
CLAIM_POLL_SECONDS = 10.0

#: The agent a launched session of a Light or Full goal runs as. A Solo goal, or
#: a goal without a recognised tier, runs in a plain session.
ORCHESTRATOR = "cure:orchestrator"
ORCHESTRATED_TIERS = ("Light", "Full")


class JobsProvider:
    def __init__(self, store: JobStore, claude: Claude, clock: Clock, plugin_root: Path = PLUGIN_ROOT,
                 sleep: Callable[[float], None] = time.sleep, monotonic: Callable[[], float] = time.monotonic,
                 config: Config = Config()):
        self.store = store
        self.config = config
        self.claude = claude
        self.clock = clock
        self.plugin_root = plugin_root
        # The wait of ``stop``; a test passes a fake pair so that it never waits.
        self.sleep = sleep
        self.monotonic = monotonic

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
        statuses = {name: session.status for name, session in sessions.items()}
        invalid_ids = {job.id for job in snapshot.invalid}
        return Listing(derive(snapshot.records, statuses, self.clock(), invalid_ids,
                              timedelta(seconds=self.config["launch-grace-seconds"])), snapshot.invalid, sessions)

    def launch(self, job_id: str, claude_args: Sequence[str] = ()) -> str:
        """Start the next run of ``job_id`` and return the session name."""
        listing = self.listing()
        view = self._find(listing, job_id)
        record = view.record
        if view.state is State.AWAITING_APPROVAL:
            raise JobStateError(f"job {job_id} is {view.state.value}; approve its goal first: "
                                f"cure-job approve {job_id} --by user")
        if view.state is State.HELD and view.after is not None and not view.after.satisfied:
            raise JobStateError(f"after {view.after.id} is {view.after.state.value}")
        if view.state is State.HELD and view.blocked_by and is_ready(record):
            raise _resource_held(listing, record)
        if not view.state.is_launchable:
            raise JobStateError(f"job {job_id} is {view.state.value}; launch needs "
                                + ", ".join(state.value for state in State if state.is_launchable))
        if view.state is State.NEEDS_INPUT:
            # The kept session of a needs-input job is not in the listing the state needs.
            name = record.session
            if name is not None and _live(self.claude.sessions().get(name)):
                raise JobStateError(f"job {job_id} is {view.state.value} and its session {name} is live; "
                                    f"continue it: cure-job resume {job_id}")
        prompt = self._prepare_run(listing, view, "launch")
        claude_args = [*WorkerSettings(self.plugin_root, job_id).arguments(), *claude_args]
        if tier(self.store.read_goal(job_id)) in ORCHESTRATED_TIERS:
            claude_args = ["--agent", ORCHESTRATOR, *claude_args]
        run = record.run + 1
        session = session_name(job_id, run)
        self._record_run(record, run, session,
                         lambda: self.claude.start(session, record.handoff.launch_dir, prompt, claude_args))
        return session

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
        if view.state is not State.NEEDS_INPUT:
            raise JobStateError(f"job {job_id} is {view.state.value}; resume needs {State.NEEDS_INPUT.value}")
        name = record.session
        session = sessions.get(name) if name is not None else None
        if session is None or session.uuid is None:
            raise SessionGone(f"job {job_id}: session {name} no longer exists; "
                              f"start a new run: cure-job launch {job_id}")
        prompt = self._prepare_run(listing, view, "resume")
        claude_args = [*WorkerSettings(self.plugin_root, job_id).arguments(), *claude_args]
        # Resuming a live session starts a copy, so it is stopped first.
        self._stop_session(name, session)
        self._record_run(record, record.run + 1, name,
                         lambda: self.claude.resume(name, session.uuid, record.handoff.launch_dir, prompt, claude_args))
        return name

    def _prepare_run(self, listing: Listing, view: JobView, operation: str) -> str:
        """Check what a new run needs, point the goal file at this plugin and return the prompt."""
        record = view.record
        job_id = record.id
        goal = self.store.goal_path(job_id)
        if not record.has_goal:
            raise JobStateError(f"job {job_id} has no goal file: {goal} does not exist")
        if view.blocked_by:
            raise _resource_held(listing, record)
        _refuse_invalid(listing.invalid, operation)
        rules = self.plugin_root / RULES
        if not rules.is_file():
            raise PluginError(f"{operation} refused: {rules} does not exist; the goal file names it")
        missing = missing_paths(retarget(self.store.read_goal(job_id), self.plugin_root), self.plugin_root)
        if missing:
            raise PluginError(f"{operation} refused: the goal file names {', '.join(missing)}, which does not exist; "
                              "write the goal again with cure:goal")
        self.store.rewrite_goal(job_id, lambda text: retarget(text, self.plugin_root))
        return f"/goal @{goal}"

    def _record_run(self, record: JobRecord, run: int, session: str, start: Callable[[], None]) -> None:
        """Archive ``result.md``, run ``start`` and record run ``run`` of ``session``."""
        job_id = record.id
        # result-<run>.md takes the number of the run that wrote it.
        archived = self.store.archive_result(job_id, record.run)
        unknown = None
        try:
            start()
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

    def approve(self, job_id: str, by: str = "user") -> None:
        """Record the approval of the current ``goal.md`` of an unlaunched job without open items.

        Reads only this job. A second call for the same goal writes nothing.
        """
        record = self.store.load(job_id)
        if record.closed is not None:
            raise JobStateError(f"job {job_id} is abandoned; approve needs an open job")
        if record.launches:
            raise JobStateError(f"job {job_id} has a launched run; approve applies only before the first launch")
        if record.result is not None:
            raise JobStateError(f"job {job_id} has a result; approve needs a job without one")
        if not record.has_goal:
            raise JobStateError(f"job {job_id} has no goal file: {self.store.goal_path(job_id)} does not exist")
        if record.open_items:
            raise JobStateError(f"job {job_id}: {self.store.goal_path(job_id)} has {record.open_items} item(s) "
                                "under ## Open; settle them before approve")
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
        if record.closed is not None:
            raise JobStateError(f"job {job_id} is abandoned; claim needs a launched run")
        if not record.launches:
            raise JobStateError(f"job {job_id} has no launched run; claim needs a launched run")
        # A relaunch archives result.md before it records the next run.
        if record.result is not None or record.run in record.archived_runs:
            raise JobStateError(f"job {job_id} has a result for run {record.run}; claim needs a running run")
        short = sorted(name for name in record.resources if resource_names.is_short_hold(name))
        if short and not set(names) <= record.resources:
            raise CureJobError(f"job {job_id} holds {', '.join(short)}; release {', '.join(short)} first")
        _refuse_invalid(snapshot.invalid, "claim")
        # Holders need only the records: a lost holder keeps its holds.
        open_records = {other.id: other for other in snapshot.records if is_open(other)}
        held = holders(snapshot.records)
        for name in names:
            holder = held.get(name)
            if holder not in (None, job_id):
                other = open_records[holder]
                # A launched holder keeps the resource even against a lower id.
                if other.launches or lock_rank(other) < lock_rank(record):
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
        view = self._find(self.listing(), job_id)
        if view.state.has_session:
            raise JobStateError(f"job {job_id} is {view.state.value}; stop session "
                                f"{view.record.session} first: cure-job stop {job_id}")
        if not view.state.is_open:
            raise JobStateError(f"job {job_id} is {view.state.value}; close needs an open job")
        self.store.append_event(job_id, Closed(reason))

    def set_origin(self, job_id: str, address: str) -> None:
        """Record ``address`` as the session ``job_id`` reports back to.

        Refused once the job has an origin, and once it has a launched run: the run reads its origin at start.
        """
        view = self._find(self.listing(), job_id)
        if view.record.origin is not None:
            raise JobStateError(f"job {job_id} already has origin {view.record.origin}; an origin is never replaced")
        if view.record.launches:
            raise JobStateError(f"job {job_id} has a launched run; origin is recorded only before the first launch")
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
        record = self._find(self._listing(snapshot, sessions), job_id).record
        if not record.launches:
            raise JobStateError(f"job {job_id} has no launched run; nothing to stop")
        name = record.session
        was_live = self._stop_session(name, sessions.get(name))
        # Recorded even when the session was already down: a session listed
        # stopped inside the launch grace is then lost, not launched.
        if not record.stop_issued:
            self.store.append_event(job_id, StopIssued(record.run, self.clock()))
        return Stopped(name, was_live=was_live)

    def _stop_session(self, name: str, session: Session | None) -> bool:
        """Stop every live entry of ``session`` and wait until none is listed. False when none was live."""
        if not _live(session):
            return False
        if not session.ids or "" in session.ids:
            raise ClaudeError(f"session {name} is listed live without an id; claude stop needs one")
        deadline = self.monotonic() + STOP_TIMEOUT_SECONDS
        for session_id in session.ids:
            self.claude.stop(session_id)
        # `claude stop` may return before the listing drops the pid, and a
        # launch or close that follows at once would see the session alive.
        while _live(self.claude.sessions().get(name)):
            if self.monotonic() >= deadline:
                raise ClaudeError(f"session {name} still live after claude stop")
            self.sleep(STOP_POLL_SECONDS)
        return True

    def remove_sessions(self, job_id: str) -> list[str]:
        """Stop and delete the session of every run of a done or abandoned job and return the deleted names.

        A failed job keeps its sessions for the user, and an open job may still use them.
        Records ``sessions-removed`` once no session of the job is listed.
        """
        snapshot = self.store.snapshot()
        sessions = self.claude.sessions()
        view = self._find(self._listing(snapshot, sessions), job_id)
        if view.state not in (State.DONE, State.ABANDONED):
            raise JobStateError(f"job {job_id} is {view.state.value}; remove-sessions needs "
                                f"{State.DONE.value} or {State.ABANDONED.value}")
        # A resumed run records the session of the run before it, so a name can repeat.
        names = list(dict.fromkeys(launched.session for launched in view.record.launches))
        listed = {name: sessions[name] for name in names if name in sessions}
        for name, session in listed.items():
            if not session.all_ids or "" in session.all_ids:
                raise ClaudeError(f"session {name} is listed without an id; claude rm needs one")
        for name, session in listed.items():
            # `claude rm` documents only sessions that have exited.
            self._stop_session(name, session)
            for session_id in session.all_ids:
                self.claude.remove(session_id)
        if listed:
            left = sorted(set(names) & set(self.claude.sessions()))
            if left:
                raise ClaudeError(f"job {job_id}: still listed after claude rm: {', '.join(left)}")
        if not view.record.sessions_removed:
            self.store.append_event(job_id, SessionsRemoved(self.clock()))
        return list(listed)

    def mark_reported(self, job_id: str) -> None:
        """Record that the origin session was told of the latest run's result.

        Reads only this job. A second call for the same run writes nothing.
        """
        record = self.store.load(job_id)
        if not record.launches:
            raise JobStateError(f"job {job_id} has no launched run; nothing to report")
        if record.result is None:
            raise JobStateError(f"job {job_id} has no result: {self.store.result_path(job_id)} does not exist")
        if record.reported:
            return
        self.store.append_event(job_id, Reported(record.run, self.clock()))

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


def _live(session: Session | None) -> bool:
    return session is not None and session.status is not SessionStatus.STOPPED


def _resource_held(listing: Listing, record: JobRecord) -> ResourceHeld:
    """The first resource of ``record`` that another job holds, with its holder."""
    held = holders(view.record for view in listing.views)
    name = next(name for name in sorted(record.resources) if held.get(name) not in (None, record.id))
    return ResourceHeld(name, held[name])


def _refuse_invalid(invalid_jobs: Sequence[InvalidJob], operation: str) -> None:
    if invalid_jobs:
        invalid = invalid_jobs[0]
        raise StoreError(f"{operation} refused: job {invalid.id} is invalid and may hold any resource; "
                         f"fix or remove {invalid.dir}: {invalid.problem}")
