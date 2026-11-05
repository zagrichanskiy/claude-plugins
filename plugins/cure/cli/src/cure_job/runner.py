"""The start, stop and removal of the sessions of a job, one protocol for every kind.

The caller runs the refusals of :mod:`cure_job.rules` first. A start then prepares, so a refusal of
``prepare`` comes before any stop, archive or ``claude`` call.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable, Mapping, NamedTuple, Sequence

from .claude import Claude, Session
from .clock import Clock
from .errors import ClaudeError, ClaudeOutcomeUnknown, CureJobError, StoreError
from .events import SessionEnded, SessionsRemoved, SessionStarted, SessionStopped
from .job import JobRecord
from .kinds import KINDS, End, SessionKind, StartContext, settings_arguments
from .sessions import listed_live
from .store import JobStore

#: How long a stop waits for the listing to drop a stopped session, and how often it reads the
#: listing meanwhile.
STOP_TIMEOUT_SECONDS = 15.0
STOP_POLL_SECONDS = 0.5


class Continuation(NamedTuple):
    """The session a start continues, by name and as listed."""
    name: str
    listed: Session


class Stopped(NamedTuple):
    session: str
    #: False when the session was already not live and nothing was stopped.
    was_live: bool


class SessionRunner:
    def __init__(self, store: JobStore, claude: Claude, clock: Clock, plugin_root: Path,
                 sleep: Callable[[float], None], monotonic: Callable[[], float],
                 kinds: Mapping[str, SessionKind] = KINDS):
        self.store = store
        self.claude = claude
        self.clock = clock
        self.plugin_root = plugin_root
        # The wait of a stop; a test passes a fake pair so that it never waits.
        self.sleep = sleep
        self.monotonic = monotonic
        self.kinds = kinds

    def start(self, record: JobRecord, kind: SessionKind, operation: str, claude_args: Sequence[str] = (),
              input_text: str | None = None, continuation: Continuation | None = None) -> str:
        """Start the next session of ``kind`` for ``record``, or continue ``continuation``; return its name.

        ``input_text`` is copied to the kind's input file of this session before the start."""
        job_id = record.id
        n = sum(1 for session in record.sessions if session.kind == kind.name) + 1
        name = continuation.name if continuation is not None else kind.session_name(job_id, n)
        if input_text is not None and kind.input is None:
            raise CureJobError(f"a {kind.name} session takes no input")
        inputs = {kind.input: self.store.input_path(job_id, kind.input, n)} if input_text is not None else {}
        ctx = StartContext(record, self.store, self.plugin_root, operation, n, name, inputs)
        prompt = kind.prepare(ctx)
        agent = kind.agent(ctx)
        arguments = [*(["--agent", agent] if agent is not None else []), *settings_arguments(kind, ctx),
                     *kind.default_args, *claude_args]
        if continuation is not None:
            # Resuming a live session starts a copy, so it is stopped first.
            self._stop_session(continuation.name, continuation.listed)
        self._stop_ended(record)
        result_kind = kind.end is End.RESULT
        # result-<run>.md takes the number of the run that wrote it.
        archived = result_kind and self.store.archive_result(job_id, record.run)
        for stem in inputs:
            self.store.write_input(job_id, stem, n, input_text)
        cwd = record.handoff.launch_dir
        unknown = None
        try:
            if continuation is not None:
                self.claude.resume(name, continuation.listed.uuid, cwd, prompt, arguments)
            else:
                self.claude.start(name, cwd, prompt, arguments)
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
            self.store.append_event(job_id, SessionStarted(kind.name, n, name, self.clock(),
                                                           n if result_kind else record.run,
                                                           tuple(path.name for path in inputs.values())))
        except StoreError as e:
            what = f"session {name}" if result_kind else f"{kind.name} session {n}, {name},"
            raise StoreError(f"job {job_id}: {what} may be running and is not recorded; "
                             f"stop it before a retry: {e}") from e
        if unknown is not None:
            if result_kind:
                raise ClaudeOutcomeUnknown(f"{unknown}; recorded as run {n}, session {name}: "
                                           "list shows it launched, then running or lost") from unknown
            raise ClaudeOutcomeUnknown(f"{unknown}; recorded as {kind.name} session {n}, {name}") from unknown
        return name

    def end(self, record: JobRecord, kind: SessionKind, summary: Sequence[str]) -> None:
        """Record the end of the latest session of ``kind``, an ``End.EVENT`` kind."""
        latest = record.latest(kind.name)
        self.store.append_event(record.id, SessionEnded(kind.name, latest.n, tuple(summary), self.clock()))

    def _stop_ended(self, record: JobRecord) -> None:
        """Stop each ended session of a kind that is not resumable and is still live.

        A kind this version does not know is left running: its own version decides."""
        names = [session.name for session in record.sessions
                 if session.ended and session.kind in self.kinds and not self.kinds[session.kind].resumable]
        if not names:
            return
        listed = self.claude.sessions()
        for name in dict.fromkeys(names):
            self._stop_session(name, listed.get(name))

    def stop(self, record: JobRecord, kinds: Iterable[str], listed: Mapping[str, Session]) -> list[Stopped]:
        """Stop the latest session of each kind named in ``kinds`` that ``record`` has, live or not.

        Records a stop for each that has none, even when the session was already down: a session
        listed stopped inside the launch grace is then lost, not launched."""
        stopped = []
        for kind in kinds:
            latest = record.latest(kind)
            if latest is None:
                continue
            was_live = self._stop_session(latest.name, listed.get(latest.name))
            if not latest.stop_recorded:
                self.store.append_event(record.id, SessionStopped(kind, latest.n, self.clock()))
            stopped.append(Stopped(latest.name, was_live=was_live))
        return stopped

    def remove_all(self, record: JobRecord, listed: Mapping[str, Session]) -> list[str]:
        """Stop and delete every listed session of ``record`` and return the deleted names.

        Records ``sessions-removed`` once no session of the job is listed."""
        names = list(record.session_names)
        present = {name: listed[name] for name in names if name in listed}
        for name, session in present.items():
            if not session.all_ids or "" in session.all_ids:
                raise ClaudeError(f"session {name} is listed without an id; claude rm needs one")
        for name, session in present.items():
            # `claude rm` documents only sessions that have exited.
            self._stop_session(name, session)
            for session_id in session.all_ids:
                self.claude.remove(session_id)
        if present:
            left = sorted(set(names) & set(self.claude.sessions()))
            if left:
                raise ClaudeError(f"job {record.id}: still listed after claude rm: {', '.join(left)}")
        if not record.sessions_removed:
            self.store.append_event(record.id, SessionsRemoved(self.clock()))
        return list(present)

    def _stop_session(self, name: str, session: Session | None) -> bool:
        """Stop every live entry of ``session`` and wait until none is listed. False when none was live."""
        if not listed_live(session):
            return False
        if not session.ids or "" in session.ids:
            raise ClaudeError(f"session {name} is listed live without an id; claude stop needs one")
        deadline = self.monotonic() + STOP_TIMEOUT_SECONDS
        for session_id in session.ids:
            self.claude.stop(session_id)
        # `claude stop` may return before the listing drops the pid, and a
        # launch or close that follows at once would see the session alive.
        while listed_live(self.claude.sessions().get(name)):
            if self.monotonic() >= deadline:
                raise ClaudeError(f"session {name} still live after claude stop")
            self.sleep(STOP_POLL_SECONDS)
        return True
