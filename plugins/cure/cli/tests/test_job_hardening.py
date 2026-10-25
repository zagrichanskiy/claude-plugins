"""Issue 80: the CLI refuses launch-capable calls it cannot check, owns the notify line, and keeps its files private."""
from __future__ import annotations

import json
import os
import stat

import pytest

from cure_job.claude import SessionStatus
from cure_job.cli import Cli, main
from cure_job.worker import WorkerSettings
from tests.builders import settings_args
from tests.test_cli import Harness

PR = "https://github.com/acme/video-core/pull/7"


@pytest.fixture
def h(root):
    return Harness(root)


def mode(path) -> int:
    return stat.S_IMODE(os.stat(path).st_mode)


def launched(h, tmp_path) -> str:
    job_id = h.new(tmp_path)
    h.approve(job_id)
    assert h.run("launch", job_id) == 0
    return job_id


def rows(h):
    h.lines.clear()
    assert h.run("list", "--json") == 0
    return {row["id"]: row for row in json.loads(h.lines[0])}


# --- finish: notify line and field checks ----------------------------------------------------------

def test_finish_prints_the_notify_line(h, tmp_path):
    job_id = launched(h, tmp_path)
    h.lines.clear()
    assert h.run("finish", job_id, "--status", "done") == 0
    assert h.lines[1:] == [f'notify: SendMessage dispatcher "job {job_id}"']


@pytest.mark.parametrize("pr", ["x; gh pr merge", "http://github.com/a/b/pull/1", "https://github.com/a/b/pull/0",
                                "https://github.com/a/b/pull/1; rm -rf x", "https://github.com/a/b/issues/1"])
def test_finish_refuses_a_pr_that_is_not_a_pull_request_url(h, tmp_path, capsys, pr):
    job_id = launched(h, tmp_path)
    assert h.run("finish", job_id, "--status", "done", "--pr", pr) == 1
    assert "pr" in capsys.readouterr().err
    assert not (h.root / "jobs" / job_id / "result.md").exists()


def test_finish_refuses_a_relative_retro(h, tmp_path, capsys):
    job_id = launched(h, tmp_path)
    assert h.run("finish", job_id, "--status", "done", "--retro", "notes/retro.md") == 1
    assert "absolute" in capsys.readouterr().err
    assert not (h.root / "jobs" / job_id / "result.md").exists()


def test_finish_accepts_a_pull_request_url_and_an_absolute_retro(h, tmp_path):
    job_id = launched(h, tmp_path)
    retro = tmp_path / "retro.md"
    assert h.run("finish", job_id, "--status", "done", "--pr", PR, "--retro", str(retro)) == 0
    text = (h.root / "jobs" / job_id / "result.md").read_text(encoding="utf-8")
    assert PR in text and str(retro) in text


def test_finish_help_shows_the_options_table(h, capsys):
    with pytest.raises(SystemExit) as caught:
        h.run("finish", "--help")
    assert caught.value.code == 0
    out = capsys.readouterr().out
    for option in ("--status done|failed|needs-input", "--unproven", "--question", "--retro", "--pr", "--kept"):
        assert option in out
    assert "https://<host>/<owner>/<repo>/pull/<n>" in out


# --- launch and resume: arguments after -- ----------------------------------------------------------

@pytest.mark.parametrize("command", ["launch", "resume"])
def test_launch_and_resume_refuse_any_argument_but_a_permission_mode(h, tmp_path, capsys, command):
    job_id = h.new(tmp_path)
    h.approve(job_id)
    assert h.run(command, job_id, "--", "--dangerously-skip-permissions") == 1
    assert "refused" in capsys.readouterr().err
    assert h.claude.started == [] and h.claude.resumed == []


@pytest.mark.parametrize("mode_name", ["acceptEdits", "default", "auto"])
@pytest.mark.parametrize("spelling", ["separate", "equals"])
def test_launch_accepts_each_permission_mode_in_both_spellings(h, tmp_path, mode_name, spelling):
    job_id = h.new(tmp_path)
    h.approve(job_id)
    given = ["--permission-mode", mode_name] if spelling == "separate" else [f"--permission-mode={mode_name}"]
    assert h.run("launch", job_id, "--", *given) == 0
    assert h.claude.started[0][3][-2:] == ("--permission-mode", mode_name)


@pytest.mark.parametrize("command", ["launch", "resume"])
@pytest.mark.parametrize("given", [["--permission-mode", "bypassPermissions"], ["--permission-mode=plan"],
                                   ["--permission-mode"], ["--permission-mode", "auto", "--model", "opus"]])
def test_launch_and_resume_refuse_a_bad_permission_mode_value(h, tmp_path, capsys, command, given):
    job_id = h.new(tmp_path)
    h.approve(job_id)
    assert h.run(command, job_id, "--", *given) == 1
    assert capsys.readouterr().err.startswith("error: refused")
    assert h.claude.started == [] and h.claude.resumed == []


def test_resume_accepts_a_permission_mode(h, tmp_path):
    job_id = launched(h, tmp_path)
    (h.root / "jobs" / job_id / "result.md").write_text(
        "---\nstatus: needs-input\nquestion: which?\n---\n", encoding="utf-8")
    h.claude.statuses[job_id] = SessionStatus.IDLE
    assert h.run("resume", job_id, "--", "--permission-mode", "acceptEdits") == 0
    assert h.claude.resumed[0][4][-2:] == ("--permission-mode", "acceptEdits")


def test_launch_and_resume_pass_settings_that_allow_finish_claim_and_release(root, tmp_path):
    plugin = tmp_path / "plugin"
    (plugin / "skills" / "goal").mkdir(parents=True)
    (plugin / "skills" / "goal" / "rules.md").write_text("## Rules\n", encoding="utf-8")
    h = Harness(root)
    h.cli = Cli(root=root, claude=h.claude, clock=h.clock, out=h.lines.append, plugin_root=plugin)
    job_id = launched(h, tmp_path)
    expected = settings_args(job_id, plugin)
    assert h.claude.started[0][3] == expected
    (root / "jobs" / job_id / "result.md").write_text("---\nstatus: needs-input\nquestion: q\n---\n", encoding="utf-8")
    h.claude.statuses[job_id] = SessionStatus.IDLE
    assert h.run("resume", job_id) == 0
    assert h.claude.resumed[0][4] == expected


def test_launch_refuses_a_goal_naming_a_missing_file_under_the_plugin_root(root, tmp_path, capsys):
    plugin = tmp_path / "plugin"
    (plugin / "skills" / "goal").mkdir(parents=True)
    (plugin / "skills" / "goal" / "rules.md").write_text("## Rules\n", encoding="utf-8")
    h = Harness(root)
    h.cli = Cli(root=root, claude=h.claude, clock=h.clock, out=h.lines.append, plugin_root=plugin)
    job_id = h.new(tmp_path)
    missing = plugin / "skills" / "goal" / "worker.md"
    (root / "jobs" / job_id / "goal.md").write_text(f"# Goal\n\nRead {missing}\n", encoding="utf-8")
    assert h.run("approve", job_id, "--by", "user") == 0
    assert h.run("launch", job_id) == 1
    assert str(missing) in capsys.readouterr().err
    assert h.claude.started == []


def test_worker_rules_allow_finish_claim_and_release_for_their_own_job_only(tmp_path):
    rules = "\n".join(WorkerSettings(tmp_path, "job-a").rules())
    assert "finish job-a *" in rules
    assert "job-b" not in rules


def test_launch_of_an_unapproved_job_names_the_approve_command_with_by_user(h, tmp_path, capsys):
    job_id = h.new(tmp_path)
    (h.root / "jobs" / job_id / "goal.md").write_text("goal", encoding="utf-8")
    assert h.run("launch", job_id) == 1
    assert f"cure-job approve {job_id} --by user" in capsys.readouterr().err


# --- approve and the open count ---------------------------------------------------------------------

def test_approve_without_by_exits_two(h, tmp_path, capsys):
    job_id = h.new(tmp_path)
    (h.root / "jobs" / job_id / "goal.md").write_text("goal", encoding="utf-8")
    with pytest.raises(SystemExit) as caught:
        h.run("approve", job_id)
    assert caught.value.code == 2
    assert "--by" in capsys.readouterr().err
    assert not (h.root / "jobs" / job_id / "dispatch.jsonl").exists()


def test_approve_refuses_a_goal_with_items_under_open(h, tmp_path, capsys):
    job_id = h.new(tmp_path)
    (h.root / "jobs" / job_id / "goal.md").write_text("# Goal\n\n## Open\n\n- which branch?\n", encoding="utf-8")
    assert h.run("approve", job_id, "--by", "user") == 1
    assert "## Open" in capsys.readouterr().err
    assert not (h.root / "jobs" / job_id / "dispatch.jsonl").exists()


@pytest.mark.parametrize("goal", ["# Goal\n\n## Open\n\n* item\n", "# Goal\n\n## Open questions\n\n1. item\n"])
def test_approve_refuses_a_star_item_or_a_numbered_item_under_an_open_heading(h, tmp_path, goal):
    job_id = h.new(tmp_path)
    (h.root / "jobs" / job_id / "goal.md").write_text(goal, encoding="utf-8")
    assert h.run("approve", job_id, "--by", "user") == 1


@pytest.mark.parametrize("goal", ["# Goal\n\n## Open\n\n## Rules\n\n- Tier: Solo.\n", "# Goal\n\n## Rules\n- Tier: Solo.\n"])
def test_approve_accepts_an_empty_or_absent_open_section(h, tmp_path, goal):
    job_id = h.new(tmp_path)
    (h.root / "jobs" / job_id / "goal.md").write_text(goal, encoding="utf-8")
    assert h.run("approve", job_id, "--by", "user") == 0


def test_approve_ignores_items_under_a_later_heading(h, tmp_path):
    job_id = h.new(tmp_path)
    (h.root / "jobs" / job_id / "goal.md").write_text("## Open\n\n## Rules\n\n- a rule\n", encoding="utf-8")
    assert h.run("approve", job_id, "--by", "user") == 0


def test_list_shows_the_open_count_of_a_valid_job(h, tmp_path):
    job_id = h.new(tmp_path)
    (h.root / "jobs" / job_id / "goal.md").write_text("## Open\n\n- one\n- two\n", encoding="utf-8")
    assert rows(h)[job_id]["open"] == 2
    h.lines.clear()
    h.run("list")
    assert "  open=2" in h.lines[0]


def test_list_hides_a_zero_open_count_in_text(h, tmp_path):
    h.new(tmp_path)
    h.lines.clear()
    h.run("list")
    assert "open=" not in h.lines[0]


def test_list_shows_the_open_count_of_an_invalid_job(h, tmp_path):
    job_id = h.new(tmp_path)
    (h.root / "jobs" / job_id / "goal.md").write_text("## Open\n\n- one\n", encoding="utf-8")
    (h.root / "jobs" / job_id / "handoff.md").write_text("garbage", encoding="utf-8")
    row = rows(h)[job_id]
    assert row["state"] == "invalid" and row["open"] == 1
    h.lines.clear()
    h.run("list")
    assert "  open=1" in h.lines[0]


# --- file modes -------------------------------------------------------------------------------------

def test_a_new_state_root_and_jobs_directory_are_private(h, tmp_path):
    job_id = h.new(tmp_path)
    assert mode(h.root) == 0o700
    assert mode(h.root / "jobs") == 0o700
    assert mode(h.root / "jobs" / job_id) == 0o700


def test_job_files_are_private(h, tmp_path):
    job_id = h.new(tmp_path)
    h.approve(job_id)
    assert h.run("launch", job_id) == 0
    assert h.run("finish", job_id, "--status", "done") == 0
    directory = h.root / "jobs" / job_id
    names = {path.name for path in directory.iterdir()}
    assert {"handoff.md", "goal.md", "dispatch.jsonl", "result.md"} <= names
    for name in ("handoff.md", "dispatch.jsonl", "result.md"):
        assert mode(directory / name) == 0o600, name


def test_an_existing_world_readable_root_is_narrowed_to_0700(root, tmp_path):
    (root / "jobs").mkdir(parents=True)
    os.chmod(root, 0o755)
    os.chmod(root / "jobs", 0o755)
    Harness(root)
    assert mode(root) == 0o700
    assert mode(root / "jobs") == 0o700


def test_config_init_creates_a_private_root_and_config_file(h):
    assert h.run("config", "init") == 0
    assert mode(h.root) == 0o700
    assert mode(h.root / "config.json") == 0o600


def test_rewriting_goal_md_leaves_it_private(root, tmp_path):
    plugin = tmp_path / "plugin"
    (plugin / "skills" / "goal").mkdir(parents=True)
    (plugin / "skills" / "goal" / "rules.md").write_text("## Rules\n", encoding="utf-8")
    h = Harness(root)
    h.cli = Cli(root=root, claude=h.claude, clock=h.clock, out=h.lines.append, plugin_root=plugin)
    job_id = h.new(tmp_path)
    goal = root / "jobs" / job_id / "goal.md"
    goal.write_text("see /home/u/.claude/plugins/cache/zagrichanskiy/cure/0.1.0/skills/goal/rules.md\n",
                    encoding="utf-8")
    os.chmod(goal, 0o644)
    assert h.run("approve", job_id, "--by", "user") == 0
    assert h.run("launch", job_id) == 0
    assert str(plugin) in goal.read_text(encoding="utf-8")
    assert mode(goal) == 0o600


def test_a_failed_chmod_of_the_state_root_exits_one_without_a_traceback(root, tmp_path, monkeypatch, capsys):
    (root / "jobs").mkdir(parents=True)

    def refuse(path, *args, **kwargs):
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(os, "chmod", refuse)
    assert main(["list"]) == 1
    captured = capsys.readouterr()
    assert captured.err.startswith("error: ")
    assert "Traceback" not in captured.err
