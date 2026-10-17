"""Issue 21: ``resume`` of a needs-input job, ``remove-sessions`` of a finished job, and the launch grace."""
from __future__ import annotations

import json
from datetime import timedelta

import pytest

from cure_job.claude import ClaudeCli, Session, SessionStatus
from cure_job.state import LAUNCH_GRACE
from tests.conftest import FAKE_CLAUDE
from tests.fakes import fake_id, fake_uuid
from tests.test_review_round1 import Harness

NEEDS_INPUT_RESULT = "---\nstatus: needs-input\nquestion: which branch?\n---\n"
DONE_RESULT = "---\nstatus: done\n---\n"
FAILED_RESULT = "---\nstatus: failed\n---\n"


@pytest.fixture
def h(root):
    return Harness(root)


def launch(h, tmp_path):
    job_id = h.new(tmp_path)
    assert h.run("launch", job_id) == 0
    return job_id, h.lines[0]


def write_result(h, job_id, text):
    (h.root / "jobs" / job_id / "result.md").write_text(text, encoding="utf-8")


def needs_input(h, tmp_path):
    """A job whose run 1 ended needs-input with its session idle; returns (job id, session name)."""
    job_id, session = launch(h, tmp_path)
    write_result(h, job_id, NEEDS_INPUT_RESULT)
    h.claude.statuses[session] = SessionStatus.IDLE
    return job_id, session


def events(h, job_id):
    lines = (h.root / "jobs" / job_id / "dispatch.jsonl").read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines]


def launches(h, job_id):
    return [entry for entry in events(h, job_id) if entry["event"] == "launched"]


# --- resume -----------------------------------------------------------------------------------------------

def test_resume_continues_the_needs_input_session_as_the_next_run(h, tmp_path):
    job_id, session = needs_input(h, tmp_path)
    assert h.run("resume", job_id) == 0
    assert h.lines == [session]
    assert h.claude.stopped == [fake_id(session)]
    goal = h.root / "jobs" / job_id / "goal.md"
    assert h.claude.resumed == [(session, fake_uuid(session), "/work/video-core", f"/goal @{goal}", ())]
    assert len(h.claude.started) == 1
    assert [(entry["run"], entry["session"]) for entry in launches(h, job_id)] == [(1, session), (2, session)]
    assert (h.root / "jobs" / job_id / "result-1.md").is_file()
    listed = h.listed()[job_id]
    assert (listed["state"], listed["run"], listed["session"]) == ("running", 2, session)


def test_resume_of_a_stopped_session_stops_nothing(h, tmp_path):
    job_id, session = needs_input(h, tmp_path)
    h.claude.statuses[session] = SessionStatus.STOPPED
    assert h.run("resume", job_id) == 0
    assert h.claude.stopped == []
    assert h.claude.resumed[0][1] == fake_uuid(session)


def test_resume_passes_claude_arguments_after_double_dash(h, tmp_path):
    job_id, _ = needs_input(h, tmp_path)
    assert h.run("resume", job_id, "--", "--model", "opus") == 0
    assert h.claude.resumed[0][4] == ("--model", "opus")


def test_resume_of_a_gone_session_exits_one_and_changes_nothing(h, tmp_path, capsys):
    job_id, session = needs_input(h, tmp_path)
    del h.claude.statuses[session]
    assert h.run("resume", job_id) == 1
    assert f"cure-job launch {job_id}" in capsys.readouterr().err
    assert h.claude.resumed == [] and h.claude.stopped == []
    assert len(launches(h, job_id)) == 1
    assert h.listed()[job_id]["state"] == "needs-input"


def test_resume_of_a_session_listed_without_a_session_id_exits_one(h, tmp_path, capsys):
    job_id, session = needs_input(h, tmp_path)
    h.claude.uuids[session] = None
    assert h.run("resume", job_id) == 1
    assert "no longer exists" in capsys.readouterr().err
    assert h.claude.resumed == [] and h.claude.stopped == []


def test_launch_refuses_a_needs_input_job_whose_session_is_live(h, tmp_path, capsys):
    job_id, session = needs_input(h, tmp_path)
    assert h.run("launch", job_id) == 1
    assert f"session {session} is live; continue it: cure-job resume {job_id}" in capsys.readouterr().err
    assert len(h.claude.started) == 1
    h.claude.statuses[session] = SessionStatus.STOPPED
    assert h.run("launch", job_id) == 0


def test_resume_refuses_a_job_that_is_not_needs_input(h, tmp_path, capsys):
    job_id, _ = launch(h, tmp_path)
    assert h.run("resume", job_id) == 1
    assert "running" in capsys.readouterr().err
    assert h.claude.resumed == []


def test_resume_failure_restores_the_result_for_a_retry(h, tmp_path):
    from cure_job.errors import ClaudeError
    job_id, _ = needs_input(h, tmp_path)
    h.claude.fail_start = ClaudeError("boom")
    assert h.run("resume", job_id) == 1
    assert h.listed()[job_id]["state"] == "needs-input"
    assert len(launches(h, job_id)) == 1


def test_resumed_session_listed_stopped_is_launched_within_the_grace_and_lost_after(h, tmp_path):
    job_id, session = needs_input(h, tmp_path)
    assert h.run("resume", job_id) == 0
    h.claude.statuses[session] = SessionStatus.STOPPED
    assert h.listed()[job_id]["state"] == "launched"
    h.clock.advance(LAUNCH_GRACE + timedelta(seconds=1))
    assert h.listed()[job_id]["state"] == "lost"


def test_resume_through_the_claude_binary_reuses_the_session_uuid(tmp_path, fake_state):
    claude = ClaudeCli(str(FAKE_CLAUDE))
    claude.start("n", str(tmp_path), "/goal @g")
    listed = claude.sessions()["n"]
    claude.stop(listed.ids[0])
    claude.resume("n", listed.uuid, str(tmp_path), "/goal @g", ["--model", "opus"])
    argv = json.loads((fake_state / "calls.jsonl").read_text(encoding="utf-8").splitlines()[-1])["argv"]
    assert argv == ["--bg", "--resume", listed.uuid, "--name", "n", "--model", "opus", "/goal @g"]
    assert claude.sessions()["n"].status is SessionStatus.BUSY


# --- remove-sessions --------------------------------------------------------------------------------------

def done_in_two_runs(h, tmp_path):
    """A done job whose runs 1 and 2 used separate sessions, both still listed; returns (id, sessions)."""
    job_id, first = launch(h, tmp_path)
    write_result(h, job_id, NEEDS_INPUT_RESULT)
    del h.claude.statuses[first]
    assert h.run("launch", job_id) == 0
    second = h.lines[0]
    h.claude.statuses[first] = SessionStatus.STOPPED
    h.claude.statuses[second] = SessionStatus.IDLE
    write_result(h, job_id, DONE_RESULT)
    return job_id, [first, second]


def test_remove_sessions_of_a_done_job_leaves_no_session_of_any_run(h, tmp_path):
    job_id, sessions = done_in_two_runs(h, tmp_path)
    assert h.run("remove-sessions", job_id) == 0
    assert h.lines == sessions
    assert h.claude.stopped == [fake_id(sessions[1])]
    assert sorted(h.claude.removed) == sorted(fake_id(name) for name in sessions)
    assert not set(sessions) & set(h.claude.sessions())
    assert (h.listed()[job_id]["state"], h.listed()[job_id]["sessions-removed"]) == ("done", True)


def test_remove_sessions_records_sessions_removed_once(h, tmp_path):
    job_id, _ = done_in_two_runs(h, tmp_path)
    assert h.listed()[job_id]["sessions-removed"] is False
    assert h.run("remove-sessions", job_id) == 0
    assert h.run("remove-sessions", job_id) == 0
    assert [entry["event"] for entry in events(h, job_id)].count("sessions-removed") == 1


def test_remove_sessions_with_an_entry_without_an_id_removes_nothing_and_records_nothing(h, tmp_path, capsys):
    job_id, sessions = done_in_two_runs(h, tmp_path)
    listing = h.claude.sessions
    h.claude.sessions = lambda: {**listing(), sessions[1]: Session(SessionStatus.STOPPED, all_ids=("",))}
    assert h.run("remove-sessions", job_id) == 1
    assert "listed without an id" in capsys.readouterr().err
    assert h.claude.removed == [] and h.claude.stopped == []
    assert h.listed()[job_id]["sessions-removed"] is False


def test_remove_sessions_that_leaves_a_session_listed_records_nothing(h, tmp_path, capsys):
    job_id, sessions = done_in_two_runs(h, tmp_path)
    h.claude.remove = h.claude.removed.append
    assert h.run("remove-sessions", job_id) == 1
    assert "still listed after claude rm" in capsys.readouterr().err
    assert h.listed()[job_id]["sessions-removed"] is False


def test_remove_sessions_of_a_resumed_job_removes_the_shared_session_once(h, tmp_path):
    job_id, session = needs_input(h, tmp_path)
    assert h.run("resume", job_id) == 0
    write_result(h, job_id, DONE_RESULT)
    assert h.run("remove-sessions", job_id) == 0
    assert h.lines == [session]
    assert h.claude.removed == [fake_id(session)]


def test_remove_sessions_of_an_abandoned_job(h, tmp_path):
    job_id, session = launch(h, tmp_path)
    assert h.run("stop", job_id) == 0
    assert h.run("close", job_id) == 0
    assert h.run("remove-sessions", job_id) == 0
    assert h.lines == [session]
    assert session not in h.claude.sessions()


def test_remove_sessions_without_listed_sessions_prints_nothing(h, tmp_path):
    job_id, sessions = done_in_two_runs(h, tmp_path)
    h.claude.statuses.clear()
    assert h.run("remove-sessions", job_id) == 0
    assert h.lines == [] and h.claude.removed == []


@pytest.mark.parametrize("result", [FAILED_RESULT, NEEDS_INPUT_RESULT])
def test_remove_sessions_refuses_a_failed_or_open_job_and_keeps_its_sessions(h, tmp_path, capsys, result):
    job_id, session = launch(h, tmp_path)
    write_result(h, job_id, result)
    assert h.run("remove-sessions", job_id) == 1
    assert "remove-sessions needs done or abandoned" in capsys.readouterr().err
    assert h.claude.removed == [] and session in h.claude.sessions()


def test_remove_through_the_claude_binary_deletes_every_entry_of_the_id(tmp_path, fake_state):
    claude = ClaudeCli(str(FAKE_CLAUDE))
    claude.start("n", str(tmp_path), "/goal @g")
    listed = claude.sessions()["n"]
    claude.stop(listed.ids[0])
    assert claude.sessions()["n"].all_ids == listed.ids
    claude.remove(listed.ids[0])
    assert "n" not in claude.sessions()


# --- launch grace in list ---------------------------------------------------------------------------------

def test_list_reports_launched_right_after_launch_before_the_session_is_listed(h, tmp_path):
    job_id, session = launch(h, tmp_path)
    del h.claude.statuses[session]
    assert h.listed()[job_id]["state"] == "launched"
    h.clock.advance(LAUNCH_GRACE + timedelta(seconds=1))
    assert h.listed()[job_id]["state"] == "lost"


def test_a_session_listed_stopped_is_launched_inside_the_grace_until_cure_job_stop(h, tmp_path):
    job_id, session = launch(h, tmp_path)
    h.claude.statuses[session] = SessionStatus.STOPPED
    h.clock.advance(LAUNCH_GRACE)
    assert h.listed()[job_id]["state"] == "launched"
    assert h.run("stop", job_id) == 0
    assert h.lines == [f"{session} not live"]
    assert h.listed()[job_id]["state"] == "lost"
    assert h.run("launch", job_id) == 0


def test_stop_records_one_stopped_event_per_run(h, tmp_path):
    job_id, _ = launch(h, tmp_path)
    assert h.run("stop", job_id) == 0
    assert h.run("stop", job_id) == 0
    lines = (h.root / "jobs" / job_id / "dispatch.jsonl").read_text(encoding="utf-8").splitlines()
    assert [json.loads(line)["event"] for line in lines].count("stopped") == 1
