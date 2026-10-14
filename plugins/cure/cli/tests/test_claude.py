"""``ClaudeCli`` against the stand-in binary, ``false`` and a missing path. The real ``claude`` is never run."""
from __future__ import annotations

import json
import sys

import pytest

from cure_job.claude import ClaudeCli
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


def test_session_with_pid_is_alive_and_without_is_stopped(cli, fake_state):
    (fake_state / "agents.json").write_text(json.dumps([
        {"name": "live", "pid": 4242, "status": "busy"},
        {"name": "stopped", "state": "idle"},
    ]), encoding="utf-8")
    assert cli.sessions() == {"live": True, "stopped": False}


def test_name_listed_twice_is_alive_when_any_entry_is(cli, fake_state):
    (fake_state / "agents.json").write_text(json.dumps([
        {"name": "dup"}, {"name": "dup", "pid": 1}, {"name": "dup2", "pid": 1}, {"name": "dup2"},
    ]), encoding="utf-8")
    assert cli.sessions() == {"dup": True, "dup2": True}


def test_entries_without_a_string_name_are_skipped(cli, fake_state):
    (fake_state / "agents.json").write_text(json.dumps([
        {"pid": 1}, {"name": 5, "pid": 1}, "text", 3, {"name": "ok", "pid": 1},
    ]), encoding="utf-8")
    assert cli.sessions() == {"ok": True}


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


def test_started_session_is_listed_alive(cli, tmp_path):
    cli.start("job-1", str(tmp_path), "prompt")
    assert cli.sessions() == {"job-1": True}


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
