"""The ``claude`` arguments of a worker or goal-writer session beyond its name and prompt.

The caller of ``launch``, ``resume`` and ``draft`` may choose only the permission
mode (:class:`RunArguments`). The CLI adds the permission rules the worker needs
to report back (:class:`WorkerSettings`), and those the goal-writer needs to
write one goal and nothing else (:class:`GoalWriterSettings`).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Sequence

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
                + [f"Bash({self.cure_job} {command} *)" for command in self.READS]
                + [f"Bash({self.cure_job} finish --help)"])

    def arguments(self) -> list[str]:
        return ["--settings", json.dumps({"permissions": {"allow": self.rules()}}, separators=(",", ":"))]


class GoalWriterSettings:
    """The ``--settings`` of a goal-writer session: run ``cure:goal``, read, edit only the job's ``goal.md``.

    Each ``cure-job`` rule names the bare command, which the plugin's ``bin/`` puts on the PATH, and the
    absolute path. The deny rules keep every decision the dispatcher makes out of the session.
    """

    BARE = "cure-job"
    READS = ("config get", "list")
    DENIED = ("approve", "launch", "resume", "close", "draft", "new")
    #: The read-only commands ``cure:goal`` runs in job mode, and the Tools check.
    COMMANDS = ("git -C * symbolic-ref --short refs/remotes/origin/HEAD", "git -C * branch --show-current",
                "gh repo view --json defaultBranchRef -q .defaultBranchRef.name", "command -v *")
    #: The permission rules the Permissions check reads, and the trust entries the Trust check reads.
    CLAUDE_FILES = ("~/.claude.json", "~/.claude/settings.json", "//etc/claude-code/managed-settings.json",
                    "//Library/Application Support/ClaudeCode/managed-settings.json")

    def __init__(self, plugin_root: Path, job_dir: Path, repos: Iterable[str], config_dir: Path):
        self.plugin_root = Path(plugin_root)
        self.cure_job = self.plugin_root / CURE_JOB
        self.job_dir = Path(job_dir)
        self.repos = tuple(repos)
        self.config_dir = Path(config_dir)

    def allow(self) -> list[str]:
        job_id = self.job_dir.name
        goal = self.job_dir / "goal.md"
        return ([f"Bash({cure_job} drafted {job_id} *)" for cure_job in self._cure_jobs()]
                + [f"Bash({cure_job} drafted --help)" for cure_job in self._cure_jobs()]
                + [f"Bash({cure_job} {command} *)" for cure_job in self._cure_jobs() for command in self.READS]
                + [f"Bash({command})" for command in self.COMMANDS]
                + ["Bash(wc -c *)", "Skill(cure:goal)", "SendMessage", f"Edit({_absolute(goal)})"]
                + [f"Read({_absolute(directory)}/**)"
                   for directory in (self.job_dir.parent, self.plugin_root, *map(Path, self.repos))]
                + [f"Read({_absolute(self.config_dir / 'question-policies.md')})"]
                + [f"Read({path})" for path in self.CLAUDE_FILES])

    def deny(self) -> list[str]:
        return (["Bash(claude *)"]
                + [f"Bash({cure_job} {command} *)" for cure_job in self._cure_jobs() for command in self.DENIED]
                + [f"Edit({_absolute(Path(repo))}/**)" for repo in self.repos])

    def arguments(self) -> list[str]:
        settings = {"permissions": {"allow": self.allow(), "deny": self.deny()}}
        return ["--settings", json.dumps(settings, separators=(",", ":"))]

    def _cure_jobs(self) -> tuple[str, ...]:
        return self.BARE, str(self.cure_job)


def _absolute(path: Path) -> str:
    """``path`` in a permission rule, where a single leading ``/`` is relative to the settings file."""
    return "/" + str(path)
