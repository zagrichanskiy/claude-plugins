"""The actions ``cure-job next`` gives the dispatcher for each job.

Every scheduling decision of the dispatcher is made here, from the derived
view alone, so that it is tested without sessions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from .config import DEFAULTS, Config
from .events import WORK
from .job import JobRecord
from .kinds import KINDS, Recovery, SessionKind
from .result import short_hold_timeout
from .rules import goal_settled, goal_writing, latest_goal_writer
from .sessions import JobSession, Liveness
from .state import JobView, PredecessorGone, SessionView, State

STALLED_CONFIRM_SECONDS = DEFAULTS["dispatcher.stalled-confirm-seconds"]

#: The ``after`` predecessor states that close a held successor. An invalid
#: predecessor is left to its own ``repair``.
CLOSING_PREDECESSOR = (State.FAILED, State.ABANDONED, PredecessorGone.MISSING)


@dataclass(frozen=True)
class Action:
    name: str
    args: Mapping[str, object] = field(default_factory=dict)


def actions(view: JobView | None, row: Mapping[str, object], config: Config = Config(),
            kinds: Mapping[str, SessionKind] = KINDS) -> list[Action]:
    """The actions of one job, in the order the dispatcher takes them: those of the work session and
    the job's state, then those of each other session by its kind's recovery.

    ``row`` is the job's ``list --json`` row. ``view`` is ``None`` for an invalid job.
    """
    if view is None:
        return [Action("repair", {"problem": row["problem"]})]
    record, state = view.record, view.state
    writing = goal_writing(record, kinds)
    settled = goal_settled(record, kinds)
    found = []
    if state in (State.DONE, State.FAILED, State.NEEDS_INPUT) and not record.reported:
        found.append(Action("report"))
    if state in (State.DONE, State.ABANDONED) and not record.sessions_removed:
        found.append(Action("remove-sessions"))
    if state is State.NEEDS_INPUT:
        answers = _answers_session(record, kinds)
        if answers is not None:
            if answers.ended:
                found.append(Action("ask-open" if record.open_items else "resume"))
        elif not writing:
            timeout = short_hold_timeout(record.result) if record.result else None
            if timeout:
                found.append(Action("ask-timeout", {"resource": timeout.resource, "holder": timeout.holder}))
            else:
                found.append(Action("ask-input"))
    elif state is State.STALLED:
        found.append(Action("confirm-stalled", {"stalled-confirm-seconds": config["dispatcher.stalled-confirm-seconds"]}))
    elif state is State.LOST:
        found.append(Action("ask-relaunch"))
    elif state is State.BLOCKED:
        found.append(Action("tell-blocked", {"waiting-for": row["waiting-for"]}))
    elif state is State.HELD and view.after is not None and view.after.state in CLOSING_PREDECESSOR:
        found.append(Action("close-successor", {"after": view.after.id, "after-state": view.after.state.value}))
    elif state is State.QUEUED or (state is State.HELD and not record.has_goal):
        if not writing and (view.after is None or view.after.goal):
            found.append(Action("draft"))
    elif state is State.AWAITING_APPROVAL or (state is State.HELD and not record.approved):
        if settled and (view.after is None or view.after.state is not PredecessorGone.INVALID):
            found.append(Action("ask-approval"))
    elif state is State.APPROVED:
        if settled:
            found.append(Action("launch"))
    elif (state is State.HELD and (view.after is None or view.after.satisfied)
          and any(holder > record.id for holder in view.blocked_by)):
        # A held approved job that a higher id blocks can wait with no bound.
        found.append(Action("note-starved"))
    for name, session in view.sessions.items():
        kind = kinds.get(name)
        # A kind this version does not know gets no action.
        if name != WORK and kind is not None:
            found.extend(_session_actions(record, kind, session, config))
    return found


def _answers_session(record: JobRecord, kinds: Mapping[str, SessionKind]) -> JobSession | None:
    """The latest goal session, where it started in the current run with answers to ``result.md``."""
    latest = latest_goal_writer(record, kinds)
    if latest is None or latest.run != record.run or record.result is None or not latest.inputs:
        return None
    return latest


def _session_actions(record: JobRecord, kind: SessionKind, view: SessionView, config: Config) -> list[Action]:
    named = {"kind": kind.name, "session": view.session.name}
    if view.liveness is Liveness.WAITING:
        return [Action("tell-blocked", {**named, "waiting-for": view.waiting_for})]
    if view.liveness not in (Liveness.STALLED, Liveness.GONE):
        return []
    if kind.recovery is Recovery.RESTART:
        return [Action("restart-session", {"kind": kind.name, "inputs": list(view.session.inputs),
                                           "restarts": record.restarts(kind.name)})]
    if view.liveness is Liveness.STALLED:
        return [Action("confirm-stalled",
                       {**named, "stalled-confirm-seconds": config["dispatcher.stalled-confirm-seconds"]})]
    return [Action("ask-relaunch", named)]
