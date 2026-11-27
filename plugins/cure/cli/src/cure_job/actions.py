"""The actions ``cure-job next`` gives the dispatcher for each job.

Every scheduling decision of the dispatcher is made here, from the derived
view alone, so that it is tested without sessions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

from .config import DEFAULTS, Config
from .events import REQUESTABLE, WORK
from .job import JobRecord
from .kinds import KINDS, Recovery, SessionKind
from .result import short_hold_timeout
from .rules import goal_settled
from .sessions import Liveness
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
    settled = goal_settled(record, kinds)
    # Who takes a message to the job's owner: the origin session itself, or the dispatcher in its place.
    route = {"route": "origin" if view.origin_reachable else "dispatcher"}
    found = []
    if state in (State.DONE, State.FAILED, State.NEEDS_INPUT) and not record.reported:
        found.append(Action("report", route))
    if state in (State.DONE, State.ABANDONED) and not record.sessions_removed:
        found.append(Action("remove-sessions"))
    if state is State.NEEDS_INPUT:
        found.append(_ask(record.result.questions if record.result else (), route, {}))
    elif state is State.AWAITING_ANSWER:
        if not view.origin_reachable:
            found.append(_ask(record.question, route, {"question": list(record.question)}))
    elif state is State.STALLED:
        found.append(Action("confirm-stalled", {"stalled-confirm-seconds": config["dispatcher.stalled-confirm-seconds"]}))
    elif state is State.LOST:
        found.append(Action("ask-relaunch"))
    elif state is State.BLOCKED:
        found.append(Action("tell-blocked", {"waiting-for": row["waiting-for"]}))
    elif state is State.HELD and view.after is not None and view.after.state in CLOSING_PREDECESSOR:
        found.append(Action("close-successor", {"after": view.after.id, "after-state": view.after.state.value}))
    elif state is State.QUEUED or (state is State.HELD and not record.has_goal):
        if view.after is None or view.after.goal:
            found.append(Action("draft"))
    elif state is State.AWAITING_APPROVAL or (state is State.HELD and not record.approved):
        if settled and (view.after is None or view.after.state is not PredecessorGone.INVALID):
            found.append(Action("ask-approval", route))
    elif state is State.APPROVED:
        if settled:
            found.append(Action("launch"))
    for name, session in view.sessions.items():
        kind = kinds.get(name)
        # A kind this version does not know gets no action.
        if name != WORK and kind is not None:
            found.extend(_session_actions(record, kind, session, config))
    # The origin was sent a requested action once; a dispatcher-route action is always asked.
    return [action for action in found if not (action.name in REQUESTABLE and action.args.get("route") == "origin"
                                               and record.requested(action.name))]


def _ask(questions: Sequence[str], route: Mapping[str, object], input_args: Mapping[str, object]) -> Action:
    """``ask-timeout`` when ``questions`` is a short-hold timeout, else ``ask-input`` with ``input_args``."""
    timeout = short_hold_timeout(questions)
    if timeout:
        return Action("ask-timeout", {"resource": timeout.resource, "holder": timeout.holder, **route})
    return Action("ask-input", {**route, **input_args})


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
