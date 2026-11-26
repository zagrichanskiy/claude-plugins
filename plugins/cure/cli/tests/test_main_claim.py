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
from cure_job.kinds import CURE_JOB
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


def denied_then_allowed_with_claim(h, cwd, command):
    assert hook("s1", "Bash", cwd, command=command) == "deny"
    assert h.run("main-claim", "s1") == 0
    assert hook("s1", "Bash", cwd, command=command) == "allow"


def test_a_fetch_that_updates_a_local_branch_needs_the_claim(h, main_ws):
    denied_then_allowed_with_claim(h, main_ws / "sources" / "app", "git fetch origin main:main")


READS = ["git status", "git log --oneline", "git diff HEAD", "git show HEAD", "git branch", "git branch -a",
         "git branch -r", "git branch -v", "git branch --show-current", "git rev-parse HEAD", "git ls-files",
         "git grep x", "git blame f.c", "git remote -v", "ls -la", "cat f.c", "head -n 3 f.c", "tail f.c",
         "grep -rn x .", "rg x", "find . -name '*.c'", "wc -l f.c", "stat f.c", "file f.c"]


@pytest.mark.parametrize("command", READS)
def test_an_allowlisted_read_in_the_main_workspace_needs_no_claim(h, main_ws, command):
    assert hook("s1", "Bash", main_ws / "sources" / "app", command=command) == "allow"


@pytest.mark.parametrize("metacharacter", [";", "&", "|", "<", ">", "$(", "`", "\\\n", "\n"])
def test_a_shell_metacharacter_turns_an_allowed_read_into_a_write(h, main_ws, metacharacter):
    denied_then_allowed_with_claim(h, main_ws / "sources" / "app", f"ls a{metacharacter}b")


@pytest.mark.parametrize("command", [
    "git commit -m m", "git --git-dir APP/.git commit -m m", "git -C APP commit -m m", "env git commit -m m",
    "sudo git commit -m m", "bash -c 'git commit -m m'", "sh -c 'git commit -m m'", "bash <<EOF\ngit commit\nEOF",
    "git fetch", "git fetch --tags", "git fetch --depth 1 git@host:team/x.git", "git fetch origin tag v1",
    "git remote add o url", "find . -exec rm {} +", "find . -delete", "git tag v1", "git reflog", "repo status",
    "repo sync", "bitbake core-image", "touch f", "/usr/bin/make", "env git status", "bash -c 'git status'"])
def test_a_command_outside_the_read_allowlist_needs_the_claim(h, main_ws, command):
    app = main_ws / "sources" / "app"
    denied_then_allowed_with_claim(h, app, command.replace("APP", str(app)))


@pytest.mark.parametrize("command", [
    "git branch newname", "git branch -D x", "git branch -m a b", "git diff --output=f", "git log --output f",
    "git grep -O vim x", "git grep --open-files-in-pager=vim x", "rg --pre cat x", "rg --pre=cat x", "ls $HOME",
    "cat ${X}"])
def test_an_allowlisted_command_with_a_writing_or_executing_option_or_a_dollar_needs_the_claim(h, main_ws, command):
    denied_then_allowed_with_claim(h, main_ws / "sources" / "app", command)


@pytest.mark.parametrize("where, command", [("main", "./build.sh"), ("outside", "SCRIPT"), ("outside", "sh SCRIPT"),
                                             ("main", "sh SCRIPT")])
def test_a_command_that_runs_a_script_in_the_main_workspace_needs_the_claim(h, main_ws, tmp_path, where, command):
    script = main_ws / "build.sh"
    script.write_text("#!/bin/sh\nbitbake core-image\n", encoding="utf-8")
    script.chmod(0o755)
    (tmp_path / "outside").mkdir()
    denied_then_allowed_with_claim(h, main_ws if where == "main" else tmp_path / "outside",
                                   command.replace("SCRIPT", str(script)))


@pytest.mark.parametrize("subcommand", ["main-claim", "main-release"])
def test_the_claim_commands_are_allowed_without_the_claim_unless_chained(h, main_ws, subcommand):
    command = f"{PLUGIN_ROOT / CURE_JOB} {subcommand} s1"
    assert hook("s1", "Bash", main_ws / "sources" / "app", command=command) == "allow"
    denied_then_allowed_with_claim(h, main_ws / "sources" / "app", f"{command} ; touch f")


@pytest.mark.parametrize("word", ["LONG", "LOCKED"])
def test_a_path_word_that_cannot_be_inspected_still_gets_a_decision(h, main_ws, tmp_path, word):
    locked = tmp_path / "locked"
    locked.mkdir()
    (locked / "x").write_text("", encoding="utf-8")
    locked.chmod(0)
    try:
        word = word.replace("LONG", str(tmp_path / ("a" * 300))).replace("LOCKED", str(locked / "x"))
        assert hook("s1", "Bash", tmp_path, command=f"touch {word} {main_ws}/f") == "deny"
    finally:
        locked.chmod(0o700)


@pytest.mark.parametrize("command", [
    "file -C -m m/x", "file --compile -m m/x", "rg --hostname-bin=./build.sh --hyperlink-format=default x",
    "git diff '--output=f'", "git diff --out\\put=f", "git diff --outp=f", "find . -fprint f",
    "git -c x=y status", "git --no-pager log"])
def test_an_option_that_writes_or_executes_is_denied_however_it_is_spelled(h, main_ws, command):
    denied_then_allowed_with_claim(h, main_ws / "sources" / "app", command)


def test_a_git_directory_option_with_an_attached_value_is_a_path_under_the_root(h, main_ws, tmp_path):
    (tmp_path / "outside").mkdir()
    denied_then_allowed_with_claim(h, tmp_path / "outside", f"git -C{main_ws}/sources/app commit -m m")


@pytest.mark.parametrize("command, decision", [
    ("cat APP/f.c", "allow"), ("git -C APP commit -m m", "deny"), ("touch APP/f", "deny"), ("rm -rf APP/x", "deny"),
    ("env -C APP git commit -m m", "deny"), ("sudo --chdir=APP git commit -m m", "deny"),
    ("cat OUT/f.c", "allow"), ("touch OUT/f", "allow"), ("git commit -m m", "allow"), ("echo hello", "allow")])
def test_only_a_command_with_an_argument_under_the_root_is_held_to_the_rule(h, main_ws, tmp_path, command, decision):
    outside = tmp_path / "outside"
    outside.mkdir()
    command = command.replace("APP", str(main_ws / "sources/app")).replace("OUT", str(outside))
    assert hook("s1", "Bash", outside, command=command) == decision


def test_a_script_run_in_a_slot_or_worktree_needs_no_claim(h, main_ws, tmp_path):
    inside = main_ws / "worktrees"
    configure(h, {"slots": {"root": str(tmp_path / "slots")}, "worktree": {"root": str(inside)}})
    for base in (tmp_path / "slots" / "1", inside / "job"):
        (base / ".repo").mkdir(parents=True)
        script = base / "build.sh"
        script.write_text("#!/bin/sh\nbitbake x\n", encoding="utf-8")
        script.chmod(0o755)
        assert hook("s1", "Bash", base, command="./build.sh") == "allow"

