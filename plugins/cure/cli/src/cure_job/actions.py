"""The actions ``cure-job next`` gives the dispatcher for each job.

Every scheduling decision of the dispatcher is made here, from the derived
view alone, so that it is tested without sessions.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

from .result import short_hold_timeout
from .state import JobView, State

#: Replaced by ``dispatcher.stalled-confirm-seconds`` of ``config.json`` once it exists.
STALLED_CONFIRM_SECONDS = 60


@dataclass(frozen=True)
class Action:
    name: str
    args: Mapping[str, object] = field(default_factory=dict)


def actions(view: JobView | None, row: Mapping[str, object]) -> list[Action]:
    """The actions of one job, in the order the dispatcher takes them.

    ``row`` is the job's ``list --json`` row. ``view`` is ``None`` for an invalid job.
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
        found.append(Action("confirm-stalled", {"stalled-confirm-seconds": STALLED_CONFIRM_SECONDS}))
    elif state is State.LOST:
        found.append(Action("ask-relaunch"))
    elif state is State.BLOCKED:
        found.append(Action("tell-blocked", {"waiting-for": row["waiting-for"]}))
    elif state is State.QUEUED:
        found.append(Action("draft"))
    elif state is State.AWAITING_APPROVAL:
        found.append(Action("ask-approval"))
    return found
