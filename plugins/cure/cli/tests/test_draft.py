"""``cure-job draft`` and ``drafted``: the goal-writer session, its states and the commands that wait for it."""
from __future__ import annotations

import io
import json
import stat
from datetime import timedelta
from pathlib import Path

import pytest

from cure_job.claude import SessionStatus
from cure_job.goal import PLUGIN_ROOT
from cure_job.worker import GoalWriterSettings
from tests.builders import set_age
from tests.fakes import fake_id
from tests.test_review_round1 import REPO, Harness
from tests.test_session_lifecycle import NEEDS_INPUT_RESULT, events, write_result

SUMMARY = ("--summary", "outcome", "--summary", "Solo, video-core", "--summary", "3 done-when, pr")
OPEN_GOAL = "# Goal\n\n## Open\n\n- which branch?\n- which board?\n"


@pytest.fixture
def h(root):
    return Harness(root)


@pytest.fixture
def queued(h, tmp_path):
    return h.new(tmp_path, goal=False)


def draft(h, job_id, *argv):
    assert h.run("draft", job_id, *argv) == 0
    return h.lines[0]


def drafted(h, job_id, goal="goal"):
    h.goal(job_id).write_text(goal, encoding="utf-8")
    assert h.run("drafted", job_id, *SUMMARY) == 0
    return list(h.lines)


def started_args(h):
    return h.claude.started[-1][3]


def test_draft_starts_a_goal_writer_session_in_the_first_repository(h, queued):
    session = draft(h, queued)
    job_dir = h.root / "jobs" / queued
    assert session == f"draft-{queued}-1"
    name, cwd, prompt, args = h.claude.started[0]
    assert (name, cwd, prompt) == (session, REPO, f"draft {queued}")
    assert args[:4] == ("--add-dir", str(job_dir), "--agent", "cure:goal-writer")
    assert args[4:] == (*GoalWriterSettings(PLUGIN_ROOT, job_dir, (REPO,), h.root).arguments(),
                        "--permission-mode", "dontAsk")
    assert events(h, queued)[-1] == {"event": "draft-started", "n": 1, "session": session, "mode": "write",
                                     "at": "2026-10-13T18:01:00+00:00"}
    row = h.listed()[queued]
    assert row["state"] == "drafting"
    assert row["draft"] == {"n": 1, "mode": "write", "state": "drafting", "session": session, "summary": None}


@pytest.mark.parametrize("argv", [("--permission-mode", "auto"), ("--permission-mode=auto",)])
def test_draft_passes_the_permission_mode_after_double_dash(h, queued, argv):
    draft(h, queued, "--", *argv)
    assert started_args(h)[-2:] == ("--permission-mode", "auto")


@pytest.mark.parametrize("before_id", [False, True])
def test_draft_with_answers_copies_them_and_prompts_apply(h, tmp_path, queued, before_id):
    h.goal(queued).write_text("goal", encoding="utf-8")
    source = tmp_path / "answers.md"
    source.write_text("1. main\n", encoding="utf-8")
    argv = ["--answers", str(source), queued] if before_id else [queued, "--answers", str(source)]
    assert h.run("draft", *argv, "--", "--permission-mode", "acceptEdits") == 0
    copy = h.root / "jobs" / queued / "answers-1.md"
    assert copy.read_text(encoding="utf-8") == "1. main\n"
    assert stat.S_IMODE(copy.stat().st_mode) == 0o600
    assert h.claude.started[0][2] == f"apply {queued} @{copy}"
    assert started_args(h)[-2:] == ("--permission-mode", "acceptEdits")
    assert events(h, queued)[-1]["mode"] == "apply"


def test_draft_reads_answers_from_stdin(h, queued, monkeypatch):
    h.goal(queued).write_text("goal", encoding="utf-8")
    monkeypatch.setattr("sys.stdin", io.StringIO("yes\n"))
    draft(h, queued, "--answers", "-")
    assert (h.root / "jobs" / queued / "answers-1.md").read_text(encoding="utf-8") == "yes\n"


def test_draft_refuses_answers_without_a_goal_and_empty_answers(h, tmp_path, queued, capsys):
    source = tmp_path / "answers.md"
    source.write_text("a\n", encoding="utf-8")
    assert h.run("draft", queued, "--answers", str(source)) == 1
    assert "no goal file" in capsys.readouterr().err
    h.goal(queued).write_text("goal", encoding="utf-8")
    source.write_text(" \n", encoding="utf-8")
    with pytest.raises(SystemExit) as exit_info:
        h.run("draft", queued, "--answers", str(source))
    assert exit_info.value.code == 2
    assert h.claude.started == [] and not (h.root / "jobs" / queued / "dispatch.jsonl").exists()


def test_draft_refuses_a_drafting_job_and_drafts_a_running_one(h, tmp_path, queued, capsys):
    draft(h, queued)
    assert h.run("draft", queued) == 1
    assert "draft needs queued, held, awaiting-approval, approved, launched, running, stalled, blocked, " \
        "lost, needs-input, draft-lost" in capsys.readouterr().err
    running = h.new(tmp_path)
    assert h.run("launch", running) == 0
    assert draft(h, running) == f"draft-{running}-1"
    assert h.listed()[running]["state"] == "running"


def test_draft_after_a_lost_draft_stops_its_live_session_and_takes_the_next_number(h, queued):
    first = draft(h, queued)
    h.claude.statuses[first] = SessionStatus.IDLE
    h.clock.advance(timedelta(hours=1))
    assert h.listed()[queued]["state"] == "draft-lost"
    assert draft(h, queued) == f"draft-{queued}-2"
    assert h.claude.stopped == [fake_id(first)]


def test_drafted_ends_the_draft_and_prints_the_goal_open_count_and_notify_line(h, queued):
    session = draft(h, queued)
    lines = drafted(h, queued, OPEN_GOAL)
    assert lines == [str(h.goal(queued)), "open=2", f'notify: SendMessage dispatcher "job {queued}"']
    assert events(h, queued)[-1] == {"event": "draft-ended", "n": 1, "open": 2,
                                     "summary": ["outcome", "Solo, video-core", "3 done-when, pr"],
                                     "at": "2026-10-13T18:01:00+00:00"}
    row = h.listed()[queued]
    assert row["state"] == "awaiting-approval"
    assert row["draft"] == {"n": 1, "mode": "write", "state": "ended", "session": session,
                            "summary": ["outcome", "Solo, video-core", "3 done-when, pr"]}


def test_drafted_refuses_without_an_open_draft_or_a_goal(h, queued, capsys):
    assert h.run("drafted", queued, *SUMMARY) == 1
    assert "no open draft" in capsys.readouterr().err
    draft(h, queued)
    assert h.run("drafted", queued, *SUMMARY) == 1
    assert "no goal file" in capsys.readouterr().err
    assert not any(event["event"] == "draft-ended" for event in events(h, queued))


@pytest.mark.parametrize("summary", [SUMMARY[:4], (*SUMMARY, "--summary", "four"), ("--summary", " ", *SUMMARY[2:])])
def test_drafted_needs_exactly_three_non_empty_summary_lines(h, queued, summary):
    draft(h, queued)
    h.goal(queued).write_text("goal", encoding="utf-8")
    with pytest.raises(SystemExit) as exit_info:
        h.run("drafted", queued, *summary)
    assert exit_info.value.code == 2


def test_approve_and_launch_refuse_an_open_draft(h, queued, capsys):
    draft(h, queued)
    h.goal(queued).write_text("goal", encoding="utf-8")
    assert h.run("approve", queued, "--by", "user") == 1
    assert h.run("launch", queued) == 1
    assert capsys.readouterr().err.count("needs a complete draft") == 2
    drafted(h, queued)
    assert h.run("approve", queued, "--by", "user") == 0
    assert h.run("launch", queued) == 0
    assert h.claude.stopped == [fake_id(f"draft-{queued}-1")]


def test_close_while_drafting_then_remove_sessions_removes_the_draft_sessions(h, queued):
    first = draft(h, queued)
    h.claude.statuses[first] = SessionStatus.STOPPED
    h.clock.advance(timedelta(hours=1))
    second = draft(h, queued)
    assert h.run("close", queued) == 0
    assert h.run("remove-sessions", queued) == 0
    assert sorted(h.lines) == sorted([first, second])
    assert h.claude.statuses == {}


def test_answers_after_needs_input_give_resume_or_ask_open(h, tmp_path):
    job_id = h.new(tmp_path)
    assert h.run("launch", job_id) == 0
    write_result(h, job_id, NEEDS_INPUT_RESULT)
    set_age(h.root / "jobs" / job_id / "result.md", h.clock(), timedelta(seconds=1))
    assert h.run("reported", job_id) == 0
    source = tmp_path / "answers.md"
    source.write_text("main\n", encoding="utf-8")
    draft(h, job_id, "--answers", str(source))
    assert next_actions(h) == {}
    drafted(h, job_id, OPEN_GOAL)
    assert next_actions(h)[job_id] == (["ask-open"], {"ask-open": {"open": 2}})
    h.goal(job_id).write_text("goal", encoding="utf-8")
    assert next_actions(h)[job_id] == (["resume"], {})


def test_next_gives_redraft_for_a_lost_apply_draft(h, tmp_path, queued):
    h.goal(queued).write_text("goal", encoding="utf-8")
    source = tmp_path / "answers.md"
    source.write_text("a\n", encoding="utf-8")
    draft(h, queued, "--answers", str(source))
    h.claude.statuses.clear()
    h.clock.advance(timedelta(hours=1))
    assert next_actions(h)[queued] == (["redraft"], {"redraft": {
        "mode": "apply", "answers": str(h.root / "jobs" / queued / "answers-1.md"), "lost": 1}})


def test_successor_gets_draft_only_once_the_predecessor_draft_ended(h, tmp_path, queued):
    source = tmp_path / "successor.md"
    source.write_text((tmp_path / "handoff.md").read_text(encoding="utf-8")
                      .replace("device: none", f"device: none\nafter: {queued}"), encoding="utf-8")
    assert h.run("new", "--slug", "y", str(source)) == 0
    successor = h.lines[0]
    draft(h, queued)
    h.goal(queued).write_text("goal", encoding="utf-8")
    assert successor not in next_actions(h)
    drafted(h, queued)
    assert next_actions(h)[successor][0] == ["draft"]


def test_launch_refusal_for_a_missing_plugin_path_names_cure_job_draft(h, tmp_path, capsys):
    job_id = h.new(tmp_path, goal=False)
    h.goal(job_id).write_text(f"read {PLUGIN_ROOT}/skills/goal/missing.md\n", encoding="utf-8")
    assert h.run("approve", job_id, "--by", "user") == 0
    assert h.run("launch", job_id) == 1
    assert f"write the goal again: cure-job draft {job_id}" in capsys.readouterr().err


def test_goal_writer_settings_allow_the_goal_and_deny_every_decision(tmp_path):
    job_dir = tmp_path / "jobs" / "261030-1750-x-y"
    settings = json.loads(GoalWriterSettings(Path("/p"), job_dir, ["/r1", "/r2"], Path("/c")).arguments()[1])
    allow, deny = settings["permissions"]["allow"], settings["permissions"]["deny"]
    for rule in ["Skill(cure:goal)", f"Bash(cure-job drafted {job_dir.name} *)",
                 f"Bash(/p/bin/cure-job drafted {job_dir.name} *)", "Bash(cure-job config get *)",
                 "Bash(/p/bin/cure-job list *)", f"Edit(/{job_dir}/goal.md)", "Bash(wc -c *)", "SendMessage",
                 f"Read(/{job_dir.parent}/**)", "Read(//p/**)", "Read(//r2/**)", "Read(//c/question-policies.md)",
                 "Bash(command -v *)", "Bash(git -C * symbolic-ref --short refs/remotes/origin/HEAD)"]:
        assert rule in allow
    assert not any(rule.startswith("Edit(") and "goal.md" not in rule for rule in allow)
    for rule in ["Bash(claude *)", "Edit(//r1/**)", "Edit(//r2/**)", "Bash(cure-job approve *)",
                 "Bash(/p/bin/cure-job launch *)", "Bash(cure-job resume *)", "Bash(cure-job close *)",
                 "Bash(cure-job draft *)", "Bash(cure-job new *)"]:
        assert rule in deny


def next_actions(h) -> dict[str, tuple[list[str], dict]]:
    assert h.run("next", "--json") == 0
    return {entry["id"]: (entry["actions"], entry["args"]) for entry in json.loads(h.lines[0])}
