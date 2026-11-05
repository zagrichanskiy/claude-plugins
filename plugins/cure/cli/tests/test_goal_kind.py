"""The goal session kind: ``start`` and ``end`` of a goal session, and the ``next`` recovery of one."""
from __future__ import annotations

import json
from datetime import timedelta

import pytest

from cure_job.actions import actions
from cure_job.claude import SessionStatus
from cure_job.events import SessionStarted
from cure_job.goal import PLUGIN_ROOT
from cure_job.state import derive
from tests.builders import NOW, listed, make_record
from tests.fakes import fake_id
from tests.test_review_round1 import Harness

A = "261013-1000-video-core-a"
OLD = timedelta(minutes=5)
SUMMARY = ("--summary", "one", "--summary", "two", "--summary", "three")


@pytest.fixture
def h(root):
    return Harness(root)


def start_goal(h, tmp_path, *extra, goal=False):
    job_id = h.new(tmp_path, goal=goal)
    assert h.run("start", job_id, "goal", *extra) == 0
    return job_id, h.lines[0]


def test_start_on_a_queued_job_without_a_goal_runs_the_goal_writer_with_its_rules_and_answers(h, tmp_path):
    source = tmp_path / "answers.txt"
    source.write_text("use main", encoding="utf-8")
    job_id, name = start_goal(h, tmp_path, "--input", str(source))
    assert h.listed()[job_id]["state"] == "queued"
    job_dir = h.root / "jobs" / job_id
    cure_job = PLUGIN_ROOT / "bin" / "cure-job"
    assert name == f"{job_id}-goal-1"
    (started, _, prompt, arguments), = h.claude.started
    assert started == name
    assert prompt == (f"job {job_id}: write the goal; handoff @{job_dir / 'handoff.md'}; "
                      f"apply the answers in @{job_dir / 'answers-1.md'}")
    assert arguments[:2] == ("--agent", "cure:goal-writer")
    settings = json.loads(arguments[arguments.index("--settings") + 1])
    assert settings["permissions"] == {
        "allow": [f"Bash({cure_job} list *)", f"Bash({cure_job} config get *)", f"Write(/{job_dir}/goal.md)",
                  f"Edit(/{job_dir}/goal.md)", f"Bash(wc -c {job_dir}/goal.md)", "Bash(git -C * symbolic-ref *)",
                  "Bash(gh repo view *)", f"Bash({cure_job} end {job_id} goal *)"],
        "deny": ["Bash(claude *)", f"Bash({cure_job} approve *)"]}
    assert (job_dir / "answers-1.md").read_text(encoding="utf-8") == "use main"


def test_start_without_an_input_gives_the_prompt_without_answers(h, tmp_path):
    job_id, _ = start_goal(h, tmp_path)
    assert h.claude.started[0][2] == (f"job {job_id}: write the goal; "
                                      f"handoff @{h.root / 'jobs' / job_id / 'handoff.md'}")


@pytest.mark.parametrize("state", ["running", "done"])
def test_start_is_refused_in_running_and_done(h, tmp_path, capsys, state):
    job_id = h.new(tmp_path)
    assert h.run("launch", job_id) == 0
    if state == "done":
        (h.root / "jobs" / job_id / "result.md").write_text("---\nstatus: done\n---\n", encoding="utf-8")
    assert h.listed()[job_id]["state"] == state
    assert h.run("start", job_id, "goal") == 1
    assert f"job {job_id} is {state}; start needs queued, held, awaiting-approval, approved, lost, needs-input" in (
        capsys.readouterr().err)


def test_end_needs_three_summary_lines(h, tmp_path, capsys):
    job_id, _ = start_goal(h, tmp_path)
    h.goal(job_id).write_text("goal", encoding="utf-8")
    assert h.run("end", job_id, "goal", "--summary", "one") == 1
    assert "end of a goal session needs 3 summary line(s), got 1" in capsys.readouterr().err


def test_end_is_refused_without_the_goal_file(h, tmp_path, capsys):
    job_id, _ = start_goal(h, tmp_path)
    assert h.run("end", job_id, "goal", *SUMMARY) == 1
    assert f"job {job_id} has no goal file" in capsys.readouterr().err
    assert h.listed()[job_id]["sessions"]["goal"]["liveness"] == "busy"


def test_end_prints_the_notify_line_and_launch_stops_the_ended_session(h, tmp_path):
    job_id, name = start_goal(h, tmp_path)
    h.goal(job_id).write_text("goal", encoding="utf-8")
    assert h.run("end", job_id, "goal", *SUMMARY) == 0
    assert h.lines == [f'notify: SendMessage dispatcher "job {job_id}"']
    assert h.listed()[job_id]["sessions"]["goal"]["summary"] == ["one", "two", "three"]
    assert h.run("approve", job_id, "--by", "user") == 0
    assert h.run("launch", job_id) == 0
    assert h.claude.stopped == [fake_id(name)]


def test_a_goal_session_on_a_lost_job_ends_and_launch_then_works(h, tmp_path):
    job_id = h.new(tmp_path)
    assert h.run("launch", job_id) == 0
    assert h.run("stop", job_id) == 0
    assert h.listed()[job_id]["state"] == "lost"
    assert h.run("start", job_id, "goal") == 0
    name = h.lines[0]
    h.goal(job_id).write_text("goal again", encoding="utf-8")
    assert h.run("end", job_id, "goal", *SUMMARY) == 0
    assert h.run("launch", job_id) == 0
    assert fake_id(name) in h.claude.stopped


def test_launch_with_a_missing_plugin_path_names_the_goal_session_with_the_refusal_as_input(h, tmp_path, capsys):
    job_id = h.new(tmp_path, goal=False)
    h.goal(job_id).write_text(f"goal: read {PLUGIN_ROOT}/agents/missing.md", encoding="utf-8")
    assert h.run("approve", job_id, "--by", "user") == 0
    assert h.run("launch", job_id) == 1
    assert (f"write the goal again: echo '<refusal>' | cure-job start {job_id} goal --input -"
            in capsys.readouterr().err)


@pytest.mark.parametrize("status, expected", [
    (None, {"restart-session": {"kind": "goal", "inputs": ["answers-1.md"], "restarts": 0}}),
    (SessionStatus.IDLE, {"restart-session": {"kind": "goal", "inputs": ["answers-1.md"], "restarts": 0}}),
    (SessionStatus.WAITING, {"tell-blocked": {"kind": "goal", "session": "g", "waiting-for": None}}),
    (SessionStatus.BUSY, {}),
])
def test_a_goal_session_gets_the_restart_recovery(status, expected):
    record = make_record(A, events=(SessionStarted("goal", 1, "g", NOW - OLD, 0, ("answers-1.md",)),))
    view = derive([record], listed({"g": status} if status is not None else {}), NOW, frozenset())[0]
    assert {action.name: dict(action.args) for action in actions(view, {})} == expected
