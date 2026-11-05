"""The refusals of every job operation, in one table.

Each row of :data:`RULES` is an ordered tuple of guards. :func:`check` raises the first refusal, so
the order of a row is the precedence of its refusals and part of the contract, as are their classes
and texts. A guard reads one :class:`Check` and returns the refusal or ``None``.

A row that reads the record only gets no :class:`JobView`: such a view would show a held job as not
held. The session list costs one run of the binary, so a guard that needs it calls ``Check.sessions``.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Mapping, Sequence

from . import resource as resource_names
from .claude import Session
from .errors import CureJobError, JobStateError, ResourceHeld, SessionGone, StoreError
from .job import JobRecord
from .sessions import listed_live
from .state import JobView, State, holders, is_ready
from .store import InvalidJob

if TYPE_CHECKING:
    from .kinds import SessionKind


class Op(enum.Enum):
    START = "start"
    CONTINUE = "continue"
    END = "end"
    STOP = "stop"
    APPROVE = "approve"
    CLOSE = "close"
    CLAIM = "claim"
    REMOVE_SESSIONS = "remove-sessions"
    ORIGIN = "origin"
    REPORTED = "reported"


class Reads(enum.Enum):
    RECORD = "record"
    LISTING = "listing"


class Fact(enum.Enum):
    """A fact of :class:`Check` beside the record and the view that a row reads."""
    KIND = "kind"
    KINDS = "kinds"
    SESSIONS = "sessions"


class Artifact(enum.Enum):
    """A job file a session kind writes."""
    GOAL = "goal.md"
    RESULT = "result.md"


@dataclass(frozen=True)
class Check:
    """The facts one operation is checked against."""
    record: JobRecord
    #: The operation word in the refusal texts: ``launch``, ``resume``, ``claim``.
    operation: str
    #: ``None`` for a row that reads the record only.
    view: JobView | None = None
    views: Sequence[JobView] = ()
    invalid: Sequence[InvalidJob] = ()
    #: The session list; the caller memoises it.
    sessions: Callable[[], Mapping[str, Session]] | None = None
    kind: SessionKind | None = None
    #: Every kind, for the kind of each open session.
    kinds: Mapping[str, SessionKind] = field(default_factory=dict)
    #: The resources a ``claim`` asks for.
    names: Sequence[str] = ()
    #: The summary lines an ``end`` reports.
    summary: Sequence[str] = ()


Guard = Callable[[Check], CureJobError | None]


@dataclass(frozen=True)
class Rule:
    reads: Reads
    guards: tuple[Guard, ...]
    needs: frozenset[Fact] = frozenset()


def _given(facts: Check, fact: Fact) -> bool:
    if fact is Fact.KINDS:
        return bool(facts.kinds)
    return getattr(facts, fact.value) is not None


def check(op: Op, facts: Check) -> None:
    """Raise the first refusal of the row of ``op``."""
    rule = RULES[op]
    if rule.reads is Reads.LISTING and facts.view is None:
        raise AssertionError(f"{op.value} reads the listing and got no view")
    missing = [fact.value for fact in Fact if fact in rule.needs and not _given(facts, fact)]
    if missing:
        raise AssertionError(f"{op.value} needs {', '.join(missing)} and got none")
    for guard in rule.guards:
        refusal = guard(facts)
        if refusal is not None:
            raise refusal


def goal_settled(record: JobRecord, kinds: Mapping[str, SessionKind]) -> bool:
    """The job has a goal, and no open session of a kind that writes the goal."""
    return record.has_goal and not any(_writes_goal(kinds, session.kind) for session in record.open_sessions())


def _writes_goal(kinds: Mapping[str, SessionKind], name: str) -> bool:
    """A kind this version does not know declares no artifact, so it writes nothing it knows of."""
    kind = kinds.get(name)
    return kind is not None and Artifact.GOAL in kind.writes


def _path(record: JobRecord, artifact: Artifact) -> str:
    return str(record.dir / artifact.value)


def _resource_held(facts: Check) -> ResourceHeld:
    """The first resource of the job that another job holds, with its holder."""
    record = facts.record
    held = holders(view.record for view in facts.views)
    name = next(name for name in sorted(record.resources) if held.get(name) not in (None, record.id))
    return ResourceHeld(name, held[name])


# --- start guards a kind may declare ----------------------------------------------------------------------------------

def approved_first(facts: Check) -> CureJobError | None:
    job_id = facts.record.id
    if facts.view.state is State.AWAITING_APPROVAL:
        return JobStateError(f"job {job_id} is {facts.view.state.value}; approve its goal first: "
                             f"cure-job approve {job_id} --by user")
    return None


def after_satisfied(facts: Check) -> CureJobError | None:
    view = facts.view
    if view.state is State.HELD and view.after is not None and not view.after.satisfied:
        return JobStateError(f"after {view.after.id} is {view.after.state.value}")
    return None


def ready_not_held(facts: Check) -> CureJobError | None:
    view = facts.view
    if view.state is State.HELD and view.blocked_by and is_ready(facts.record):
        return _resource_held(facts)
    return None


def state_in_start_states(facts: Check) -> CureJobError | None:
    state = facts.view.state
    start_states = facts.kind.start_states
    if state not in start_states:
        return JobStateError(f"job {facts.record.id} is {state.value}; {facts.operation} needs "
                             + ", ".join(item.value for item in State if item in start_states))
    return None


def kept_session_not_live(facts: Check) -> CureJobError | None:
    """The kept session of a needs-input job is not in the listing the state needs, so it is read here."""
    record = facts.record
    state = facts.view.state
    name = record.session
    if state is State.NEEDS_INPUT and name is not None and listed_live(facts.sessions().get(name)):
        return JobStateError(f"job {record.id} is {state.value} and its session {name} is live; "
                             f"continue it: cure-job resume {record.id}")
    return None


def goal_exists(facts: Check) -> CureJobError | None:
    record = facts.record
    if not record.has_goal:
        return JobStateError(f"job {record.id} has no goal file: {_path(record, Artifact.GOAL)} does not exist")
    return None


def not_blocked(facts: Check) -> CureJobError | None:
    return _resource_held(facts) if facts.view.blocked_by else None


def no_invalid_job(facts: Check) -> CureJobError | None:
    if not facts.invalid:
        return None
    invalid = facts.invalid[0]
    return StoreError(f"{facts.operation} refused: job {invalid.id} is invalid and may hold any resource; "
                      f"fix or remove {invalid.dir}: {invalid.problem}")


# --- end guards a kind may declare ------------------------------------------------------------------------------------

def finish_open(facts: Check) -> CureJobError | None:
    if facts.record.closed is not None:
        return JobStateError(f"job {facts.record.id} is abandoned; finish needs an open launched job")
    return None


def finish_no_result(facts: Check) -> CureJobError | None:
    record = facts.record
    if record.result is not None:
        return JobStateError(f"job {record.id} already has {_path(record, Artifact.RESULT)}")
    return None


def finish_launched(facts: Check) -> CureJobError | None:
    if facts.record.run == 0:
        return JobStateError(f"job {facts.record.id} has no launched event; finish needs a launched job")
    return None


# --- generic guards ---------------------------------------------------------------------------------------------------

def _kind_start_guards(facts: Check) -> CureJobError | None:
    return next((refusal for guard in facts.kind.start_guards if (refusal := guard(facts)) is not None), None)


def _goal_settled(facts: Check) -> CureJobError | None:
    """A kind that writes the goal starts without one, and its own open session does not block it."""
    record = facts.record
    starting = facts.kind
    if not record.has_goal and Artifact.GOAL not in starting.writes:
        return goal_exists(facts)
    writer = next((session for session in record.open_sessions()
                   if session.kind != starting.name and _writes_goal(facts.kinds, session.kind)), None)
    if writer is not None:
        return JobStateError(f"job {record.id}: its {writer.kind} session {writer.name} writes the goal; "
                             f"{facts.operation} needs a settled goal")
    return None


def _no_other_live_session(facts: Check) -> CureJobError | None:
    """A job has at most one live session."""
    job_id = facts.record.id
    for kind, session in facts.view.sessions.items():
        if session.liveness is not None and session.liveness.is_live:
            return JobStateError(f"job {job_id} has live {kind} session {session.session.name}; "
                                 f"stop it first: cure-job stop {job_id}")
    return None


def _kind_end_guards(facts: Check) -> CureJobError | None:
    return next((refusal for guard in facts.kind.end_guards if (refusal := guard(facts)) is not None), None)


def _session_open(facts: Check) -> CureJobError | None:
    record = facts.record
    latest = record.latest(facts.kind.name)
    if latest is None or latest.ended:
        return JobStateError(f"job {record.id} has no open {facts.kind.name} session; nothing to end")
    return None


def _summary_lines(facts: Check) -> CureJobError | None:
    expected = facts.kind.summary_lines
    if len(facts.summary) != expected:
        return CureJobError(f"{facts.operation} of a {facts.kind.name} session needs {expected} summary line(s), "
                            f"got {len(facts.summary)}")
    return None


# --- guards of one row ------------------------------------------------------------------------------------------------

def _resume_needs_input(facts: Check) -> CureJobError | None:
    state = facts.view.state
    if state is not State.NEEDS_INPUT:
        return JobStateError(f"job {facts.record.id} is {state.value}; {facts.operation} needs "
                             f"{State.NEEDS_INPUT.value}")
    return None


def _kept_session_listed(facts: Check) -> CureJobError | None:
    record = facts.record
    name = record.session
    session = facts.sessions().get(name) if name is not None else None
    if session is None or session.uuid is None:
        return SessionGone(f"job {record.id}: session {name} no longer exists; "
                           f"start a new run: cure-job launch {record.id}")
    return None


def _no_live_session(facts: Check) -> CureJobError | None:
    view = facts.view
    job_id = facts.record.id
    for session in view.sessions.values():
        if session.liveness is not None and session.liveness.is_live:
            return JobStateError(f"job {job_id} is {view.state.value}; stop session "
                                 f"{session.session.name} first: cure-job stop {job_id}")
    return None


def _open(facts: Check) -> CureJobError | None:
    state = facts.view.state
    if not state.is_open:
        return JobStateError(f"job {facts.record.id} is {state.value}; {facts.operation} needs an open job")
    return None


def _has_session(facts: Check) -> CureJobError | None:
    """Without a kind, a session of any kind; with one, a session of that kind."""
    record = facts.record
    if facts.kind is None and not record.sessions:
        return JobStateError(f"job {record.id} has no launched run; nothing to stop")
    if facts.kind is not None and record.latest(facts.kind.name) is None:
        return JobStateError(f"job {record.id} has no {facts.kind.name} session; nothing to stop")
    return None


def _done_or_abandoned(facts: Check) -> CureJobError | None:
    state = facts.view.state
    if state not in (State.DONE, State.ABANDONED):
        return JobStateError(f"job {facts.record.id} is {state.value}; {facts.operation} needs "
                             f"{State.DONE.value} or {State.ABANDONED.value}")
    return None


def _no_origin(facts: Check) -> CureJobError | None:
    record = facts.record
    if record.origin is not None:
        return JobStateError(f"job {record.id} already has origin {record.origin}; an origin is never replaced")
    return None


def _origin_before_launch(facts: Check) -> CureJobError | None:
    if facts.record.run > 0:
        return JobStateError(f"job {facts.record.id} has a launched run; "
                             "origin is recorded only before the first launch")
    return None


def _claim_not_abandoned(facts: Check) -> CureJobError | None:
    if facts.record.closed is not None:
        return JobStateError(f"job {facts.record.id} is abandoned; claim needs a launched run")
    return None


def _claim_launched(facts: Check) -> CureJobError | None:
    if facts.record.run == 0:
        return JobStateError(f"job {facts.record.id} has no launched run; claim needs a launched run")
    return None


def _claim_no_result(facts: Check) -> CureJobError | None:
    record = facts.record
    # A relaunch archives result.md before it records the next run.
    if record.result is not None or record.run in record.archived_runs:
        return JobStateError(f"job {record.id} has a result for run {record.run}; claim needs a running run")
    return None


def _claim_keeps_short_holds(facts: Check) -> CureJobError | None:
    record = facts.record
    short = sorted(name for name in record.resources if resource_names.is_short_hold(name))
    if short and not set(facts.names) <= record.resources:
        return CureJobError(f"job {record.id} holds {', '.join(short)}; release {', '.join(short)} first")
    return None


def _approve_open(facts: Check) -> CureJobError | None:
    if facts.record.closed is not None:
        return JobStateError(f"job {facts.record.id} is abandoned; approve needs an open job")
    return None


def _approve_unlaunched(facts: Check) -> CureJobError | None:
    if facts.record.run > 0:
        return JobStateError(f"job {facts.record.id} has a launched run; "
                             "approve applies only before the first launch")
    return None


def _approve_no_result(facts: Check) -> CureJobError | None:
    if facts.record.result is not None:
        return JobStateError(f"job {facts.record.id} has a result; approve needs a job without one")
    return None


def _no_open_items(facts: Check) -> CureJobError | None:
    record = facts.record
    if record.open_items:
        return JobStateError(f"job {record.id}: {_path(record, Artifact.GOAL)} has {record.open_items} item(s) "
                             "under ## Open; settle them before approve")
    return None


def _reported_launched(facts: Check) -> CureJobError | None:
    if facts.record.run == 0:
        return JobStateError(f"job {facts.record.id} has no launched run; nothing to report")
    return None


def _reported_has_result(facts: Check) -> CureJobError | None:
    record = facts.record
    if record.result is None:
        return JobStateError(f"job {record.id} has no result: {_path(record, Artifact.RESULT)} does not exist")
    return None


#: Every row that starts a session ends with these.
_GENERIC_START: tuple[Guard, ...] = (_goal_settled, _no_other_live_session)
_START_NEEDS = frozenset({Fact.KIND, Fact.KINDS, Fact.SESSIONS})

RULES: Mapping[Op, Rule] = {
    Op.START: Rule(Reads.LISTING, (_kind_start_guards, *_GENERIC_START), _START_NEEDS),
    Op.CONTINUE: Rule(Reads.LISTING, (_resume_needs_input, _kept_session_listed, goal_exists, not_blocked,
                                      no_invalid_job, *_GENERIC_START), _START_NEEDS),
    Op.CLOSE: Rule(Reads.LISTING, (_no_live_session, _open)),
    Op.STOP: Rule(Reads.LISTING, (_has_session,)),
    Op.REMOVE_SESSIONS: Rule(Reads.LISTING, (_done_or_abandoned,)),
    Op.ORIGIN: Rule(Reads.LISTING, (_no_origin, _origin_before_launch)),
    Op.CLAIM: Rule(Reads.RECORD, (_claim_not_abandoned, _claim_launched, _claim_no_result, _claim_keeps_short_holds,
                                  no_invalid_job)),
    Op.APPROVE: Rule(Reads.RECORD, (_approve_open, _approve_unlaunched, _approve_no_result, goal_exists,
                                    _no_open_items)),
    Op.END: Rule(Reads.RECORD, (_kind_end_guards, _session_open, _summary_lines), frozenset({Fact.KIND})),
    Op.REPORTED: Rule(Reads.RECORD, (_reported_launched, _reported_has_result)),
}
