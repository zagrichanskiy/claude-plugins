"""Round 1 of the dispatcher workflow: the blocked state, ``stop``, ``reported`` and the ``origin`` refusal."""
from __future__ import annotations

from datetime import timedelta

import pytest

from cure_job.claude import Session, SessionStatus
from cure_job.events import Launched
from cure_job.job_id import session_name
from cure_job.state import LAUNCH_GRACE, State, derive
from tests.builders import NOW, make_record
from tests.fakes import fake_id
from tests.test_review_round1 import Harness

WAITING, BUSY, IDLE = SessionStatus.WAITING, SessionStatus.BUSY, SessionStatus.IDLE
A = "261013-1000-video-core-a"
NEEDS_INPUT_RESULT = "---\nstatus: needs-input\n---\nquestion"
DONE_RESULT = "---\nstatus: done\n---\n"


@pytest.fixture
def h(root):
    return Harness(root)


def state_of(age):
    record = make_record(A, events=(Launched(1, session_name(A, 1), NOW - age),))
    return derive([record], {session_name(A, 1): WAITING}, NOW, frozenset())[0].state


def launch(h, tmp_path, **kwargs):
    """A launched job; returns (job id, session name)."""
    job_id = h.new(tmp_path, **kwargs)
    assert h.run("launch", job_id) == 0
    return job_id, h.lines[0]


def write_result(h, job_id, text=DONE_RESULT):
    (h.root / "jobs" / job_id / "result.md").write_text(text, encoding="utf-8")


def events_text(h, job_id):
    return (h.root / "jobs" / job_id / "dispatch.jsonl").read_text(encoding="utf-8")


# --- blocked ----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("age", [timedelta(seconds=1), LAUNCH_GRACE, LAUNCH_GRACE + timedelta(seconds=1),
                                 timedelta(hours=3)])
def test_a_waiting_session_is_blocked_inside_and_after_the_grace_period(age):
    assert state_of(age) is State.BLOCKED


def test_blocked_is_open_has_a_session_and_is_not_launchable():
    assert State.BLOCKED.is_open and State.BLOCKED.has_session
    assert not State.BLOCKED.is_launchable


def test_a_waiting_session_with_a_result_is_needs_input_not_blocked():
    from tests.builders import result_of
    from cure_job.result import ResultStatus
    record = make_record(A, events=(Launched(1, session_name(A, 1), NOW - timedelta(minutes=5)),),
                         result=result_of(ResultStatus.NEEDS_INPUT))
    assert derive([record], {session_name(A, 1): WAITING}, NOW, frozenset())[0].state is State.NEEDS_INPUT


def test_close_refuses_a_blocked_job_and_names_the_stop_command(h, tmp_path, capsys):
    job_id, session = launch(h, tmp_path)
    h.claude.statuses[session] = WAITING
    assert h.run("close", job_id) == 1
    err = capsys.readouterr().err
    assert "blocked" in err and f"cure-job stop {job_id}" in err
    assert h.listed()[job_id]["state"] == "blocked"


def test_launch_refuses_a_blocked_job(h, tmp_path, capsys):
    job_id, session = launch(h, tmp_path)
    h.claude.statuses[session] = WAITING
    h.claude.started.clear()
    assert h.run("launch", job_id) == 1
    assert "blocked" in capsys.readouterr().err
    assert h.claude.started == []


def test_list_json_shows_waiting_for_only_while_blocked(h, tmp_path):
    job_id, session = launch(h, tmp_path)
    h.claude.waiting_for[session] = "approve Bash: rm build"
    h.claude.statuses[session] = WAITING
    row = h.listed()[job_id]
    assert (row["state"], row["waiting-for"]) == ("blocked", "approve Bash: rm build")
    h.claude.statuses[session] = BUSY
    row = h.listed()[job_id]
    assert (row["state"], row["waiting-for"]) == ("running", None)


def test_list_json_waiting_for_is_null_for_a_job_without_a_session(h, tmp_path):
    job_id = h.new(tmp_path)
    assert h.listed()[job_id]["waiting-for"] is None


def test_list_json_waiting_for_is_null_when_blocked_without_a_description(h, tmp_path):
    job_id, session = launch(h, tmp_path)
    h.claude.statuses[session] = WAITING
    assert h.listed()[job_id]["waiting-for"] is None


# --- stop -------------------------------------------------------------------------------------------------

def with_ids(h, session, ids, status=BUSY):
    """List ``session`` live under ``ids`` until ``stop`` is called, then stopped."""
    h.claude.sessions = lambda: {session: Session(SessionStatus.STOPPED) if h.claude.stopped
                                 else Session(status, None, tuple(ids))}


def test_stop_prints_the_session_name_and_stops_its_id(h, tmp_path):
    job_id, session = launch(h, tmp_path)
    assert h.run("stop", job_id) == 0
    assert h.lines == [session]
    assert h.claude.stopped == [fake_id(session)]
    assert h.listed()[job_id]["state"] == "lost"


def test_stop_stops_a_blocked_session_and_close_then_works(h, tmp_path):
    job_id, session = launch(h, tmp_path)
    h.claude.statuses[session] = WAITING
    assert h.run("stop", job_id) == 0
    assert h.run("close", job_id) == 0


def test_stop_stops_every_live_id_under_the_name(h, tmp_path):
    job_id, session = launch(h, tmp_path)
    with_ids(h, session, ["busy0001", "idle0001"])
    assert h.run("stop", job_id) == 0
    assert h.claude.stopped == ["busy0001", "idle0001"]


def test_stop_refuses_a_job_with_no_launched_run(h, tmp_path, capsys):
    job_id = h.new(tmp_path)
    assert h.run("stop", job_id) == 1
    assert "no launched run" in capsys.readouterr().err
    assert h.claude.stopped == []


def test_stop_of_a_session_the_listing_does_not_have_prints_not_live(h, tmp_path):
    job_id, session = launch(h, tmp_path)
    del h.claude.statuses[session]
    assert h.run("stop", job_id) == 0
    assert h.lines == [f"{session} not live"]
    assert h.claude.stopped == []


def test_stop_of_a_stopped_session_prints_not_live(h, tmp_path):
    job_id, session = launch(h, tmp_path)
    h.claude.statuses[session] = SessionStatus.STOPPED
    assert h.run("stop", job_id) == 0
    assert h.lines == [f"{session} not live"]
    assert h.claude.stopped == []


@pytest.mark.parametrize("ids", [[""], ["good0001", ""], []])
def test_stop_refuses_a_live_entry_without_an_id_and_stops_nothing(h, tmp_path, capsys, ids):
    job_id, session = launch(h, tmp_path)
    with_ids(h, session, ids)
    assert h.run("stop", job_id) == 1
    assert "without an id" in capsys.readouterr().err
    assert h.claude.stopped == []


def test_stop_refuses_an_unknown_job(h, capsys):
    assert h.run("stop", "261013-1800-video-core-nothing") == 1
    assert "unknown job" in capsys.readouterr().err


def test_stop_reads_the_session_list_even_for_a_job_with_a_result(h, tmp_path):
    job_id, session = launch(h, tmp_path)
    write_result(h, job_id, NEEDS_INPUT_RESULT)
    assert h.run("stop", job_id) == 0
    assert h.claude.stopped == [fake_id(session)]


def test_stop_with_a_malformed_id_exits_two(h):
    with pytest.raises(SystemExit) as caught:
        h.run("stop", "not a job id")
    assert caught.value.code == 2


def test_stop_without_an_id_exits_two(h):
    with pytest.raises(SystemExit) as caught:
        h.run("stop")
    assert caught.value.code == 2


# --- reported ---------------------------------------------------------------------------------------------

def test_reported_appends_one_event_for_the_latest_run(h, tmp_path):
    job_id, _ = launch(h, tmp_path)
    write_result(h, job_id)
    assert h.run("reported", job_id) == 0
    assert h.lines == []
    lines = [line for line in events_text(h, job_id).splitlines() if '"reported"' in line]
    assert len(lines) == 1 and '"run":1' in lines[0] and '"at":' in lines[0]


def test_list_json_reported_is_false_until_marked_then_true(h, tmp_path):
    job_id, _ = launch(h, tmp_path)
    write_result(h, job_id, NEEDS_INPUT_RESULT)
    assert h.listed()[job_id]["reported"] is False
    assert h.run("reported", job_id) == 0
    assert h.listed()[job_id]["reported"] is True


def test_reported_is_false_for_a_job_that_was_never_launched(h, tmp_path):
    job_id = h.new(tmp_path)
    assert h.listed()[job_id]["reported"] is False


def test_a_relaunch_makes_reported_false_for_the_new_run(h, tmp_path):
    job_id, session = launch(h, tmp_path)
    write_result(h, job_id, NEEDS_INPUT_RESULT)
    assert h.run("reported", job_id) == 0
    del h.claude.statuses[session]  # launch refuses while the needs-input session is live
    assert h.run("launch", job_id) == 0
    row = h.listed()[job_id]
    assert (row["run"], row["reported"]) == (2, False)


def test_reporting_the_second_run_marks_only_the_second_run(h, tmp_path):
    job_id, session = launch(h, tmp_path)
    write_result(h, job_id, NEEDS_INPUT_RESULT)
    assert h.run("reported", job_id) == 0
    del h.claude.statuses[session]  # launch refuses while the needs-input session is live
    assert h.run("launch", job_id) == 0
    write_result(h, job_id)
    assert h.run("reported", job_id) == 0
    assert h.listed()[job_id]["reported"] is True
    assert events_text(h, job_id).count('"event":"reported"') == 2


def test_a_repeated_reported_call_writes_nothing(h, tmp_path):
    job_id, _ = launch(h, tmp_path)
    write_result(h, job_id)
    assert h.run("reported", job_id) == 0
    before = events_text(h, job_id)
    assert h.run("reported", job_id) == 0
    assert events_text(h, job_id) == before


def test_reported_refuses_a_job_without_a_launched_run(h, tmp_path, capsys):
    job_id = h.new(tmp_path)
    write_result(h, job_id)
    assert h.run("reported", job_id) == 1
    assert "no launched run" in capsys.readouterr().err
    assert "reported" not in (events_text(h, job_id) if (h.root / "jobs" / job_id / "dispatch.jsonl").exists() else "")


def test_reported_refuses_a_job_without_result_md(h, tmp_path, capsys):
    job_id, _ = launch(h, tmp_path)
    assert h.run("reported", job_id) == 1
    assert "has no result" in capsys.readouterr().err
    assert '"reported"' not in events_text(h, job_id)


def test_reported_refuses_an_unknown_job(h, capsys):
    assert h.run("reported", "261013-1800-video-core-nothing") == 1
    assert capsys.readouterr().err.startswith("error:")


def test_reported_with_a_malformed_id_exits_two(h):
    with pytest.raises(SystemExit) as caught:
        h.run("reported", "not a job id")
    assert caught.value.code == 2


# --- origin -----------------------------------------------------------------------------------------------

def test_origin_is_accepted_before_the_first_launch(h, tmp_path):
    job_id = h.new(tmp_path)
    assert h.run("origin", job_id, "main-session") == 0
    assert h.listed()[job_id]["origin"] == "main-session"


def test_origin_is_refused_once_the_job_has_a_launched_event(h, tmp_path, capsys):
    job_id, _ = launch(h, tmp_path)
    before = events_text(h, job_id)
    assert h.run("origin", job_id, "main-session") == 1
    assert "launched run" in capsys.readouterr().err
    assert events_text(h, job_id) == before
    assert h.listed()[job_id]["origin"] is None


@pytest.mark.parametrize("address", ["", " main", "main ", "\tmain", "main\n", "main\nother", "a\nb"])
def test_origin_with_an_empty_padded_or_multi_line_address_exits_two(h, tmp_path, address):
    job_id = h.new(tmp_path)
    with pytest.raises(SystemExit) as caught:
        h.run("origin", job_id, address)
    assert caught.value.code == 2
    assert h.listed()[job_id]["origin"] is None


# --- stop: the wait loop ----------------------------------------------------------------------------------

class FakeTime:
    """A monotonic clock that only the fake sleep advances, so the wait loop never really sleeps."""

    def __init__(self):
        self.now = 100.0
        self.slept: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def stop_harness(root):
    fake = FakeTime()
    return Harness(root, sleep=fake.sleep, monotonic=fake.monotonic), fake


def test_stop_polls_every_half_second_until_the_session_goes_down(root, tmp_path):
    h, fake = stop_harness(root)
    job_id, session = launch(h, tmp_path)
    polls_live = 3
    polled = []

    def sessions():
        if h.claude.stopped:
            polled.append(1)
            if len(polled) > polls_live:
                return {session: Session(SessionStatus.STOPPED)}
        return {session: Session(BUSY, None, (fake_id(session),))}

    h.claude.sessions = sessions
    assert h.run("stop", job_id) == 0
    assert h.lines == [session]
    assert fake.slept == [0.5] * polls_live
    assert h.claude.stopped == [fake_id(session)]


def test_stop_does_not_sleep_when_the_session_is_down_at_once(root, tmp_path):
    h, fake = stop_harness(root)
    job_id, session = launch(h, tmp_path)
    assert h.run("stop", job_id) == 0
    assert fake.slept == []


def test_stop_fails_when_the_session_is_still_live_after_the_timeout(root, tmp_path, capsys):
    h, fake = stop_harness(root)
    job_id, session = launch(h, tmp_path)
    h.claude.sessions = lambda: {session: Session(BUSY, None, (fake_id(session),))}
    assert h.run("stop", job_id) == 1
    assert "still live after claude stop" in capsys.readouterr().err
    assert h.lines == []
    assert h.claude.stopped == [fake_id(session)]
    assert sum(fake.slept) == pytest.approx(15.0)
