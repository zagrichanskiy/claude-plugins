"""Test doubles for the two seams of ``JobsProvider``: the ``claude`` binary and the clock."""
from __future__ import annotations

import zlib
from datetime import datetime, timedelta
from typing import Sequence

from cure_job.claude import Session, SessionStatus
from cure_job.errors import ClaudeError


def fake_id(name: str) -> str:
    """The 8-hex listing ``id`` the fake gives the live session ``name``."""
    return f"{zlib.crc32(name.encode()):08x}"


def fake_uuid(name: str) -> str:
    """The ``sessionId`` the fake gives the session ``name``."""
    return f"uuid-{fake_id(name)}"


class FakeClaude:
    """In-process ``Claude``.

    ``statuses`` is what ``sessions()`` reports (the method owns the name ``sessions``); tests mutate it to
    model a busy, waiting, idle or stopped session, or a vanished one (deleted). ``waiting_for`` holds the
    ``waitingFor`` of a session. A live session gets the id ``fake_id(name)``. ``start`` records the call and
    marks the session BUSY; ``stop`` records the id and marks its session STOPPED. ``resume`` records the call
    and marks the session of the uuid BUSY; ``uuids`` overrides the ``sessionId`` of a session; ``remove`` records the id and deletes its session."""

    def __init__(self, statuses: dict[str, SessionStatus] | None = None):
        self.statuses: dict[str, SessionStatus] = dict(statuses or {})
        self.waiting_for: dict[str, str] = {}
        self.uuids: dict[str, str | None] = {}
        self.started: list[tuple[str, str, str, tuple[str, ...]]] = []
        self.stopped: list[str] = []
        self.resumed: list[tuple[str, str, str, str, tuple[str, ...]]] = []
        self.removed: list[str] = []
        self.sessions_calls = 0
        self.fail_sessions: ClaudeError | None = None
        self.fail_start: ClaudeError | None = None

    def sessions(self) -> dict[str, Session]:
        self.sessions_calls += 1
        if self.fail_sessions is not None:
            raise self.fail_sessions
        return {name: Session(status, self.waiting_for.get(name),
                              () if status is SessionStatus.STOPPED else (fake_id(name),),
                              (fake_id(name),), self.uuids.get(name, fake_uuid(name)))
                for name, status in self.statuses.items()}

    def stop(self, session_id: str) -> None:
        self.stopped.append(session_id)
        for name in self.statuses:
            if fake_id(name) == session_id:
                self.statuses[name] = SessionStatus.STOPPED

    def start(self, name: str, cwd: str, prompt: str, extra_args: Sequence[str] = ()) -> None:
        if self.fail_start is not None:
            raise self.fail_start
        self.started.append((name, cwd, prompt, tuple(extra_args)))
        self.statuses[name] = SessionStatus.BUSY

    def resume(self, name: str, uuid: str, cwd: str, prompt: str, extra_args: Sequence[str] = ()) -> None:
        if self.fail_start is not None:
            raise self.fail_start
        self.resumed.append((name, uuid, cwd, prompt, tuple(extra_args)))
        for name in self.statuses:
            if fake_uuid(name) == uuid:
                self.statuses[name] = SessionStatus.BUSY

    def remove(self, session_id: str) -> None:
        self.removed.append(session_id)
        for name in [name for name in self.statuses if fake_id(name) == session_id]:
            del self.statuses[name]


class FakeClock:
    """A settable clock. ``advance`` moves time forward between operations."""

    def __init__(self, now: datetime):
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, delta: timedelta) -> None:
        self.now += delta
