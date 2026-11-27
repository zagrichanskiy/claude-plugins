"""Issue 131: the claim ``main`` and the PreToolUse hook that denies a write under the main workspace.

Assumed interface: ``cure-job main-claim SESSION`` exits 0 when SESSION holds ``main`` and 1 with
``held by <session>`` when another session does; ``cure-job main-release SESSION`` ends SESSION's claim.
``hooks/main-claim-check.sh`` reads the PreToolUse payload (``session_id``, ``cwd``, ``tool_name``,
``tool_input``), prints nothing to allow, and prints a ``permissionDecision: deny`` document to deny.
A workspace directly under ``slots.root`` is a slot, never the main workspace.
"""
from __future__ import annotations

import json
import os
import subprocess

import pytest

from cure_job.goal import PLUGIN_ROOT
from tests.test_cli import Harness
from tests.test_config import configure

HOOK = PLUGIN_ROOT / "hooks" / "main-claim-check.sh"


@pytest.fixture
def h(root, tmp_path, monkeypatch):
    harness = Harness(root)
    configure(harness, {"slots": {"root": str(tmp_path / "slots")}})
    monkeypatch.setenv("CURE_JOB_CONFIG", str(root / "config.json"))
    return harness


@pytest.fixture
def main_ws(tmp_path):
    (tmp_path / "ws" / ".repo").mkdir(parents=True)
    (tmp_path / "ws" / "sources" / "app").mkdir(parents=True)
    (tmp_path / "ws" / "build").mkdir()
    return tmp_path / "ws"


def hook(session, tool, cwd, **tool_input):
    payload = {"session_id": session, "cwd": str(cwd), "tool_name": tool, "tool_input": tool_input}
    done = subprocess.run(["sh", str(HOOK)], input=json.dumps(payload), capture_output=True, text=True,
                          env={"CLAUDE_PLUGIN_ROOT": str(PLUGIN_ROOT), "PATH": "/usr/bin:/bin", **env()})
    assert done.returncode == 0
    return json.loads(done.stdout)["hookSpecificOutput"]["permissionDecision"] if done.stdout else "allow"


def env():
    return {key: os.environ[key] for key in ("HOME", "CURE_JOB_ROOT", "CURE_JOB_CONFIG")}


def writes(ws):
    app = ws / "sources" / "app"
    return [("Edit", app, {"file_path": str(app / "main.c")}),
            ("Write", app, {"file_path": str(app / "new.c")}),
            ("Bash", app, {"command": "git commit -m fix"}),
            ("Bash", ws / "build", {"command": "bitbake core-image"})]


def test_the_claim_is_held_by_one_session_until_released(h, capsys):
    assert h.run("main-claim", "s1") == 0
    assert h.run("main-claim", "s1") == 0
    assert h.run("main-claim", "s2") == 1
    assert "held by s1" in capsys.readouterr().err
    assert h.run("main-release", "s2") == 0
    assert h.run("main-claim", "s2") == 1
    assert h.run("main-release", "s1") == 0
    assert h.run("main-claim", "s2") == 0


@pytest.mark.parametrize("index", range(4))
def test_a_session_without_the_claim_is_denied_a_write_in_the_main_workspace(h, main_ws, index):
    tool, cwd, tool_input = writes(main_ws)[index]
    assert hook("s1", tool, cwd, **tool_input) == "deny"


def test_a_session_holding_another_claim_is_denied(h, main_ws):
    assert h.run("main-claim", "s2") == 0
    assert hook("s1", "Edit", main_ws, file_path=str(main_ws / "f")) == "deny"


@pytest.mark.parametrize("index", range(4))
def test_a_session_holding_main_is_allowed_every_write(h, main_ws, index):
    assert h.run("main-claim", "s1") == 0
    tool, cwd, tool_input = writes(main_ws)[index]
    assert hook("s1", tool, cwd, **tool_input) == "allow"


def test_a_released_claim_denies_the_session_again(h, main_ws):
    assert h.run("main-claim", "s1") == 0
    assert h.run("main-release", "s1") == 0
    assert hook("s1", "Edit", main_ws, file_path=str(main_ws / "f")) == "deny"


@pytest.mark.parametrize("tool, tool_input", [
    ("Read", {"file_path": "f"}),
    ("Grep", {"pattern": "x"}),
    ("Bash", {"command": "git status"}),
    ("Bash", {"command": "git log --oneline"}),
    ("Bash", {"command": "ls"}),
])
def test_a_read_in_the_main_workspace_needs_no_claim(h, main_ws, tool, tool_input):
    assert hook("s1", tool, main_ws / "sources" / "app", **tool_input) == "allow"


def test_a_write_in_a_slot_or_outside_any_workspace_needs_no_claim(h, tmp_path):
    (tmp_path / "slots" / "1" / ".repo").mkdir(parents=True)
    (tmp_path / "elsewhere").mkdir()
    assert hook("s1", "Edit", tmp_path / "slots" / "1", file_path=str(tmp_path / "slots" / "1" / "f")) == "allow"
    assert hook("s1", "Bash", tmp_path / "slots" / "1", command="bitbake x") == "allow"
    assert hook("s1", "Edit", tmp_path / "elsewhere", file_path=str(tmp_path / "elsewhere" / "f")) == "allow"


def hook_reason(session, tool, cwd, **tool_input):
    payload = {"session_id": session, "cwd": str(cwd), "tool_name": tool, "tool_input": tool_input}
    done = subprocess.run(["sh", str(HOOK)], input=json.dumps(payload), capture_output=True, text=True,
                          env={"CLAUDE_PLUGIN_ROOT": str(PLUGIN_ROOT), "PATH": "/usr/bin:/bin", **env()})
    return json.loads(done.stdout)["hookSpecificOutput"]["permissionDecisionReason"]


def test_a_write_under_the_worktree_root_is_never_denied_inside_the_main_workspace(h, main_ws, root):
    inside = main_ws / "worktrees"
    configure(h, {"slots": {"root": str(main_ws.parent / "slots")}, "worktree": {"root": str(inside)}})
    target = inside / "job" / "sources" / "app"
    target.mkdir(parents=True)
    assert hook("s1", "Edit", target, file_path=str(target / "f.c")) == "allow"
    assert hook("s1", "Bash", target, command="git commit -m x") == "allow"
    assert hook("s1", "Edit", main_ws, file_path=str(main_ws / "f")) == "deny"


@pytest.mark.parametrize("command", [
    "git symbolic-ref HEAD", "git reflog", "git remote -v", "git remote get-url origin", "git tag -l",
    "git worktree list", "git fetch", "repo status", "repo info", "repo list", "repo manifest", "repo diff",
    "repo branches",
])
def test_these_read_commands_in_the_main_workspace_need_no_claim(h, main_ws, command):
    assert hook("s1", "Bash", main_ws / "sources" / "app", command=command) == "allow"


@pytest.mark.parametrize("command", ["repo sync", "repo start x --all", "repo forall -c 'git checkout x'"])
def test_these_repo_commands_in_the_main_workspace_need_the_claim(h, main_ws, command):
    assert hook("s1", "Bash", main_ws, command=command) == "deny"
    assert h.run("main-claim", "s1") == 0
    assert hook("s1", "Bash", main_ws, command=command) == "allow"


def test_the_denial_while_another_session_holds_main_names_the_release_command(h, main_ws):
    assert h.run("main-claim", "s2") == 0
    assert "cure-job main-release s2" in hook_reason("s1", "Edit", main_ws, file_path=str(main_ws / "f"))


def test_a_refused_claim_names_the_release_command(h, capsys):
    assert h.run("main-claim", "s2") == 0
    assert h.run("main-claim", "s1") == 1
    assert "cure-job main-release s2" in capsys.readouterr().err


def test_the_session_end_hook_releases_the_claim_of_its_session(h, main_ws):
    command = json.loads((PLUGIN_ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))[
        "hooks"]["SessionEnd"][0]["hooks"][0]["command"]
    assert h.run("main-claim", "s1") == 0
    done = subprocess.run(["sh", "-c", command], input=json.dumps({"session_id": "s1"}), capture_output=True,
                          text=True, env={"CLAUDE_PLUGIN_ROOT": str(PLUGIN_ROOT), "PATH": "/usr/bin:/bin", **env()})
    assert done.returncode == 0, done.stderr
    assert h.run("main-claim", "s2") == 0


def test_a_fetch_that_updates_a_local_branch_needs_the_claim(h, main_ws):
    cwd = main_ws / "sources" / "app"
    assert hook("s1", "Bash", cwd, command="git fetch origin main:main") == "deny"
    assert h.run("main-claim", "s1") == 0
    assert hook("s1", "Bash", cwd, command="git fetch origin main:main") == "allow"


@pytest.mark.parametrize("command, decision", [("git fetch", "allow"), ("git fetch origin", "allow"),
                                               ("git tag", "allow"), ("git tag v1", "deny")])
def test_fetch_without_a_refspec_and_bare_tag_listing_need_no_claim(h, main_ws, command, decision):
    assert hook("s1", "Bash", main_ws / "sources" / "app", command=command) == decision
