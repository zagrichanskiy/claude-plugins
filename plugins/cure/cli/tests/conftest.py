"""Isolation for every test: no real ``claude`` binary and nothing under the real home directory."""
from __future__ import annotations

from pathlib import Path

import pytest

FAKE_CLAUDE = Path(__file__).resolve().parent / "fake_claude.py"


@pytest.fixture(autouse=True)
def isolated_environment(tmp_path, monkeypatch):
    """Point the environment seams at temporary paths so even a stray ``main`` call is harmless."""
    home = tmp_path / "home"
    home.mkdir()
    state = tmp_path / "fake-claude-state"
    state.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("CURE_JOB_ROOT", str(tmp_path / "cure"))
    monkeypatch.setenv("CURE_JOB_CLAUDE", str(FAKE_CLAUDE))
    monkeypatch.setenv("CURE_JOB_CONFIG", str(tmp_path / "config" / "config.json"))
    monkeypatch.setenv("FAKE_CLAUDE_STATE", str(state))
    monkeypatch.delenv("PYTHONPATH", raising=False)


@pytest.fixture
def root(tmp_path) -> Path:
    return tmp_path / "cure"


@pytest.fixture
def fake_state(tmp_path) -> Path:
    return tmp_path / "fake-claude-state"
