"""Issue 126: cure-job marks the directory of a job session trusted in ``~/.claude.json`` before the start."""
from __future__ import annotations

import fcntl
import json
import os
import threading
from pathlib import Path

import pytest

from cure_job import trust
from cure_job.claude import SessionStatus
from cure_job.errors import CureJobError
from tests.test_approve import NEEDS_INPUT_RESULT
from tests.test_cli import Harness

DIR = "/home/u/dev/worktrees/repo/job"


@pytest.fixture
def claude_json(tmp_path) -> Path:
    return tmp_path / "home" / ".claude.json"


def write(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_trust_writes_an_absent_entry_and_keeps_every_other_key(claude_json):
    write(claude_json, {"numStartups": 7, "projects": {"/other": {"hasTrustDialogAccepted": False, "x": 1}}})
    trust.mark_trusted(DIR)
    assert read(claude_json) == {"numStartups": 7, "projects": {
        "/other": {"hasTrustDialogAccepted": False, "x": 1}, DIR: {"hasTrustDialogAccepted": True}}}


def test_trust_keeps_the_other_keys_of_the_project_entry(claude_json):
    write(claude_json, {"projects": {DIR: {"allowedTools": ["Bash"], "hasTrustDialogAccepted": False}}})
    trust.mark_trusted(DIR)
    assert read(claude_json) == {"projects": {DIR: {"allowedTools": ["Bash"], "hasTrustDialogAccepted": True}}}


def test_trust_adds_the_projects_object_when_absent(claude_json):
    write(claude_json, {"theme": "dark"})
    trust.mark_trusted(DIR)
    assert read(claude_json) == {"theme": "dark", "projects": {DIR: {"hasTrustDialogAccepted": True}}}


def test_trust_already_accepted_leaves_the_file_untouched(claude_json):
    claude_json.write_text('{"projects": {"%s": {"hasTrustDialogAccepted": true}}}' % DIR, encoding="utf-8")
    before = claude_json.stat()
    trust.mark_trusted(DIR)
    after = claude_json.stat()
    assert (after.st_ino, after.st_mtime_ns) == (before.st_ino, before.st_mtime_ns)


def test_trust_keeps_the_file_mode_and_leaves_no_temporary_file(claude_json):
    write(claude_json, {})
    claude_json.chmod(0o600)
    trust.mark_trusted(DIR)
    assert claude_json.stat().st_mode & 0o777 == 0o600
    assert [p.name for p in claude_json.parent.iterdir()] == [".claude.json"]


def test_trust_writes_through_a_symlink_to_its_target(claude_json, tmp_path):
    target = tmp_path / "dotfiles" / "claude.json"
    target.parent.mkdir()
    write(target, {})
    claude_json.symlink_to(target)
    trust.mark_trusted(DIR)
    assert claude_json.is_symlink()
    assert read(target) == {"projects": {DIR: {"hasTrustDialogAccepted": True}}}


def test_trust_keys_the_project_by_the_real_path_of_the_directory(claude_json, tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    (tmp_path / "link").symlink_to(real)
    write(claude_json, {})
    trust.mark_trusted(str(tmp_path / "link"))
    assert read(claude_json) == {"projects": {str(real): {"hasTrustDialogAccepted": True}}}


def test_trust_waits_for_the_lock_and_keeps_the_entry_written_meanwhile(claude_json):
    write(claude_json, {})
    lock = os.open(claude_json.parent, os.O_RDONLY | os.O_DIRECTORY)
    fcntl.flock(lock, fcntl.LOCK_EX)
    worker = threading.Thread(target=trust.mark_trusted, args=(DIR,))
    try:
        worker.start()
        worker.join(0.3)
        assert worker.is_alive()
        write(claude_json, {"projects": {"/other": {"hasTrustDialogAccepted": True}}})
    finally:
        os.close(lock)
    worker.join(5)
    assert not worker.is_alive()
    assert read(claude_json)["projects"] == {"/other": {"hasTrustDialogAccepted": True},
                                             DIR: {"hasTrustDialogAccepted": True}}


def test_trust_skips_a_missing_file(claude_json):
    trust.mark_trusted(DIR)
    assert not claude_json.exists()


@pytest.mark.parametrize("text", ["{", "[]", '{"projects": []}', '{"projects": {"%s": 1}}' % DIR])
def test_trust_refuses_a_file_it_cannot_update_and_leaves_it(claude_json, text):
    claude_json.write_text(text, encoding="utf-8")
    with pytest.raises(CureJobError):
        trust.mark_trusted(DIR)
    assert claude_json.read_text(encoding="utf-8") == text


def test_launch_and_resume_trust_the_session_directory(root, tmp_path, claude_json):
    h = Harness(root)
    write(claude_json, {"keep": True})
    job_id = h.new(tmp_path)
    h.approve(job_id)
    assert h.run("launch", job_id) == 0
    cwd = h.claude.started[-1][1]
    key = os.path.realpath(cwd)
    assert read(claude_json) == {"keep": True, "projects": {key: {"hasTrustDialogAccepted": True}}}
    write(claude_json, {"keep": True})
    (root / "jobs" / job_id / "result.md").write_text(NEEDS_INPUT_RESULT, encoding="utf-8")
    h.claude.statuses[job_id] = SessionStatus.IDLE
    assert h.run("resume", job_id) == 0
    assert h.claude.resumed[-1][2] == cwd
    assert read(claude_json) == {"keep": True, "projects": {key: {"hasTrustDialogAccepted": True}}}


def test_a_launch_refused_by_trust_starts_no_session(root, tmp_path, claude_json):
    h = Harness(root)
    claude_json.write_text("{", encoding="utf-8")
    job_id = h.new(tmp_path)
    h.approve(job_id)
    assert h.run("launch", job_id) == 1
    assert h.claude.started == []
