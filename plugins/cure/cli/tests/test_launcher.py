"""The ``bin/cure-job`` launcher run as a subprocess, and the design note's CLI check end to end."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from tests.builders import handoff_text
from tests.conftest import FAKE_CLAUDE

LAUNCHER = Path(__file__).resolve().parents[2] / "bin" / "cure-job"
COMMANDS = ["new", "list", "launch", "claim", "close", "prune"]


@pytest.fixture
def workdir(tmp_path):
    """A directory outside the repository: the launcher must not depend on the working directory."""
    path = tmp_path / "elsewhere"
    path.mkdir()
    return path


def run(workdir, *argv, stdin=None):
    return subprocess.run([str(LAUNCHER), *argv], cwd=workdir, input=stdin, capture_output=True, text=True,
                          timeout=60, env=dict(os.environ))


def list_states(workdir):
    done = run(workdir, "list", "--json")
    assert done.returncode == 0, done.stderr
    return [(item["id"], item["state"]) for item in json.loads(done.stdout)]


def test_launcher_is_executable_python_script():
    assert LAUNCHER.stat().st_mode & 0o111
    assert LAUNCHER.read_text(encoding="utf-8").startswith("#!/usr/bin/env python3")


def test_help_lists_the_six_commands(workdir):
    done = run(workdir, "--help")
    assert done.returncode == 0
    for name in COMMANDS:
        assert name in done.stdout


def test_bare_launcher_prints_help_and_exits_zero(workdir):
    done = run(workdir)
    assert done.returncode == 0
    assert "new" in done.stdout


def test_launcher_works_without_pythonpath(workdir):
    assert "PYTHONPATH" not in os.environ
    assert run(workdir, "list").returncode == 0


def test_launcher_followed_through_a_symlink(tmp_path, workdir):
    link = tmp_path / "linked-cure-job"
    link.symlink_to(LAUNCHER)
    done = subprocess.run([str(link), "--help"], cwd=workdir, capture_output=True, text=True, timeout=60)
    assert done.returncode == 0 and "prune" in done.stdout


def test_exit_codes_through_the_launcher(workdir):
    assert run(workdir, "bogus").returncode == 2
    missing = run(workdir, "close", "261013-1800-repo-nothing")
    assert missing.returncode == 1
    assert missing.stderr.startswith("error: ")


def test_cli_check_scenario(tmp_path, workdir, root, fake_state):
    repo = tmp_path / "repo"
    repo.mkdir()
    handoff = tmp_path / "handoff.md"
    handoff.write_text(handoff_text((str(repo),)), encoding="utf-8")

    # Step 1: two jobs for one repository.
    created = run(workdir, "new", "--slug", "check", str(handoff)).stdout.splitlines()
    first = created[0]
    assert created[1:] == [f'notify: SendMessage dispatcher "job {first}"']
    created = run(workdir, "new", "--slug", "check", str(handoff)).stdout.splitlines()
    second = created[0]
    assert second == first + "-2"
    assert created[1:] == [f'notify: SendMessage dispatcher "job {second}"']
    assert list_states(workdir) == [(first, "queued"), (second, "queued")]

    # Step 2: the dispatcher writes goal.md and approves it.
    (root / "jobs" / first / "goal.md").write_text("goal", encoding="utf-8")
    assert list_states(workdir) == [(first, "awaiting-approval"), (second, "queued")]
    assert run(workdir, "approve", first, "--by", "user").returncode == 0
    assert list_states(workdir) == [(first, "approved"), (second, "held")]

    # Step 3: launch through the fake claude.
    launched = run(workdir, "launch", first)
    assert launched.returncode == 0, launched.stderr
    assert launched.stdout.strip() == first
    assert list_states(workdir) == [(first, "running"), (second, "held")]
    calls = [json.loads(line) for line in (fake_state / "calls.jsonl").read_text(encoding="utf-8").splitlines()]
    start = [call for call in calls if call["argv"][0] == "--bg"][0]
    assert start["argv"][:3] == ["--bg", "--name", first]
    assert start["argv"][-1] == f"/goal @{root / 'jobs' / first / 'goal.md'}"
    assert start["cwd"] == str(repo.resolve())

    # Step 4: the job session writes result.md.
    (root / "jobs" / first / "result.md").write_text("---\nstatus: done\n---\n", encoding="utf-8")
    assert list_states(workdir) == [(first, "done"), (second, "queued")]

    # Step 5: close the second job; prune keeps both, since the sessions of the closed one are not removed.
    assert run(workdir, "close", second).returncode == 0
    assert list_states(workdir) == [(first, "done"), (second, "abandoned")]
    pruned = run(workdir, "prune")
    assert pruned.returncode == 0 and pruned.stdout == ""

    # Once its sessions are removed, the abandoned job is pruned at once.
    assert run(workdir, "remove-sessions", second).returncode == 0
    pruned = run(workdir, "prune")
    assert pruned.stdout.split() == [second]
    assert list_states(workdir) == [(first, "done")]


def test_isolation_fixture_points_the_seams_at_temporary_paths(tmp_path):
    assert os.environ["CURE_JOB_CLAUDE"] == str(FAKE_CLAUDE)
    assert os.environ["CURE_JOB_ROOT"].startswith(str(tmp_path))
    assert os.environ["HOME"].startswith(str(tmp_path))
    assert os.environ["FAKE_CLAUDE_STATE"].startswith(str(tmp_path))
