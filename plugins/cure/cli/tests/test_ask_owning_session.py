"""``ask`` and ``answered``: a job that asks its owner is awaiting-answer, and the dispatcher leaves a reachable owner alone."""
from __future__ import annotations

import dataclasses
import json
from datetime import timedelta

import pytest

from cure_job.claude import SessionStatus
from cure_job.clock import format_local
from cure_job.errors import ClaudeError, ClaudeOutcomeUnknown
from cure_job.cli import Cli
from cure_job.events import SessionStarted
from cure_job.job_id import session_name
from cure_job.state import LAUNCH_GRACE, State, derive
from tests.builders import NOW, listed, make_record
from tests.fakes import FakeClaude
from tests.test_cli import Harness, _next

ORIGIN_PID = 4242
ORIGIN = f"uds:/run/cure/{ORIGIN_PID}.sock"
OWNER_SESSION = "owner-session"
A = "261013-1000-video-core-a"
QUESTION = ["Which branch?", "Keep the old API?"]


class PidClaude(FakeClaude):
    """A listing whose sessions carry the pids in ``pids``: one pid or a tuple of the pids of the live entries."""

    def __init__(self):
        super().__init__()
        self.pids: dict[str, int | tuple[int, ...]] = {}

    def sessions(self):
        def pids(name):
            value = self.pids[name]
            return value if isinstance(value, tuple) else (value,)
        return {name: dataclasses.replace(session, pids=pids(name)) if name in self.pids else session
                for name, session in super().sessions().items()}


@pytest.fixture
def h(root):
    harness = Harness(root)
    harness.claude = PidClaude()
    harness.sleeps = []
    harness.on_sleep = lambda: None

    def sleep(seconds):
        harness.sleeps.append(seconds)
        assert len(harness.sleeps) < 50, "await-answer polled without end"
        harness.on_sleep()

    harness.cli = Cli(root=root, config_path=root / "config.json", claude=harness.claude, clock=harness.clock,
                      out=harness.lines.append, sleep=sleep)
    return harness


def events(h, job_id, kind):
    lines = (h.root / "jobs" / job_id / "dispatch.jsonl").read_text(encoding="utf-8").splitlines()
    return [e for e in map(json.loads, lines) if e["event"] == kind]


def row(h, job_id):
    h.lines.clear()
    assert h.run("list", "--json") == 0
    return {r["id"]: r for r in json.loads(h.lines[0])}[job_id]


def ask(h, job_id, *questions):
    argv = ["ask", job_id]
    for question in questions or QUESTION:
        argv += ["--question", question]
    return h.run(*argv)


def asking_job(h, tmp_path, monkeypatch, reachable=True, origin=ORIGIN):
    """A launched job with an origin, whose run session is the caller."""
    job_id = h.new(tmp_path)
    if origin:
        assert h.run("origin", job_id, origin) == 0
    h.approve(job_id)
    assert h.run("launch", job_id) == 0
    if reachable:
        h.claude.statuses[OWNER_SESSION] = SessionStatus.BUSY
        h.claude.pids[OWNER_SESSION] = ORIGIN_PID
    monkeypatch.setenv("CURE_JOB_ID", job_id)
    return job_id


def work_session(h, job_id):
    return row(h, job_id)["session"]


# --- state -------------------------------------------------------------------------------------------------

def test_an_asking_job_is_awaiting_answer_not_stalled(h, tmp_path, monkeypatch):
    job_id = asking_job(h, tmp_path, monkeypatch)
    assert ask(h, job_id) == 0
    h.claude.statuses[work_session(h, job_id)] = SessionStatus.IDLE
    h.clock.advance(LAUNCH_GRACE + timedelta(minutes=1))
    assert row(h, job_id)["state"] == "awaiting-answer"
    assert row(h, job_id)["question"] == QUESTION


def test_a_job_that_did_not_ask_still_stalls_and_has_a_null_question(h, tmp_path, monkeypatch):
    job_id = asking_job(h, tmp_path, monkeypatch)
    h.claude.statuses[work_session(h, job_id)] = SessionStatus.IDLE
    h.clock.advance(LAUNCH_GRACE + timedelta(minutes=1))
    assert row(h, job_id)["state"] == "stalled"
    assert row(h, job_id)["question"] is None


def test_an_asking_job_that_is_gone_is_lost_and_one_that_is_busy_is_awaiting_answer():
    name = session_name(A, 1)
    started = SessionStarted("work", 1, name, NOW - timedelta(hours=1), 1)
    asked = make_record(A, events=(started, _asked(1)))
    def state(status):
        return derive([asked], listed({name: status}) if status else {}, NOW, frozenset())[0].state
    assert state(SessionStatus.BUSY) is State.AWAITING_ANSWER
    assert state(None) is State.LOST


def _asked(run):
    from cure_job.events import Asked
    return Asked(run, tuple(QUESTION), NOW)


def test_awaiting_answer_is_an_open_state():
    assert State.AWAITING_ANSWER.is_open


def test_a_job_is_running_again_after_the_answer_is_recorded(h, tmp_path, monkeypatch):
    job_id = asking_job(h, tmp_path, monkeypatch)
    assert ask(h, job_id) == 0
    h.claude.statuses[work_session(h, job_id)] = SessionStatus.IDLE
    h.clock.advance(LAUNCH_GRACE + timedelta(minutes=1))
    assert h.run("answered", job_id, "--answer", "main", "--answer", "yes") == 0
    assert [e["answer"] for e in events(h, job_id, "answered")] == [["main", "yes"]]
    assert events(h, job_id, "answered")[0]["run"] == 1
    h.claude.statuses[work_session(h, job_id)] = SessionStatus.BUSY
    assert row(h, job_id)["state"] == "running"
    assert row(h, job_id)["question"] is None


def test_ask_records_an_asked_event_and_prints_a_notify_line_naming_the_origin(h, tmp_path, monkeypatch):
    job_id = asking_job(h, tmp_path, monkeypatch)
    assert ask(h, job_id) == 0
    [event] = events(h, job_id, "asked")
    assert (event["run"], event["question"]) == (1, QUESTION) and "at" in event
    assert h.lines[-1].startswith("notify:") and ORIGIN in h.lines[-1]


def test_a_repeated_answered_call_is_a_no_op(h, tmp_path, monkeypatch):
    job_id = asking_job(h, tmp_path, monkeypatch)
    assert ask(h, job_id) == 0
    assert h.run("answered", job_id, "--answer", "main") == 0
    assert h.run("answered", job_id, "--answer", "main") == 0
    assert len(events(h, job_id, "answered")) == 1


def test_answered_without_a_pending_question_exits_one(h, tmp_path, monkeypatch):
    job_id = asking_job(h, tmp_path, monkeypatch)
    assert h.run("answered", job_id, "--answer", "main") == 1
    assert events(h, job_id, "answered") == []


def test_answered_by_a_session_that_is_not_the_job_exits_one(h, tmp_path, monkeypatch):
    job_id = asking_job(h, tmp_path, monkeypatch)
    assert ask(h, job_id) == 0
    monkeypatch.setenv("CURE_JOB_ID", "261013-1000-video-core-other")
    assert h.run("answered", job_id, "--answer", "main") == 1
    assert events(h, job_id, "answered") == []


# --- ask refusals ------------------------------------------------------------------------------------------

def test_ask_is_refused_when_the_origin_is_not_reachable(h, tmp_path, monkeypatch, capsys):
    job_id = asking_job(h, tmp_path, monkeypatch, reachable=False)
    assert ask(h, job_id) == 1
    assert "origin" in capsys.readouterr().err
    assert events(h, job_id, "asked") == []


def test_ask_is_refused_when_the_caller_is_not_the_job_session(h, tmp_path, monkeypatch):
    job_id = asking_job(h, tmp_path, monkeypatch)
    monkeypatch.setenv("CURE_JOB_ID", "261013-1000-video-core-other")
    assert ask(h, job_id) == 1
    monkeypatch.delenv("CURE_JOB_ID")
    assert ask(h, job_id) == 1
    assert events(h, job_id, "asked") == []


def test_ask_is_refused_without_an_origin(h, tmp_path, monkeypatch):
    job_id = asking_job(h, tmp_path, monkeypatch, origin=None)
    assert ask(h, job_id) == 1


def test_ask_is_refused_when_a_result_exists_for_the_run(h, tmp_path, monkeypatch):
    job_id = asking_job(h, tmp_path, monkeypatch)
    (h.root / "jobs" / job_id / "result.md").write_text("---\nstatus: done\n---\n", encoding="utf-8")
    assert ask(h, job_id) == 1


def test_ask_is_refused_for_an_abandoned_job(h, tmp_path, monkeypatch):
    job_id = asking_job(h, tmp_path, monkeypatch)
    h.claude.statuses[work_session(h, job_id)] = SessionStatus.STOPPED
    h.clock.advance(LAUNCH_GRACE + timedelta(minutes=1))
    assert h.run("close", job_id) == 0
    assert ask(h, job_id) == 1


def test_ask_is_refused_for_a_job_that_was_never_launched(h, tmp_path, monkeypatch):
    job_id = h.new(tmp_path)
    assert h.run("origin", job_id, ORIGIN) == 0
    monkeypatch.setenv("CURE_JOB_ID", job_id)
    assert ask(h, job_id) == 1


def test_ask_without_a_question_is_a_usage_error(h, tmp_path, monkeypatch, capsys):
    job_id = asking_job(h, tmp_path, monkeypatch)
    with pytest.raises(SystemExit) as caught:
        h.run("ask", job_id)
    assert caught.value.code == 2
    assert "--question" in capsys.readouterr().err


# --- routing -----------------------------------------------------------------------------------------------

def routes(h):
    return {name: arg.get("route") for item in _next(h) for name, arg in zip(item["actions"], item["args"])}


def test_a_reachable_owner_gets_route_origin_for_ask_approval(h, tmp_path):
    job_id = h.new(tmp_path)
    assert h.run("origin", job_id, ORIGIN) == 0
    (h.root / "jobs" / job_id / "goal.md").write_text("goal", encoding="utf-8")
    h.claude.statuses[OWNER_SESSION] = SessionStatus.BUSY
    h.claude.pids[OWNER_SESSION] = ORIGIN_PID
    assert routes(h) == {"ask-approval": "origin"}


def test_an_unreachable_owner_gets_route_dispatcher_for_ask_approval(h, tmp_path):
    job_id = h.new(tmp_path)
    assert h.run("origin", job_id, ORIGIN) == 0
    (h.root / "jobs" / job_id / "goal.md").write_text("goal", encoding="utf-8")
    assert routes(h) == {"ask-approval": "dispatcher"}


def test_a_reachable_owner_gets_route_origin_for_report_and_ask_input(h, tmp_path, monkeypatch):
    job_id = asking_job(h, tmp_path, monkeypatch)
    (h.root / "jobs" / job_id / "result.md").write_text("---\nstatus: needs-input\n---\n", encoding="utf-8")
    assert routes(h) == {"report": "origin", "ask-input": "origin"}


def test_an_unreachable_owner_gets_route_dispatcher_for_report(h, tmp_path, monkeypatch):
    job_id = asking_job(h, tmp_path, monkeypatch, reachable=False)
    (h.root / "jobs" / job_id / "result.md").write_text("---\nstatus: done\n---\n", encoding="utf-8")
    assert routes(h)["report"] == "dispatcher"


def test_a_stopped_owner_session_is_not_reachable(h, tmp_path, monkeypatch):
    job_id = asking_job(h, tmp_path, monkeypatch)
    h.claude.statuses[OWNER_SESSION] = SessionStatus.STOPPED
    (h.root / "jobs" / job_id / "result.md").write_text("---\nstatus: done\n---\n", encoding="utf-8")
    assert routes(h)["report"] == "dispatcher"


def test_an_awaiting_answer_job_with_an_unreachable_owner_gets_ask_input_with_the_question(h, tmp_path, monkeypatch):
    job_id = asking_job(h, tmp_path, monkeypatch)
    assert ask(h, job_id) == 0
    h.claude.statuses[OWNER_SESSION] = SessionStatus.STOPPED
    h.claude.statuses[work_session(h, job_id)] = SessionStatus.IDLE
    h.clock.advance(LAUNCH_GRACE + timedelta(minutes=1))
    [item] = _next(h)
    assert item["state"] == "awaiting-answer"
    assert item["actions"] == ["ask-input"]
    assert item["args"][0]["route"] == "dispatcher"
    assert item["args"][0]["question"] == QUESTION


def test_an_awaiting_answer_job_with_a_reachable_owner_never_gets_confirm_stalled(h, tmp_path, monkeypatch):
    job_id = asking_job(h, tmp_path, monkeypatch)
    assert ask(h, job_id) == 0
    h.claude.statuses[work_session(h, job_id)] = SessionStatus.IDLE
    h.clock.advance(LAUNCH_GRACE + timedelta(minutes=1))
    assert "confirm-stalled" not in [name for item in _next(h) for name in item["actions"]]


def reachable_owner(h, pids=ORIGIN_PID):
    h.claude.statuses[OWNER_SESSION] = SessionStatus.BUSY
    h.claude.pids[OWNER_SESSION] = pids


def write_result(h, job_id, text):
    (h.root / "jobs" / job_id / "result.md").write_text(text, encoding="utf-8")


def awaiting_answer_job(h, tmp_path, monkeypatch, *question, owner_gone=True):
    job_id = asking_job(h, tmp_path, monkeypatch)
    assert ask(h, job_id, *question) == 0
    if owner_gone:
        h.claude.statuses[OWNER_SESSION] = SessionStatus.STOPPED
    h.claude.statuses[work_session(h, job_id)] = SessionStatus.IDLE
    h.clock.advance(LAUNCH_GRACE + timedelta(minutes=1))
    return job_id


# --- await-answer ------------------------------------------------------------------------------------------

def test_await_answer_exits_zero_at_once_when_the_question_is_already_answered(h, tmp_path, monkeypatch):
    job_id = asking_job(h, tmp_path, monkeypatch)
    assert ask(h, job_id) == 0
    assert h.run("answered", job_id, "--answer", "main") == 0
    assert h.run("await-answer", job_id) == 0


def test_await_answer_polls_until_the_answer_is_recorded(h, tmp_path, monkeypatch):
    job_id = asking_job(h, tmp_path, monkeypatch)
    assert ask(h, job_id) == 0
    h.on_sleep = lambda: len(h.sleeps) == 3 and h.run("answered", job_id, "--answer", "main")
    assert h.run("await-answer", job_id) == 0
    assert len(h.sleeps) == 3


def test_await_answer_exits_one_when_the_run_gets_a_result(h, tmp_path, monkeypatch):
    job_id = asking_job(h, tmp_path, monkeypatch)
    assert ask(h, job_id) == 0
    h.on_sleep = lambda: write_result(h, job_id, "---\nstatus: done\n---\n")
    assert h.run("await-answer", job_id) == 1


def test_await_answer_exits_one_when_the_job_is_abandoned(h, tmp_path, monkeypatch):
    job_id = asking_job(h, tmp_path, monkeypatch)
    assert ask(h, job_id) == 0
    h.claude.statuses[work_session(h, job_id)] = SessionStatus.STOPPED
    h.clock.advance(LAUNCH_GRACE + timedelta(minutes=1))
    assert h.run("close", job_id) == 0
    assert h.run("await-answer", job_id) == 1


def test_await_answer_exits_one_when_no_question_was_asked_in_the_run(h, tmp_path, monkeypatch):
    job_id = asking_job(h, tmp_path, monkeypatch)
    assert h.run("await-answer", job_id) == 1
    assert h.sleeps == []


def test_await_answer_exits_one_when_the_caller_is_not_the_job(h, tmp_path, monkeypatch):
    job_id = asking_job(h, tmp_path, monkeypatch)
    assert ask(h, job_id) == 0
    monkeypatch.setenv("CURE_JOB_ID", "261013-1000-video-core-other")
    assert h.run("await-answer", job_id) == 1


# --- requested ---------------------------------------------------------------------------------------------

def actions_of(h):
    return [name for item in _next(h) for name in item["actions"]]


def test_requested_appends_a_requested_event_for_the_run(h, tmp_path):
    job_id = h.new(tmp_path)
    assert h.run("origin", job_id, ORIGIN) == 0
    (h.root / "jobs" / job_id / "goal.md").write_text("goal", encoding="utf-8")
    assert h.run("requested", job_id, "--action", "ask-approval") == 0
    [event] = events(h, job_id, "requested")
    assert (event["run"], event["action"], event["at"]) == (0, "ask-approval", format_local(h.clock.now))


def test_requested_rejects_an_action_that_is_not_a_route_action(h, tmp_path):
    job_id = h.new(tmp_path)
    with pytest.raises(SystemExit) as caught:
        h.run("requested", job_id, "--action", "report")
    assert caught.value.code == 2


def test_next_omits_a_requested_ask_approval_of_a_reachable_owner_until_the_goal_changes(h, tmp_path):
    job_id = h.new(tmp_path)
    assert h.run("origin", job_id, ORIGIN) == 0
    goal = h.root / "jobs" / job_id / "goal.md"
    goal.write_text("goal", encoding="utf-8")
    reachable_owner(h)
    assert actions_of(h) == ["ask-approval"]
    assert h.run("requested", job_id, "--action", "ask-approval") == 0
    assert actions_of(h) == []
    goal.write_text("goal, revised", encoding="utf-8")
    assert actions_of(h) == ["ask-approval"]


def test_next_omits_a_requested_ask_input_but_keeps_report(h, tmp_path, monkeypatch):
    job_id = asking_job(h, tmp_path, monkeypatch)
    write_result(h, job_id, "---\nstatus: needs-input\n---\n")
    assert h.run("requested", job_id, "--action", "ask-input") == 0
    assert actions_of(h) == ["report"]


def test_next_omits_a_requested_ask_timeout(h, tmp_path, monkeypatch):
    job_id = asking_job(h, tmp_path, monkeypatch)
    write_result(h, job_id, "---\nstatus: needs-input\nquestion:\n  - 'short-hold timeout: gpu held by x'\n---\n")
    assert "ask-timeout" in actions_of(h)
    assert h.run("requested", job_id, "--action", "ask-timeout") == 0
    assert "ask-timeout" not in actions_of(h)


def test_next_never_suppresses_a_dispatcher_route_action(h, tmp_path):
    job_id = h.new(tmp_path)
    assert h.run("origin", job_id, ORIGIN) == 0
    (h.root / "jobs" / job_id / "goal.md").write_text("goal", encoding="utf-8")
    reachable_owner(h)
    assert h.run("requested", job_id, "--action", "ask-approval") == 0
    h.claude.statuses[OWNER_SESSION] = SessionStatus.STOPPED
    assert routes(h) == {"ask-approval": "dispatcher"}


# --- short-hold timeout of an awaiting-answer job ----------------------------------------------------------

def test_an_awaiting_answer_job_asking_a_short_hold_timeout_gets_ask_timeout_for_the_dispatcher(h, tmp_path,
                                                                                               monkeypatch):
    awaiting_answer_job(h, tmp_path, monkeypatch, "short-hold timeout: gpu held by 261013-1000-video-core-b")
    [item] = _next(h)
    assert item["actions"] == ["ask-timeout"]
    assert item["args"][0]["route"] == "dispatcher"


def test_a_multi_line_question_led_by_a_short_hold_timeout_gets_ask_input_with_every_line(h, tmp_path,
                                                                                          monkeypatch):
    question = ["short-hold timeout: gpu held by 261013-1000-video-core-b", "Which board?"]
    awaiting_answer_job(h, tmp_path, monkeypatch, *question)
    [item] = _next(h)
    assert item["actions"] == ["ask-input"]
    assert item["args"][0]["question"] == question


# --- a session list that cannot be read --------------------------------------------------------------------

BROKEN = [ClaudeError("claude agents: exit 1"), ClaudeOutcomeUnknown("claude agents: no exit within 60 seconds")]


@pytest.mark.parametrize("error", BROKEN)
def test_a_failing_session_list_routes_ask_approval_to_the_dispatcher(h, tmp_path, error):
    job_id = h.new(tmp_path)
    assert h.run("origin", job_id, ORIGIN) == 0
    (h.root / "jobs" / job_id / "goal.md").write_text("goal", encoding="utf-8")
    reachable_owner(h)
    h.claude.fail_sessions = error
    assert routes(h) == {"ask-approval": "dispatcher"}
    assert row(h, job_id)["state"] == "awaiting-approval"


@pytest.mark.parametrize("error", BROKEN)
def test_a_failing_session_list_routes_the_report_of_a_done_job_to_the_dispatcher(h, tmp_path, monkeypatch, error):
    job_id = asking_job(h, tmp_path, monkeypatch)
    write_result(h, job_id, "---\nstatus: done\n---\n")
    h.claude.fail_sessions = error
    assert routes(h)["report"] == "dispatcher"
    assert row(h, job_id)["state"] == "done"


# --- the question and asked_at of a list row ---------------------------------------------------------------

def test_a_working_job_row_carries_the_question_and_when_it_was_asked(h, tmp_path, monkeypatch):
    job_id = asking_job(h, tmp_path, monkeypatch)
    assert row(h, job_id)["asked-at"] is None
    assert ask(h, job_id) == 0
    found = row(h, job_id)
    assert (found["question"], found["asked-at"]) == (QUESTION, format_local(h.clock.now))


def test_a_needs_input_job_that_asked_and_got_no_answer_has_a_null_question(h, tmp_path, monkeypatch):
    job_id = asking_job(h, tmp_path, monkeypatch)
    assert ask(h, job_id) == 0
    write_result(h, job_id, "---\nstatus: needs-input\n---\n")
    found = row(h, job_id)
    assert (found["phase"], found["question"]) == ("needs-input", None)


# --- an origin that cannot be reached by pid ---------------------------------------------------------------

def test_new_warns_once_about_an_origin_that_is_not_a_pid_socket(h, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CLAUDE_CODE_MESSAGING_SOCKET", "/run/session.sock")
    h.new(tmp_path)
    err = capsys.readouterr().err.splitlines()
    assert len(err) == 1 and "origin" in err[0]


def test_new_does_not_warn_about_a_pid_socket_origin(h, tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("CLAUDE_CODE_MESSAGING_SOCKET", f"/run/cure/{ORIGIN_PID}.sock")
    h.new(tmp_path)
    assert capsys.readouterr().err == ""


def test_an_owner_is_reachable_by_a_pid_of_any_of_its_live_entries(h, tmp_path):
    job_id = h.new(tmp_path)
    assert h.run("origin", job_id, ORIGIN) == 0
    (h.root / "jobs" / job_id / "goal.md").write_text("goal", encoding="utf-8")
    reachable_owner(h, (1, ORIGIN_PID))
    assert routes(h) == {"ask-approval": "origin"}
