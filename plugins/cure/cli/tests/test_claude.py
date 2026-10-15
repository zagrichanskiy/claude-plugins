"""``ClaudeCli`` against the stand-in binary, ``false`` and a missing path. The real ``claude`` is never run."""
from __future__ import annotations

import json
import sys

import pytest

from cure_job.claude import ClaudeCli, SessionStatus
from cure_job.errors import ClaudeError
from tests.conftest import FAKE_CLAUDE


@pytest.fixture
def cli():
    return ClaudeCli(str(FAKE_CLAUDE))


def calls(fake_state):
    path = fake_state / "calls.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_fake_binary_is_executable():
    assert FAKE_CLAUDE.stat().st_mode & 0o111


def test_constructor_does_no_io():
    ClaudeCli("/nonexistent/claude")


def test_sessions_is_empty_without_agents_file(cli):
    assert cli.sessions() == {}


def test_sessions_runs_agents_json_all(cli, fake_state):
    cli.sessions()
    assert calls(fake_state)[0]["argv"] == ["agents", "--json", "--all"]


def write_agents(fake_state, entries):
    (fake_state / "agents.json").write_text(json.dumps(entries), encoding="utf-8")


# Field shapes as printed by `claude agents --json --all` on Claude Code 2.1.300.
@pytest.mark.parametrize("entry, expected", [
    ({"name": "n", "pid": 4242, "state": "idle", "status": "idle", "kind": "background"}, SessionStatus.IDLE),
    ({"name": "n", "pid": 4242, "state": "working", "status": "busy", "kind": "background"}, SessionStatus.BUSY),
    ({"name": "n", "pid": 4242, "state": "blocked", "status": "waiting", "kind": "background"}, SessionStatus.BUSY),
    ({"name": "n", "pid": 4242}, SessionStatus.BUSY),
    ({"name": "n", "pid": 4242, "status": "something-new"}, SessionStatus.BUSY),
    ({"name": "n", "kind": "background"}, SessionStatus.STOPPED),
    ({"name": "n", "state": "idle"}, SessionStatus.STOPPED),
])
def test_entry_maps_to_a_session_status(cli, fake_state, entry, expected):
    write_agents(fake_state, [entry])
    assert cli.sessions() == {"n": expected}


def test_unlisted_name_is_absent(cli, fake_state):
    write_agents(fake_state, [{"name": "listed", "pid": 1, "status": "idle"}])
    assert "other" not in cli.sessions()


@pytest.mark.parametrize("statuses, expected", [
    (("busy", "idle"), SessionStatus.BUSY),
    (("idle", "busy"), SessionStatus.BUSY),
    (("idle", "stopped"), SessionStatus.IDLE),
    (("stopped", "idle"), SessionStatus.IDLE),
    (("busy", "stopped"), SessionStatus.BUSY),
    (("stopped", "busy"), SessionStatus.BUSY),
    (("stopped", "stopped"), SessionStatus.STOPPED),
])
def test_name_listed_twice_takes_the_strongest_status_whatever_the_order(cli, fake_state, statuses, expected):
    shapes = {"busy": {"pid": 1, "status": "busy"}, "idle": {"pid": 2, "status": "idle"}, "stopped": {}}
    write_agents(fake_state, [{"name": "dup", **shapes[s]} for s in statuses])
    assert cli.sessions() == {"dup": expected}


def test_distinct_names_keep_their_own_status(cli, fake_state):
    write_agents(fake_state, [{"name": "a", "pid": 1, "status": "idle"}, {"name": "b", "pid": 2, "status": "busy"},
                              {"name": "c"}])
    assert cli.sessions() == {"a": SessionStatus.IDLE, "b": SessionStatus.BUSY, "c": SessionStatus.STOPPED}


def test_entries_without_a_string_name_are_skipped(cli, fake_state):
    (fake_state / "agents.json").write_text(json.dumps([
        {"pid": 1}, {"name": 5, "pid": 1}, "text", 3, {"name": "ok", "pid": 1},
    ]), encoding="utf-8")
    assert cli.sessions() == {"ok": SessionStatus.BUSY}


def test_sessions_rejects_output_that_is_not_a_json_array(cli, fake_state):
    (fake_state / "agents.json").write_text('{"name":"x"}', encoding="utf-8")
    with pytest.raises(ClaudeError):
        cli.sessions()


def test_sessions_rejects_output_that_is_not_json(cli, fake_state):
    (fake_state / "agents.json").write_text("not json", encoding="utf-8")
    with pytest.raises(ClaudeError):
        cli.sessions()


def test_start_runs_bg_with_name_extra_arguments_and_prompt_in_cwd(cli, fake_state, tmp_path):
    workdir = tmp_path / "work"
    workdir.mkdir()
    cli.start("job-1", str(workdir), "/goal @/x/goal.md", ["--add-dir", "/y"])
    call = calls(fake_state)[0]
    assert call["argv"] == ["--bg", "--name", "job-1", "--add-dir", "/y", "/goal @/x/goal.md"]
    assert call["cwd"] == str(workdir.resolve())


def test_start_without_extra_arguments(cli, fake_state, tmp_path):
    cli.start("job-1", str(tmp_path), "prompt")
    assert calls(fake_state)[0]["argv"] == ["--bg", "--name", "job-1", "prompt"]


def test_started_session_is_listed_busy(cli, tmp_path):
    cli.start("job-1", str(tmp_path), "prompt")
    assert cli.sessions() == {"job-1": SessionStatus.BUSY}


def test_start_with_a_cwd_that_is_not_a_directory_raises(cli, tmp_path):
    with pytest.raises(ClaudeError):
        cli.start("job-1", str(tmp_path / "absent"), "prompt")


def test_missing_binary_raises_claude_error(tmp_path):
    with pytest.raises(ClaudeError):
        ClaudeCli(str(tmp_path / "no-such-binary")).sessions()


def test_missing_binary_on_start_raises_claude_error(tmp_path):
    with pytest.raises(ClaudeError):
        ClaudeCli(str(tmp_path / "no-such-binary")).start("n", str(tmp_path), "p")


def test_non_zero_exit_raises_claude_error_naming_the_argv():
    with pytest.raises(ClaudeError, match="agents"):
        ClaudeCli("false").sessions()


def test_non_zero_exit_on_start_raises_claude_error(tmp_path):
    with pytest.raises(ClaudeError):
        ClaudeCli("false").start("n", str(tmp_path), "p")


def test_error_message_holds_the_first_stderr_line(tmp_path):
    script = tmp_path / "noisy"
    script.write_text(f"#!{sys.executable}\nimport sys\nsys.stderr.write('first line\\nsecond line\\n')\n"
                      "sys.exit(3)\n", encoding="utf-8")
    script.chmod(0o755)
    with pytest.raises(ClaudeError) as caught:
        ClaudeCli(str(script)).sessions()
    assert "first line" in str(caught.value)
    assert "second line" not in str(caught.value)


def test_timeout_raises_claude_error(tmp_path, monkeypatch):
    script = tmp_path / "slow"
    script.write_text(f"#!{sys.executable}\nimport time\ntime.sleep(30)\n", encoding="utf-8")
    script.chmod(0o755)
    monkeypatch.setattr(ClaudeCli, "TIMEOUT_SECONDS", 0.5)
    with pytest.raises(ClaudeError):
        ClaudeCli(str(script)).sessions()


def test_timeout_default_is_sixty_seconds():
    assert ClaudeCli.TIMEOUT_SECONDS == 60


def test_stdin_is_not_inherited(tmp_path):
    script = tmp_path / "reader"
    script.write_text(f"#!{sys.executable}\nimport sys\nsys.stdout.write('[]' if sys.stdin.read() == '' else 'x')\n",
                      encoding="utf-8")
    script.chmod(0o755)
    assert ClaudeCli(str(script)).sessions() == {}
