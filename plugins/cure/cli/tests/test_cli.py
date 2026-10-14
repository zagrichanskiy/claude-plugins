"""``Cli.run``: command surface, exit codes, ``list`` output, and ``main`` reading the environment."""
from __future__ import annotations

import io
import json
import os
import sys
from datetime import timedelta

import pytest

from cure_job import cli as cli_module
from cure_job.cli import Cli, main
from cure_job.errors import ClaudeError
from tests.builders import NOW, handoff_text
from tests.conftest import FAKE_CLAUDE
from tests.fakes import FakeClaude, FakeClock

COMMANDS = ["new", "list", "launch", "claim", "close", "prune"]


class Harness:
    def __init__(self, root):
        self.root = root
        self.claude = FakeClaude()
        self.clock = FakeClock(NOW)
        self.lines: list[str] = []
        self.cli = Cli(root=root, claude=self.claude, clock=self.clock, out=self.lines.append)

    def run(self, *argv: str) -> int:
        return self.cli.run(list(argv))

    def new(self, tmp_path, slug="x", repos=("/work/video-core",), device="none") -> str:
        """Create a job through the command line and return its id; each call is a minute later."""
        self.clock.advance(timedelta(minutes=1))
        source = tmp_path / "handoff.md"
        source.write_text(handoff_text(repos, device), encoding="utf-8")
        self.lines.clear()
        assert self.run("new", "--slug", slug, str(source)) == 0
        return self.lines[0]

    def approve(self, job_id: str) -> None:
        (self.root / "jobs" / job_id / "goal.md").write_text("goal", encoding="utf-8")


@pytest.fixture
def h(root):
    return Harness(root)


# --- surface and exit codes ---------------------------------------------------------------------------

def test_bare_invocation_prints_root_help_and_returns_zero(h, capsys):
    assert h.cli.run([]) == 0
    printed = capsys.readouterr().out + "".join(h.lines)
    for name in COMMANDS:
        assert name in printed


def test_dash_h_lists_the_six_commands_and_exits_zero(h, capsys):
    with pytest.raises(SystemExit) as caught:
        h.cli.run(["-h"])
    assert caught.value.code == 0
    out = capsys.readouterr().out
    assert "cure-job COMMAND" in out
    for name in COMMANDS:
        assert name in out


@pytest.mark.parametrize("name", COMMANDS)
def test_every_command_has_help(h, capsys, name):
    with pytest.raises(SystemExit) as caught:
        h.cli.run([name, "-h"])
    assert caught.value.code == 0
    assert f"cure-job {name}" in capsys.readouterr().out


@pytest.mark.parametrize("argv", [
    ["bogus"],
    ["--bogus"],
    ["new"],
    ["launch"],
    ["launch", "not-an-id"],
    ["claim", "261013-1800-video-core-x"],
    ["claim", "261013-1800-video-core-x", "relative/path"],
    ["close", "../etc"],
    ["list", "--bogus"],
])
def test_usage_errors_exit_two(h, capsys, argv):
    with pytest.raises(SystemExit) as caught:
        h.cli.run(argv)
    assert caught.value.code == 2
    assert capsys.readouterr().err


def test_slug_that_slugifies_to_nothing_exits_two(h, tmp_path, capsys):
    source = tmp_path / "handoff.md"
    source.write_text(handoff_text(), encoding="utf-8")
    with pytest.raises(SystemExit) as caught:
        h.cli.run(["new", "--slug", "!!!", str(source)])
    assert caught.value.code == 2


def test_domain_error_prints_error_line_on_stderr_and_returns_one(h, capsys):
    assert h.run("close", "261013-1800-video-core-nothing") == 1
    captured = capsys.readouterr()
    assert captured.err.startswith("error: ")
    assert "261013-1800-video-core-nothing" in captured.err
    assert captured.out == ""


def test_other_exceptions_are_not_caught(h, monkeypatch):
    def boom():
        raise RuntimeError("bug")
    monkeypatch.setattr(h.cli.jobs, "views", boom)
    with pytest.raises(RuntimeError):
        h.run("list")


# --- new ----------------------------------------------------------------------------------------------

def test_new_from_file_prints_the_id_alone(h, tmp_path):
    job_id = h.new(tmp_path, slug="FPS clamp")
    assert job_id == "261013-1801-video-core-fps-clamp"
    assert h.lines == [job_id]


@pytest.mark.parametrize("dash", [True, False])
def test_new_reads_stdin_when_file_is_dash_or_absent(h, monkeypatch, dash):
    monkeypatch.setattr(sys, "stdin", io.StringIO(handoff_text()))
    argv = ["new", "--slug", "x"] + (["-"] if dash else [])
    assert h.cli.run(argv) == 0
    assert h.lines == ["261013-1800-video-core-x"]


def test_new_with_invalid_handoff_returns_one(h, tmp_path, capsys):
    source = tmp_path / "bad.md"
    source.write_text("nothing", encoding="utf-8")
    assert h.run("new", "--slug", "x", str(source)) == 1
    assert "error:" in capsys.readouterr().err


# --- list ---------------------------------------------------------------------------------------------

def test_list_without_jobs_prints_nothing(h):
    assert h.run("list") == 0
    assert h.lines == []


def test_list_text_has_one_aligned_line_per_job_with_blocked_by(h, tmp_path):
    first = h.new(tmp_path, slug="a")
    second = h.new(tmp_path, slug="a-much-longer-slug")
    h.lines.clear()
    assert h.run("list") == 0
    width = len(second)
    assert h.lines == [f"{first.ljust(width)}  queued", f"{second}  held  blocked-by={first}"]


def test_list_text_joins_several_blockers_with_commas(h, tmp_path):
    first = h.new(tmp_path, repos=("/work/a",))
    second = h.new(tmp_path, repos=("/work/b",))
    third = h.new(tmp_path, repos=("/work/a", "/work/b"))
    h.lines.clear()
    h.run("list")
    assert h.lines[2].endswith(f"held  blocked-by={first},{second}")


def test_list_json_is_one_compact_line_with_kebab_case_keys(h, tmp_path):
    first = h.new(tmp_path)
    second = h.new(tmp_path)
    h.lines.clear()
    assert h.run("list", "--json") == 0
    assert len(h.lines) == 1 and "\n" not in h.lines[0]
    assert ", " not in h.lines[0] and ": " not in h.lines[0]
    data = json.loads(h.lines[0])
    assert [item["id"] for item in data] == [first, second]
    assert data[0] == {
        "id": first, "state": "queued", "dir": str(h.root / "jobs" / first), "run": 0, "session": None,
        "resources": ["/work/video-core"], "blocked-by": [], "problem": None}
    assert data[1]["state"] == "held" and data[1]["blocked-by"] == [first]


def test_list_json_reports_run_session_and_problem(h, tmp_path):
    job_id = h.new(tmp_path)
    h.approve(job_id)
    h.run("launch", job_id)
    (h.root / "jobs" / job_id / "result.md").write_text("garbage", encoding="utf-8")
    h.lines.clear()
    h.run("list", "--json")
    item = json.loads(h.lines[0])[0]
    assert item["state"] == "needs-input"
    assert item["run"] == 1 and item["session"] == job_id
    assert item["problem"]


def test_list_json_without_jobs_is_an_empty_array(h):
    h.run("list", "--json")
    assert h.lines == ["[]"]


# --- launch, claim, close, prune ------------------------------------------------------------------------

def test_launch_prints_the_session_name(h, tmp_path):
    job_id = h.new(tmp_path)
    h.approve(job_id)
    h.lines.clear()
    assert h.run("launch", job_id) == 0
    assert h.lines == [job_id]
    assert h.claude.started[0][0] == job_id


def test_launch_passes_arguments_after_double_dash_without_the_dash(h, tmp_path):
    job_id = h.new(tmp_path)
    h.approve(job_id)
    assert h.run("launch", job_id, "--", "--add-dir", "/work/other") == 0
    assert h.claude.started[0][3] == ("--add-dir", "/work/other")


def test_launch_of_a_held_job_returns_one(h, tmp_path, capsys):
    h.new(tmp_path)
    second = h.new(tmp_path)
    h.approve(second)
    assert h.run("launch", second) == 1
    assert "error:" in capsys.readouterr().err


def test_launch_claude_failure_returns_one(h, tmp_path, capsys):
    job_id = h.new(tmp_path)
    h.approve(job_id)
    h.claude.fail_start = ClaudeError("claude: cannot start")
    assert h.run("launch", job_id) == 1
    assert "cannot start" in capsys.readouterr().err


def test_claim_prints_nothing_and_resource_is_normalised(h, tmp_path):
    job_id = h.new(tmp_path)
    h.lines.clear()
    assert h.run("claim", job_id, "/work/extra/../other/") == 0
    assert h.lines == []
    h.run("list", "--json")
    assert "/work/other" in json.loads(h.lines[0])[0]["resources"]


def test_claim_device_bench(h, tmp_path):
    job_id = h.new(tmp_path)
    assert h.run("claim", job_id, "device:bench") == 0
    h.run("list", "--json")
    assert "device:bench" in json.loads(h.lines[-1])[0]["resources"]


def test_claim_refused_returns_one_with_holder_in_message(h, tmp_path, capsys):
    first = h.new(tmp_path, repos=("/work/a",), device="bench")
    second = h.new(tmp_path, repos=("/work/b",))
    assert h.run("claim", second, "device:bench") == 1
    assert f"device:bench is held by {first}" in capsys.readouterr().err


def test_close_prints_nothing_and_abandons(h, tmp_path):
    job_id = h.new(tmp_path)
    h.lines.clear()
    assert h.run("close", job_id, "--reason", "superseded") == 0
    assert h.lines == []
    h.run("list")
    assert h.lines == [f"{job_id}  abandoned"]


def test_close_without_reason_succeeds(h, tmp_path):
    assert h.run("close", h.new(tmp_path)) == 0


def test_prune_prints_each_removed_id_one_per_line(h, tmp_path):
    ids = [h.new(tmp_path, repos=(f"/work/{n}",)) for n in "ab"]
    keep = h.new(tmp_path, repos=("/work/c",))
    for job_id in ids:
        h.run("close", job_id)
        stamp = (NOW - timedelta(days=60)).timestamp()
        os.utime(h.root / "jobs" / job_id / "dispatch.jsonl", (stamp, stamp))
    h.lines.clear()
    assert h.run("prune") == 0
    assert h.lines == ids
    assert (h.root / "jobs" / keep).is_dir()


def test_prune_with_nothing_to_remove_prints_nothing(h, tmp_path):
    h.new(tmp_path)
    h.lines.clear()
    assert h.run("prune") == 0
    assert h.lines == []


def test_a_malformed_state_file_makes_list_exit_one_naming_the_file(h, tmp_path, capsys):
    job_id = h.new(tmp_path)
    (h.root / "jobs" / job_id / "dispatch.jsonl").write_text("garbage\n", encoding="utf-8")
    assert h.run("list") == 1
    assert "dispatch.jsonl" in capsys.readouterr().err


# --- main and the environment ---------------------------------------------------------------------------

def test_env_names_are_documented():
    assert (cli_module.ROOT_ENV, cli_module.CLAUDE_ENV) == ("CURE_JOB_ROOT", "CURE_JOB_CLAUDE")
    assert (cli_module.DEFAULT_ROOT, cli_module.DEFAULT_CLAUDE) == ("~/.claude/cure", "claude")


def test_main_uses_root_and_binary_from_the_environment(root, fake_state, tmp_path, capsys):
    source = tmp_path / "handoff.md"
    source.write_text(handoff_text((str(tmp_path),)), encoding="utf-8")
    assert main(["new", "--slug", "env", str(source)]) == 0
    job_id = capsys.readouterr().out.strip()
    assert (root / "jobs" / job_id / "handoff.md").is_file()
    (root / "jobs" / job_id / "goal.md").write_text("goal", encoding="utf-8")
    assert main(["launch", job_id]) == 0
    calls = [json.loads(line) for line in (fake_state / "calls.jsonl").read_text(encoding="utf-8").splitlines()]
    assert calls[-1]["argv"][:3] == ["--bg", "--name", job_id]


def test_main_defaults_the_root_under_home_when_unset_or_empty(tmp_path, monkeypatch, capsys):
    source = tmp_path / "handoff.md"
    source.write_text(handoff_text(), encoding="utf-8")
    for value in (None, ""):
        if value is None:
            monkeypatch.delenv("CURE_JOB_ROOT")
        else:
            monkeypatch.setenv("CURE_JOB_ROOT", value)
        assert main(["new", "--slug", "a" if value is None else "b", str(source)]) == 0
    assert len(list((tmp_path / "home" / ".claude" / "cure" / "jobs").iterdir())) == 2


def test_main_makes_a_relative_binary_path_absolute(tmp_path, monkeypatch, capsys):
    job_dir = tmp_path / "repo"
    job_dir.mkdir()
    source = tmp_path / "handoff.md"
    source.write_text(handoff_text((str(job_dir),)), encoding="utf-8")
    monkeypatch.chdir(FAKE_CLAUDE.parent)
    monkeypatch.setenv("CURE_JOB_CLAUDE", "./fake_claude.py")
    main(["new", "--slug", "rel", str(source)])
    job_id = capsys.readouterr().out.strip()
    root = tmp_path / "cure"
    (root / "jobs" / job_id / "goal.md").write_text("goal", encoding="utf-8")
    assert main(["launch", job_id]) == 0


def test_main_reads_the_environment_on_each_call(tmp_path, monkeypatch, capsys):
    source = tmp_path / "handoff.md"
    source.write_text(handoff_text(), encoding="utf-8")
    for name in ("one", "two"):
        monkeypatch.setenv("CURE_JOB_ROOT", str(tmp_path / name))
        assert main(["new", "--slug", "x", str(source)]) == 0
        assert len(list((tmp_path / name / "jobs").iterdir())) == 1


def test_main_bare_returns_zero(capsys):
    assert main([]) == 0
    assert "new" in capsys.readouterr().out
