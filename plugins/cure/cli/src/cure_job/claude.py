"""The ``claude`` binary seam.

``ClaudeCli`` is the only code that runs the binary. Everything else depends on
the :class:`Claude` protocol, so a test passes a fake.
"""
from __future__ import annotations

import json
import os
import shlex
import subprocess
from typing import Protocol, Sequence

from .errors import ClaudeError, ClaudeOutcomeUnknown


class Claude(Protocol):
    def sessions(self) -> dict[str, bool]:
        """Session name to alive, for every session the binary lists."""

    def start(self, name: str, cwd: str, prompt: str, extra_args: Sequence[str] = ()) -> None:
        """Start one background session. Returns when the binary has returned."""


class ClaudeCli:
    TIMEOUT_SECONDS = 60

    def __init__(self, binary: str):
        self.binary = binary

    def sessions(self) -> dict[str, bool]:
        argv = [self.binary, "agents", "--json", "--all"]
        stdout = self._run(argv)
        try:
            entries = json.loads(stdout)
        except ValueError:
            entries = None
        if not isinstance(entries, list):
            raise ClaudeError(f"{shlex.join(argv)}: the output is not a JSON array")
        alive: dict[str, bool] = {}
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
                continue
            # A stopped session stays listed under --all, without a pid. A name
            # may be listed more than once, and one live entry is enough.
            alive[entry["name"]] = alive.get(entry["name"], False) or "pid" in entry
        return alive

    def start(self, name: str, cwd: str, prompt: str, extra_args: Sequence[str] = ()) -> None:
        argv = [self.binary, "--bg", "--name", name, *extra_args, prompt]
        # Checked here: subprocess reports a missing cwd and a missing binary
        # with the same FileNotFoundError.
        if not os.path.isdir(cwd):
            raise ClaudeError(f"{shlex.join(argv)}: {cwd} is not a directory")
        self._run(argv, cwd=cwd)

    def _run(self, argv: list[str], cwd: str | None = None) -> str:
        command = shlex.join(argv)
        try:
            done = subprocess.run(argv, cwd=cwd, stdin=subprocess.DEVNULL, capture_output=True,
                                  text=True, errors="replace", timeout=self.TIMEOUT_SECONDS)
        except OSError as e:
            raise ClaudeError(f"{command}: cannot run: {e.strerror or e}") from e
        except subprocess.TimeoutExpired as e:
            raise ClaudeOutcomeUnknown(f"{command}: no exit within {self.TIMEOUT_SECONDS} seconds") from e
        if done.returncode != 0:
            raise ClaudeError(f"{command}: exit {done.returncode}{_first_line(done.stderr)}")
        return done.stdout


def _first_line(stderr: str) -> str:
    lines = stderr.strip().splitlines()
    return f": {lines[0]}" if lines else ""
