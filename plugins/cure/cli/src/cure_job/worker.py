"""The ``claude`` arguments of a worker session beyond its name and prompt.

The caller of ``launch`` and ``resume`` may choose only the permission mode
(:class:`RunArguments`). The CLI adds the permission rules the worker needs to
report back (:class:`WorkerSettings`).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

from .errors import CureJobError

CURE_JOB = Path("bin", "cure-job")


class RunArguments:
    """The arguments after ``--``: at most one ``--permission-mode`` of :attr:`MODES`."""

    OPTION = "--permission-mode"
    MODES = ("acceptEdits", "default", "auto")

    def __init__(self, given: Sequence[str]):
        self.mode = self._mode(list(given))

    def arguments(self) -> list[str]:
        return [self.OPTION, self.mode] if self.mode is not None else []

    def _mode(self, given: list[str]) -> str | None:
        if not given:
            return None
        if len(given) == 2 and given[0] == self.OPTION:
            mode = given[1]
        elif len(given) == 1 and given[0].startswith(self.OPTION + "="):
            mode = given[0][len(self.OPTION) + 1:]
        else:
            raise CureJobError(f"refused claude arguments {' '.join(given)!r}; after -- only "
                               f"{self.OPTION} {'|'.join(self.MODES)} is accepted")
        if mode not in self.MODES:
            raise CureJobError(f"refused {self.OPTION} {mode!r}; expected one of {', '.join(self.MODES)}")
        return mode


class WorkerSettings:
    """The ``--settings`` that allow a worker to run ``cure-job finish``, ``claim`` and ``release`` on its job."""

    COMMANDS = ("finish", "claim", "release")
    READS = ("config get", "list")

    def __init__(self, plugin_root: Path, job_id: str):
        self.cure_job = Path(plugin_root) / CURE_JOB
        self.job_id = job_id

    def rules(self) -> list[str]:
        return ([f"Bash({self.cure_job} {command} {self.job_id} *)" for command in self.COMMANDS]
                + [f"Bash({self.cure_job} {command} *)" for command in self.READS])

    def arguments(self) -> list[str]:
        return ["--settings", json.dumps({"permissions": {"allow": self.rules()}}, separators=(",", ":"))]
