"""Test doubles for the two seams of ``JobsProvider``: the ``claude`` binary and the clock."""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Sequence

from cure_job.claude import SessionStatus
from cure_job.errors import ClaudeError


class FakeClaude:
    """In-process ``Claude``.

    ``statuses`` is what ``sessions()`` reports (the method owns the name ``sessions``); tests mutate it to
    model a busy, idle or stopped session, or a vanished one (deleted). ``start`` records the call and
    marks the session BUSY."""

    def __init__(self, statuses: dict[str, SessionStatus] | None = None):
        self.statuses: dict[str, SessionStatus] = dict(statuses or {})
        self.started: list[tuple[str, str, str, tuple[str, ...]]] = []
        self.sessions_calls = 0
        self.fail_sessions: ClaudeError | None = None
        self.fail_start: ClaudeError | None = None

    def sessions(self) -> dict[str, SessionStatus]:
        self.sessions_calls += 1
        if self.fail_sessions is not None:
            raise self.fail_sessions
        return dict(self.statuses)

    def start(self, name: str, cwd: str, prompt: str, extra_args: Sequence[str] = ()) -> None:
        if self.fail_start is not None:
            raise self.fail_start
        self.started.append((name, cwd, prompt, tuple(extra_args)))
        self.statuses[name] = SessionStatus.BUSY


class FakeClock:
    """A settable clock. ``advance`` moves time forward between operations."""

    def __init__(self, now: datetime):
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta
