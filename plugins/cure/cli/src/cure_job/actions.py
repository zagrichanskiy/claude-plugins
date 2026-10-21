"""The actions ``cure-job next`` gives the dispatcher for each job.

Every scheduling decision of the dispatcher is made here, from the derived
view alone, so that it is tested without sessions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from .config import DEFAULTS, Config
from .result import short_hold_timeout
from .state import JobView, PredecessorGone, State

STALLED_CONFIRM_SECONDS = DEFAULTS["dispatcher.stalled-confirm-seconds"]

#: The ``after`` predecessor states that close a held successor. An invalid
#: predecessor is left to its own ``repair``.
CLOSING_PREDECESSOR = (State.FAILED, State.ABANDONED, PredecessorGone.MISSING)


@dataclass(frozen=True)
class Action:
    name: str
    args: Mapping[str, object] = field(default_factory=dict)


def actions(view: JobView | None, row: Mapping[str, object], config: Config = Config(),
            after_goal: bool = False) -> list[Action]:
    """The actions of one job, in the order the dispatcher takes them.

    ``row`` is the job's ``list --json`` row. ``view`` is ``None`` for an invalid job.
    ``after_goal`` is true when the job's ``after`` predecessor has a goal.
    """
    if view is None:
        return [Action("repair", {"problem": row["problem"]})]
    record, state = view.record, view.state
    found = []
    if state in (State.DONE, State.FAILED, State.NEEDS_INPUT) and not record.reported:
        found.append(Action("report"))
    if state in (State.DONE, State.ABANDONED) and not record.sessions_removed:
        found.append(Action("remove-sessions"))
    if state is State.NEEDS_INPUT:
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
        if view.after is None or after_goal:
            found.append(Action("draft"))
    elif state is State.AWAITING_APPROVAL or (state is State.HELD and not record.approved):
        if view.after is None or view.after.state is not PredecessorGone.INVALID:
            found.append(Action("ask-approval"))
    elif state is State.APPROVED:
        found.append(Action("launch"))
    elif (state is State.HELD and (view.after is None or view.after.satisfied)
          and any(holder > record.id for holder in view.blocked_by)):
        # A held approved job that a higher id blocks can wait with no bound.
        found.append(Action("note-starved"))
    return found
