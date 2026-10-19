"""State derivation (the States table), the lock rule, retention and the session-need predicate.

Every test builds ``JobRecord`` values by hand: ``derive`` is pure and touches no filesystem."""
from __future__ import annotations

from datetime import timedelta

import pytest

from cure_job.claude import SessionStatus
from cure_job.events import Claim, Closed, Launched, StopIssued
from cure_job.handoff import Device
from cure_job.resource import DEVICE_BENCH
from cure_job.result import ResultStatus
from cure_job.state import LAUNCH_GRACE, RETENTION, State, derive, expired, needs_sessions
from tests.builders import NOW, make_record, result_of

BUSY, IDLE, STOPPED = SessionStatus.BUSY, SessionStatus.IDLE, SessionStatus.STOPPED
A = "261013-1000-video-core-a"
B = "261013-1001-video-core-b"
C = "261013-1002-video-core-c"


def launched(job_id: str, run: int = 1, age: timedelta = timedelta(minutes=5)) -> Launched:
    from cure_job.job_id import session_name
    return Launched(run, session_name(job_id, run), NOW - age)


def state_of(record, sessions=None, now=NOW):
    return derive([record], sessions or {}, now)[0].state


def states(records, sessions=None, now=NOW):
    return {view.record.id: view.state for view in derive(records, sessions or {}, now)}


# --- one test per States row ------------------------------------------------------------------------

def test_row_1_closed_event_is_abandoned():
    assert state_of(make_record(A, events=(Closed("superseded"),))) is State.ABANDONED


def test_row_2_failed_result_is_failed():
    assert state_of(make_record(A, result=result_of(ResultStatus.FAILED))) is State.FAILED


def test_row_3_done_result_without_unproven_is_done():
    assert state_of(make_record(A, result=result_of(ResultStatus.DONE))) is State.DONE


def test_row_4_needs_input_result_is_needs_input():
    assert state_of(make_record(A, result=result_of(ResultStatus.NEEDS_INPUT))) is State.NEEDS_INPUT


def test_row_4_done_result_with_unproven_is_needs_input():
    record = make_record(A, result=result_of(ResultStatus.DONE, unproven=("flaky",)))
    assert state_of(record) is State.NEEDS_INPUT


def test_row_4_malformed_result_is_needs_input_and_keeps_the_job_open():
    record = make_record(A, result=result_of(ResultStatus.NEEDS_INPUT, problem="no status"))
    assert state_of(record) is State.NEEDS_INPUT
    assert State.NEEDS_INPUT.is_open


def test_row_5_live_session_is_running():
    record = make_record(A, events=(launched(A),))
    assert state_of(record, {A: BUSY}) is State.RUNNING


def test_row_5_latest_launch_names_the_session_checked():
    record = make_record(A, events=(launched(A, 1), launched(A, 2)))
    assert state_of(record, {A: BUSY, A + "-r2": STOPPED}) is State.LOST
    assert state_of(record, {A: STOPPED, A + "-r2": BUSY}) is State.RUNNING


def test_row_6_stopped_session_is_launched_inside_the_grace_period():
    # Listed without a pid while starting: row 9 of ~/.claude/retros/2026-10-16-cure-dispatcher-first-run.md.
    record = make_record(A, events=(launched(A, age=timedelta(seconds=1)),))
    assert state_of(record, {A: STOPPED}) is State.LAUNCHED


def test_row_6_stopped_session_is_lost_inside_the_grace_period_after_cure_job_stop():
    record = make_record(A, events=(launched(A, age=timedelta(seconds=1)), StopIssued(1, NOW)))
    assert state_of(record, {A: STOPPED}) is State.LOST


def test_row_6_stop_of_an_earlier_run_does_not_end_the_grace_of_the_latest():
    record = make_record(A, events=(launched(A, 1), StopIssued(1, NOW), launched(A, 2, age=timedelta(seconds=1))))
    assert state_of(record, {A + "-r2": STOPPED}) is State.LAUNCHED


def test_row_7_unlisted_session_inside_the_grace_period_is_launched():
    record = make_record(A, events=(launched(A, age=timedelta(seconds=10)),))
    assert state_of(record, {}) is State.LAUNCHED


def test_row_7_grace_period_is_sixty_seconds_and_inclusive():
    assert LAUNCH_GRACE == timedelta(seconds=60)
    record = make_record(A, events=(launched(A, age=LAUNCH_GRACE),))
    assert state_of(record, {}) is State.LAUNCHED


def test_row_8_unlisted_session_past_the_grace_period_is_lost():
    record = make_record(A, events=(launched(A, age=LAUNCH_GRACE + timedelta(seconds=1)),))
    assert state_of(record, {}) is State.LOST


def test_row_9_goal_file_is_awaiting_approval():
    assert state_of(make_record(A, goal=True)) is State.AWAITING_APPROVAL


def test_row_10_job_holding_every_resource_is_queued():
    assert state_of(make_record(A)) is State.QUEUED


def test_row_11_job_not_holding_a_resource_is_held():
    assert states([make_record(A), make_record(B)])[B] is State.HELD


# --- precedence ----------------------------------------------------------------------------------------

def test_closed_beats_a_failed_result():
    record = make_record(A, events=(Closed(""),), result=result_of(ResultStatus.FAILED))
    assert state_of(record) is State.ABANDONED


def test_closed_beats_a_live_session():
    record = make_record(A, events=(launched(A), Closed("")))
    assert state_of(record, {A: BUSY}) is State.ABANDONED


def test_result_beats_a_live_session():
    record = make_record(A, events=(launched(A),), result=result_of(ResultStatus.DONE))
    assert state_of(record, {A: BUSY}) is State.DONE


def test_needs_input_result_beats_a_live_session():
    record = make_record(A, events=(launched(A),), result=result_of(ResultStatus.NEEDS_INPUT))
    assert state_of(record, {A: BUSY}) is State.NEEDS_INPUT


def test_launched_beats_goal_file():
    record = make_record(A, goal=True, events=(launched(A),))
    assert state_of(record, {A: BUSY}) is State.RUNNING


def test_goal_file_beats_queued_and_held():
    views = derive([make_record(A), make_record(B, goal=True)], {}, NOW)
    assert views[1].state is State.AWAITING_APPROVAL


def test_failed_result_is_failed_whatever_unproven_holds():
    assert state_of(make_record(A, result=result_of(ResultStatus.FAILED, unproven=("x",)))) is State.FAILED


# --- open states --------------------------------------------------------------------------------------

@pytest.mark.parametrize("state, is_open", [
    (State.QUEUED, True), (State.HELD, True), (State.AWAITING_APPROVAL, True), (State.LAUNCHED, True),
    (State.RUNNING, True), (State.STALLED, True), (State.LOST, True), (State.NEEDS_INPUT, True),
    (State.DONE, False), (State.FAILED, False), (State.ABANDONED, False),
])
def test_is_open(state, is_open):
    assert state.is_open is is_open


def test_state_values_are_the_documented_words():
    assert {s.value for s in State} == {
        "queued", "held", "awaiting-approval", "launched", "running", "stalled", "blocked", "lost", "needs-input", "done",
        "failed", "abandoned"}


# --- lock rule ----------------------------------------------------------------------------------------

def test_lowest_open_id_holds_and_the_others_are_held():
    result = states([make_record(C), make_record(A), make_record(B)])
    assert result == {A: State.QUEUED, B: State.HELD, C: State.HELD}


def test_views_are_ascending_by_id_whatever_the_input_order():
    views = derive([make_record(C), make_record(A), make_record(B)], {}, NOW)
    assert [view.record.id for view in views] == [A, B, C]


def test_blocked_by_lists_ascending_ids_of_holders():
    one = make_record(A, repos=("/work/x",))
    two = make_record(B, repos=("/work/y",))
    three = make_record(C, repos=("/work/x", "/work/y"))
    view = derive([one, two, three], {}, NOW)[2]
    assert view.state is State.HELD
    assert view.blocked_by == (A, B)


def test_job_holds_nothing_blocked_by_is_empty_for_the_holder():
    views = derive([make_record(A), make_record(B)], {}, NOW)
    assert views[0].blocked_by == ()
    assert views[1].blocked_by == (A,)


def test_disjoint_resources_do_not_block():
    result = states([make_record(A, repos=("/work/x",)), make_record(B, repos=("/work/y",))])
    assert result == {A: State.QUEUED, B: State.QUEUED}


def test_job_holding_one_resource_but_not_the_other_is_held():
    result = states([make_record(A, repos=("/work/x",)), make_record(B, repos=("/work/y", "/work/x"))])
    assert result[B] is State.HELD


@pytest.mark.parametrize("closer", [
    dict(events=(Closed(""),)),
    dict(result=result_of(ResultStatus.DONE)),
    dict(result=result_of(ResultStatus.FAILED)),
])
def test_lock_is_released_when_the_holder_closes_or_finishes(closer):
    result = states([make_record(A, **closer), make_record(B)])
    assert result[B] is State.QUEUED


def test_blocked_by_is_empty_for_jobs_that_are_not_open():
    views = derive([make_record(A), make_record(B, events=(Closed(""),))], {}, NOW)
    assert views[1].state is State.ABANDONED
    assert views[1].blocked_by == ()


@pytest.mark.parametrize("sessions, age", [
    ({A: STOPPED}, timedelta(minutes=5)),
    ({}, timedelta(minutes=5)),
])
def test_lost_job_is_open_and_keeps_its_resources(sessions, age):
    lost = make_record(A, events=(launched(A, age=age),))
    result = states([lost, make_record(B)], sessions)
    assert result == {A: State.LOST, B: State.HELD}


def test_needs_input_job_keeps_its_resources():
    result = states([make_record(A, result=result_of(ResultStatus.NEEDS_INPUT)), make_record(B)])
    assert result[B] is State.HELD


def test_claim_event_adds_a_resource_to_the_job():
    claimed = make_record(A, events=(Claim(DEVICE_BENCH),))
    other = make_record(B, device=Device.BENCH)
    assert claimed.resources == frozenset({"/work/video-core", DEVICE_BENCH})
    assert states([claimed, other])[B] is State.HELD


def test_device_bench_in_the_handoff_does_not_hold_the_bench():
    result = states([make_record(A, repos=("/work/x",), device=Device.BENCH),
                     make_record(B, repos=("/work/y",), device=Device.BENCH)])
    assert result == {A: State.QUEUED, B: State.QUEUED}


def test_ids_compare_as_plain_strings():
    low = "261013-0959-video-core-z"
    result = states([make_record(A), make_record(low)])
    assert result == {low: State.QUEUED, A: State.HELD}


def test_awaiting_approval_job_still_reports_the_holder_it_waits_for():
    views = derive([make_record(A), make_record(B, goal=True)], {}, NOW)
    assert views[1].state is State.AWAITING_APPROVAL
    assert views[1].blocked_by == (A,)


# --- ended_at and expired --------------------------------------------------------------------------------

def test_ended_at_of_done_and_failed_is_the_result_mtime():
    stamp = NOW - timedelta(days=3)
    for status in (ResultStatus.DONE, ResultStatus.FAILED):
        view = derive([make_record(A, result=result_of(status), result_mtime=stamp)], {}, NOW)[0]
        assert view.ended_at == stamp


def test_ended_at_of_abandoned_is_the_events_mtime():
    stamp = NOW - timedelta(days=3)
    view = derive([make_record(A, events=(Closed(""),), events_mtime=stamp)], {}, NOW)[0]
    assert view.ended_at == stamp


def test_ended_at_is_none_for_open_jobs():
    view = derive([make_record(A, events_mtime=NOW)], {}, NOW)[0]
    assert view.ended_at is None


def test_retention_periods():
    assert RETENTION == {State.DONE: timedelta(days=14), State.FAILED: timedelta(days=30),
                         State.ABANDONED: timedelta(days=30)}


def _expiry_view(status_kwargs, age):
    stamp = NOW - age
    return derive([make_record(A, result_mtime=stamp, events_mtime=stamp, **status_kwargs)], {}, NOW)[0]


@pytest.mark.parametrize("kwargs, days", [
    (dict(result=result_of(ResultStatus.DONE)), 14),
    (dict(result=result_of(ResultStatus.FAILED)), 30),
    (dict(events=(Closed(""),)), 30),
])
def test_expired_only_strictly_after_the_retention_period(kwargs, days):
    assert not expired(_expiry_view(kwargs, timedelta(days=days)), NOW)
    assert expired(_expiry_view(kwargs, timedelta(days=days, seconds=1)), NOW)
    assert not expired(_expiry_view(kwargs, timedelta(days=days - 1)), NOW)


def test_open_job_never_expires():
    view = derive([make_record(A, goal=True, events_mtime=NOW - timedelta(days=400))], {}, NOW)[0]
    assert not expired(view, NOW)


def test_needs_input_job_never_expires():
    record = make_record(A, result=result_of(ResultStatus.NEEDS_INPUT), result_mtime=NOW - timedelta(days=400))
    assert not expired(derive([record], {}, NOW)[0], NOW)


# --- needs_sessions --------------------------------------------------------------------------------------

def test_needs_sessions_true_for_launched_job_without_result_or_close():
    assert needs_sessions([make_record(A, events=(launched(A),))])


@pytest.mark.parametrize("record", [
    make_record(A),
    make_record(A, goal=True),
    make_record(A, events=(launched(A),), result=result_of(ResultStatus.DONE)),
    make_record(A, events=(launched(A),), result=result_of(ResultStatus.NEEDS_INPUT)),
    make_record(A, events=(launched(A), Closed(""))),
])
def test_needs_sessions_false_when_no_state_depends_on_sessions(record):
    assert not needs_sessions([record])


def test_needs_sessions_false_for_no_records():
    assert not needs_sessions([])


# --- stalled: a live session that is idle with no result ----------------------------------------------

def test_idle_session_inside_the_grace_period_is_running():
    record = make_record(A, events=(launched(A, age=timedelta(seconds=10)),))
    assert state_of(record, {A: IDLE}) is State.RUNNING


def test_idle_session_at_exactly_the_grace_period_is_still_running():
    record = make_record(A, events=(launched(A, age=LAUNCH_GRACE),))
    assert state_of(record, {A: IDLE}) is State.RUNNING


def test_idle_session_past_the_grace_period_is_stalled():
    record = make_record(A, events=(launched(A, age=LAUNCH_GRACE + timedelta(seconds=1)),))
    assert state_of(record, {A: IDLE}) is State.STALLED


def test_busy_session_past_the_grace_period_stays_running():
    record = make_record(A, events=(launched(A, age=timedelta(hours=3)),))
    assert state_of(record, {A: BUSY}) is State.RUNNING


def test_idle_session_with_a_result_is_needs_input_not_stalled():
    record = make_record(A, events=(launched(A, age=timedelta(hours=1)),),
                         result=result_of(ResultStatus.NEEDS_INPUT))
    assert state_of(record, {A: IDLE}) is State.NEEDS_INPUT


def test_stalled_state_checks_the_session_of_the_latest_launch():
    record = make_record(A, events=(launched(A, 1, age=timedelta(hours=2)), launched(A, 2, age=timedelta(hours=1))))
    assert state_of(record, {A: IDLE, A + "-r2": BUSY}) is State.RUNNING
    assert state_of(record, {A: BUSY, A + "-r2": IDLE}) is State.STALLED


def test_stalled_has_a_session_and_is_open_but_not_launchable():
    assert State.STALLED.value == "stalled"
    assert State.STALLED.has_session
    assert State.STALLED.is_open
    assert not State.STALLED.is_launchable


def test_stalled_job_keeps_its_resources():
    stalled = make_record(A, events=(launched(A, age=timedelta(hours=1)),))
    assert states([stalled, make_record(B)], {A: IDLE}) == {A: State.STALLED, B: State.HELD}
