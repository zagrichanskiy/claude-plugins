"""The session fold: ``launched`` and ``stopped`` lines read as work sessions, and the record's session members."""
from __future__ import annotations

from datetime import timedelta

import pytest

from cure_job.events import Reported, SessionEnded, SessionStarted, SessionStopped, decode, encode
from cure_job.result import ResultStatus
from cure_job.sessions import JobSession, fold
from tests.builders import NOW, make_record, result_of

A = "261013-1000-video-core-a"
EARLIER = NOW - timedelta(minutes=5)


def work(n: int, name: str = A, at=EARLIER) -> SessionStarted:
    return SessionStarted("work", n, name, at, n)


def goal(n: int, run: int = 0, name: str = A + "-goal") -> SessionStarted:
    return SessionStarted("goal", n, f"{name}-{n}", NOW, run, ("answers-1.md",))


# --- events -----------------------------------------------------------------------------------------------------------

def test_a_launched_line_decodes_as_a_work_session_and_encodes_to_the_same_bytes():
    line = '{"event":"launched","run":3,"session":"x-r3","at":"2026-10-13T17:42:05+00:00"}'
    event = decode(line)
    assert (event.kind, event.n, event.run, event.session, event.inputs) == ("work", 3, 3, "x-r3", ())
    assert encode(event) == line


def test_a_stopped_line_decodes_as_a_work_stop_and_encodes_to_the_same_bytes():
    line = '{"event":"stopped","run":2,"at":"2026-10-13T17:42:05+00:00"}'
    event = decode(line)
    assert event == SessionStopped("work", 2, event.at)
    assert encode(event) == line


@pytest.mark.parametrize("n, run, inputs", [(1, 2, ()), (1, 1, ("answers-1.md",))])
def test_a_work_session_needs_n_equal_to_run_and_no_inputs(n, run, inputs):
    with pytest.raises(ValueError, match="work session"):
        SessionStarted("work", n, A, NOW, run, inputs)


@pytest.mark.parametrize("event, tag", [(goal(1), "session-started"), (SessionStopped("goal", 1, NOW), "session-stopped"),
                                        (SessionEnded("goal", 1, ("settled",), NOW), "session-ended")])
def test_a_session_event_of_another_kind_has_its_own_line_and_decodes_back(event, tag):
    line = encode(event)
    assert line.startswith(f'{{"event":"{tag}","kind":"goal",')
    assert decode(line) == event


# --- fold -------------------------------------------------------------------------------------------------------------

def test_fold_of_no_session_events_is_empty():
    assert fold((Reported(1, NOW),), has_result=False) == ()


def test_fold_keeps_the_start_facts():
    assert fold((work(1, at=NOW),), has_result=False) == (
        JobSession(kind="work", n=1, name=A, run=1, started_at=NOW, inputs=(), ended=False, summary=(),
                   stop_recorded=False),)


def test_a_work_session_ends_when_a_later_work_session_starts():
    assert [session.ended for session in fold((work(1), work(2, A + "-r2")), has_result=False)] == [True, False]


def test_the_latest_work_session_ends_with_result_md():
    assert [session.ended for session in fold((work(1), work(2, A + "-r2")), has_result=True)] == [True, True]


def test_a_session_of_another_kind_does_not_end_the_work_session():
    sessions = fold((work(1), goal(1, run=1)), has_result=False)
    assert [(session.kind, session.ended) for session in sessions] == [("work", False), ("goal", False)]


def test_result_md_does_not_end_a_session_of_another_kind():
    assert fold((goal(1),), has_result=True)[0].ended is False


def test_a_stop_marks_only_the_session_of_its_kind_and_n():
    sessions = fold((work(1), SessionStopped("work", 1, NOW), work(2, A + "-r2"), goal(2)), has_result=False)
    assert [session.stop_recorded for session in sessions] == [True, False, False]


# --- JobRecord --------------------------------------------------------------------------------------------------------

def test_a_record_without_sessions():
    record = make_record(A)
    assert (record.sessions, record.run, record.session, record.session_names) == ((), 0, None, ())
    assert record.latest("work") is None
    assert record.open_sessions() == ()
    assert record.restarts("work") == 0


def test_run_counts_work_sessions_and_session_is_the_latest_work_name():
    record = make_record(A, events=(work(1), goal(1, run=1), work(2, A + "-r2"), goal(2, run=2)))
    assert (record.run, record.session) == (2, A + "-r2")
    assert record.latest("work").n == 2
    assert record.latest("goal").name == A + "-goal-2"


def test_session_names_cover_every_kind_in_first_seen_order_without_repeats():
    record = make_record(A, events=(work(1), goal(1, run=1), work(2)))
    assert record.session_names == (A, A + "-goal-1")


def test_open_sessions_are_the_latest_of_each_kind_not_ended():
    record = make_record(A, events=(work(1), goal(1, run=1), goal(2, run=1)), result=result_of(ResultStatus.DONE))
    assert [(session.kind, session.n) for session in record.open_sessions()] == [("goal", 2)]


def test_restarts_count_the_starts_that_followed_an_open_session_of_the_kind():
    record = make_record(A, events=(goal(1), goal(2), goal(3), work(1)))
    assert record.restarts("goal") == 2
    assert record.restarts("work") == 0


def test_restarts_of_work_are_zero_across_relaunches():
    assert make_record(A, events=(work(1), work(2), work(3))).restarts("work") == 0


def test_sessions_are_folded_once_per_record():
    record = make_record(A, events=(work(1),))
    assert record.sessions is record.sessions
