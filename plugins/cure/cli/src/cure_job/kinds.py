"""The kinds of session a job runs, as data.

A kind declares the job states it may start in, its own start refusals and the job files it writes.
The START rule of :mod:`cure_job.rules` runs the refusals of the kind, then the generic ones.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from . import events
from .rules import (Artifact, Guard, after_satisfied, approved_first, goal_exists, kept_session_not_live,
                    no_invalid_job, not_blocked, ready_not_held, state_in_start_states)
from .state import State


@dataclass(frozen=True, kw_only=True)
class SessionKind:
    name: str
    start_states: frozenset[State]
    #: Run in order before the generic start guards; the first refusal wins.
    start_guards: tuple[Guard, ...]
    writes: frozenset[Artifact]


WORK = SessionKind(
    name=events.WORK,
    start_states=frozenset({State.APPROVED, State.LOST, State.NEEDS_INPUT}),
    start_guards=(approved_first, after_satisfied, ready_not_held, state_in_start_states, kept_session_not_live,
                  goal_exists, not_blocked, no_invalid_job),
    writes=frozenset({Artifact.RESULT}),
)

KINDS: Mapping[str, SessionKind] = {WORK.name: WORK}
