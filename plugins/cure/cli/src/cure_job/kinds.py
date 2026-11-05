"""The kinds of session a job runs, as data.

A kind declares the job states it may start in, its own start refusals, the job files it writes,
its permission rules and how it prepares a start. The START rule of :mod:`cure_job.rules` runs the
refusals of the kind, then the generic ones. :class:`~cure_job.runner.SessionRunner` starts a session
of any kind by one protocol.
"""
from __future__ import annotations

import enum
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

from . import events
from .errors import PluginError
from .goal import RULES, missing_paths, retarget, tier
from .job import JobRecord
from .job_id import session_name
from .rules import (Artifact, Guard, after_satisfied, approved_first, goal_exists, kept_session_not_live,
                    no_invalid_job, not_blocked, ready_not_held, state_in_start_states)
from .state import State
from .store import JobStore

CURE_JOB = Path("bin", "cure-job")
#: The variable a session reads its job id from.
JOB_ID_VARIABLE = "CURE_JOB_ID"

#: The agent a work session of a Light or Full goal runs as. A Solo goal, or a goal without a
#: recognised tier, runs in a plain session.
ORCHESTRATOR = "cure:orchestrator"
ORCHESTRATED_TIERS = ("Light", "Full")


class End(enum.Enum):
    """How a session of the kind ends: a ``session-ended`` event, or ``result.md``."""
    EVENT = "event"
    RESULT = "result"


class Recovery(enum.Enum):
    """What ``next`` proposes for a stalled or gone session of the kind."""
    ASK = "ask"
    RESTART = "restart"


@dataclass(frozen=True)
class StartContext:
    record: JobRecord
    store: JobStore
    plugin_root: Path
    #: The operation word in the refusal texts: ``launch``, ``resume``.
    operation: str
    n: int
    session: str
    inputs: Mapping[str, Path]


@dataclass(frozen=True, kw_only=True)
class SessionKind:
    name: str
    #: Runs after :attr:`prepare`.
    agent: Callable[[StartContext], str | None]
    #: Permission rules; ``{cure_job}``, ``{job_id}`` and ``{job_dir}`` are filled in.
    allow: tuple[str, ...]
    deny: tuple[str, ...] = ()
    default_args: tuple[str, ...] = ()
    start_states: frozenset[State]
    #: Run in order before the generic start guards; the first refusal wins.
    start_guards: tuple[Guard, ...]
    writes: frozenset[Artifact]
    end: End
    #: The number of summary lines the end of a session reports.
    summary_lines: int = 0
    recovery: Recovery
    #: False: the next start of the job stops an ended session of this kind that is still live.
    resumable: bool
    #: The stem of the input copy ``<input>-<n>.md``.
    input: str | None = None
    session_name: Callable[[str, int], str]
    #: Raises the refusals that read files, makes idempotent edits and returns the prompt.
    prepare: Callable[[StartContext], str]


def settings_arguments(kind: SessionKind, ctx: StartContext) -> list[str]:
    """The ``--settings`` pair of a session of ``kind``: its permission rules and :data:`JOB_ID_VARIABLE`."""
    job_id = ctx.record.id
    cure_job = ctx.plugin_root / CURE_JOB
    fields = {"cure_job": cure_job, "job_id": job_id, "job_dir": ctx.record.dir}
    allow = [rule.format(**fields) for rule in kind.allow]
    if kind.end is End.EVENT:
        allow.append(f"Bash({cure_job} end {job_id} {kind.name} *)")
    permissions: dict[str, list[str]] = {"allow": allow}
    if kind.deny:
        permissions["deny"] = [rule.format(**fields) for rule in kind.deny]
    settings = {"permissions": permissions, "env": {JOB_ID_VARIABLE: job_id}}
    return ["--settings", json.dumps(settings, separators=(",", ":"))]


def _work_prepare(ctx: StartContext) -> str:
    """Check the plugin files a new run needs, point the goal file at this plugin and return the prompt."""
    job_id = ctx.record.id
    rules = ctx.plugin_root / RULES
    if not rules.is_file():
        raise PluginError(f"{ctx.operation} refused: {rules} does not exist; the goal file names it")
    missing = missing_paths(retarget(ctx.store.read_goal(job_id), ctx.plugin_root), ctx.plugin_root)
    if missing:
        raise PluginError(f"{ctx.operation} refused: the goal file names {', '.join(missing)}, which does not exist; "
                          "write the goal again with cure:goal")
    ctx.store.rewrite_goal(job_id, lambda text: retarget(text, ctx.plugin_root))
    return f"/goal @{ctx.store.goal_path(job_id)}"


def _work_agent(ctx: StartContext) -> str | None:
    return ORCHESTRATOR if tier(ctx.store.read_goal(ctx.record.id)) in ORCHESTRATED_TIERS else None


WORK = SessionKind(
    name=events.WORK,
    agent=_work_agent,
    allow=("Bash({cure_job} finish {job_id} *)", "Bash({cure_job} claim {job_id} *)",
           "Bash({cure_job} release {job_id} *)", "Bash({cure_job} config get *)", "Bash({cure_job} list *)",
           "Bash({cure_job} finish --help)"),
    start_states=frozenset({State.APPROVED, State.LOST, State.NEEDS_INPUT}),
    start_guards=(approved_first, after_satisfied, ready_not_held, state_in_start_states, kept_session_not_live,
                  goal_exists, not_blocked, no_invalid_job),
    writes=frozenset({Artifact.RESULT}),
    end=End.RESULT,
    recovery=Recovery.ASK,
    resumable=True,
    session_name=session_name,
    prepare=_work_prepare,
)

KINDS: Mapping[str, SessionKind] = {WORK.name: WORK}
