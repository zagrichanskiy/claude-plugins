"""The ``claude`` binary seam.

``ClaudeCli`` is the only code that runs the binary. Everything else depends on
the :class:`Claude` protocol, so a test passes a fake.
"""
from __future__ import annotations

import enum
import json
import os
import shlex
import subprocess
from dataclasses import dataclass
from typing import Protocol, Sequence

from .errors import ClaudeError, ClaudeOutcomeUnknown


class SessionStatus(enum.Enum):
    BUSY = "busy"
    WAITING = "waiting"
    IDLE = "idle"
    STOPPED = "stopped"


@dataclass(frozen=True)
class Session:
    """One session name as `claude agents --json --all` lists it.

    ``waiting_for`` is the strongest entry's ``waitingFor``. ``ids`` holds the
    listing ``id`` of every live entry under the name, strongest first; a live
    entry without a string ``id`` contributes ``""``. ``all_ids`` holds the
    listing ``id`` of every entry, live or stopped, in the same way. ``uuid`` is
    the strongest entry's ``sessionId``, which ``claude --resume`` takes.
    """
    status: SessionStatus
    waiting_for: str | None = None
    ids: tuple[str, ...] = ()
    all_ids: tuple[str, ...] = ()
    uuid: str | None = None


#: The key `claude agents --json` puts the status of a live session under, and
#: the values this module knows. A live entry with any other value, or none, is busy.
STATUS_KEY = "status"
_STATUSES = {"idle": SessionStatus.IDLE, "waiting": SessionStatus.WAITING}

#: A name listed more than once takes its strongest entry.
_STRENGTH = {SessionStatus.BUSY: 3, SessionStatus.WAITING: 2, SessionStatus.IDLE: 1, SessionStatus.STOPPED: 0}


class Claude(Protocol):
    def sessions(self) -> dict[str, Session]:
        """Session name to session, for every session the binary lists."""

    def start(self, name: str, cwd: str, prompt: str, extra_args: Sequence[str] = ()) -> None:
        """Start one background session. Returns when the binary has returned."""

    def stop(self, session_id: str) -> None:
        """Stop the live session whose listing ``id`` is ``session_id``."""

    def resume(self, name: str, uuid: str, cwd: str, prompt: str, extra_args: Sequence[str] = ()) -> None:
        """Continue the stopped session ``uuid`` in the background under ``name``. Returns when the binary returned."""

    def remove(self, session_id: str) -> None:
        """Delete the session whose listing ``id`` is ``session_id``, live or stopped."""


class ClaudeCli:
    TIMEOUT_SECONDS = 60

    def __init__(self, binary: str):
        self.binary = binary

    def sessions(self) -> dict[str, Session]:
        argv = [self.binary, "agents", "--json", "--all"]
        stdout = self._run(argv)
        try:
            entries = json.loads(stdout)
        except ValueError:
            entries = None
        if not isinstance(entries, list):
            raise ClaudeError(f"{shlex.join(argv)}: the output is not a JSON array")
        by_name: dict[str, list[tuple[SessionStatus, dict]]] = {}
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
                continue
            by_name.setdefault(entry["name"], []).append((_status(entry), entry))
        found: dict[str, Session] = {}
        for name, listed in by_name.items():
            # sort is stable: equal entries keep the listing order.
            listed.sort(key=lambda item: _STRENGTH[item[0]], reverse=True)
            status, strongest = listed[0]
            waiting_for = strongest.get("waitingFor")
            ids = tuple(_id(entry) for entry_status, entry in listed if entry_status is not SessionStatus.STOPPED)
            uuid = strongest.get("sessionId")
            found[name] = Session(status, waiting_for if isinstance(waiting_for, str) else None, ids,
                                  tuple(_id(entry) for _, entry in listed), uuid if isinstance(uuid, str) else None)
        return found

    def start(self, name: str, cwd: str, prompt: str, extra_args: Sequence[str] = ()) -> None:
        self._run_in([self.binary, "--bg", "--name", name, *extra_args, prompt], cwd)

    def resume(self, name: str, uuid: str, cwd: str, prompt: str, extra_args: Sequence[str] = ()) -> None:
        # Resuming a running session starts a copy, so the caller stops it first.
        # --name keeps the listed name, which every later operation looks up.
        self._run_in([self.binary, "--bg", "--resume", uuid, "--name", name, *extra_args, prompt], cwd)

    def stop(self, session_id: str) -> None:
        self._run([self.binary, "stop", session_id])

    def remove(self, session_id: str) -> None:
        self._run([self.binary, "rm", session_id])

    def _run_in(self, argv: list[str], cwd: str) -> None:
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


def _status(entry: dict) -> SessionStatus:
    # A stopped session stays listed under --all, without a pid.
    if "pid" not in entry:
        return SessionStatus.STOPPED
    value = entry.get(STATUS_KEY)
    # A list or an object is not hashable, and is not a known value either.
    return _STATUSES.get(value, SessionStatus.BUSY) if isinstance(value, str) else SessionStatus.BUSY


def _id(entry: dict) -> str:
    # The short `id`, which `claude stop` takes; not `sessionId`.
    value = entry.get("id")
    return value if isinstance(value, str) else ""


def _first_line(stderr: str) -> str:
    lines = stderr.strip().splitlines()
    return f": {lines[0]}" if lines else ""
