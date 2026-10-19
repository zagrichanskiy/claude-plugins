"""``actions``: the dispatcher's action table, one test per row, from hand-built records."""
from __future__ import annotations

from datetime import timedelta

import pytest

from cure_job.actions import STALLED_CONFIRM_SECONDS, Action, actions
from cure_job.claude import SessionStatus
from cure_job.events import Closed, Reported, SessionsRemoved
from cure_job.result import Result, ResultStatus
from cure_job.state import State, derive
from tests.builders import NOW, make_record, result_of
from tests.test_state import A, B, launched

TIMEOUT = "short-hold timeout: device:bench held by " + B


def names(record, sessions=None, row=None):
    view = derive([record], sessions or {}, NOW)[0]
    return [action.name for action in actions(view, row or {})]


def finished(status, *extra, **kwargs):
    return make_record(A, events=(launched(A), *extra), result=result_of(status), **kwargs)


def test_invalid_job_gets_repair_with_the_problem():
    assert actions(None, {"problem": "handoff.md: bad"}) == [Action("repair", {"problem": "handoff.md: bad"})]


def test_queued_job_gets_draft():
    assert names(make_record(A)) == ["draft"]


def test_done_unreported_job_gets_report_then_remove_sessions():
    assert names(finished(ResultStatus.DONE)) == ["report", "remove-sessions"]


def test_done_reported_job_gets_remove_sessions_only():
    assert names(finished(ResultStatus.DONE, Reported(1, NOW))) == ["remove-sessions"]


def test_failed_unreported_job_gets_report_only():
    assert names(finished(ResultStatus.FAILED)) == ["report"]


def test_abandoned_job_gets_remove_sessions():
    assert names(make_record(A, events=(Closed("superseded"),))) == ["remove-sessions"]


def test_needs_input_unreported_job_gets_report_then_ask_input():
    assert names(finished(ResultStatus.NEEDS_INPUT)) == ["report", "ask-input"]


def test_needs_input_reported_job_gets_ask_input_only():
    assert names(finished(ResultStatus.NEEDS_INPUT, Reported(1, NOW))) == ["ask-input"]


def test_stalled_job_gets_confirm_stalled_with_the_wait():
    record = make_record(A, events=(launched(A, age=timedelta(minutes=5)),))
    view = derive([record], {A: SessionStatus.IDLE}, NOW)[0]
    assert actions(view, {}) == [Action("confirm-stalled", {"stalled-confirm-seconds": STALLED_CONFIRM_SECONDS})]


def test_lost_job_gets_ask_relaunch():
    record = make_record(A, events=(launched(A, age=timedelta(minutes=5)),))
    assert names(record, {A: SessionStatus.STOPPED}) == ["ask-relaunch"]


def test_blocked_job_gets_tell_blocked_with_waiting_for():
    record = make_record(A, events=(launched(A),))
    view = derive([record], {A: SessionStatus.WAITING}, NOW)[0]
    assert view.state is State.BLOCKED
    assert actions(view, {"waiting-for": "a permission"}) == [Action("tell-blocked", {"waiting-for": "a permission"})]


@pytest.mark.parametrize("record, sessions", [
    (make_record(A, events=(launched(A, age=timedelta(seconds=1)),)), {}),
    (make_record(A, events=(launched(A),)), {A: SessionStatus.BUSY}),
    (finished(ResultStatus.DONE, Reported(1, NOW), SessionsRemoved(NOW)), {}),
    (finished(ResultStatus.FAILED, Reported(1, NOW)), {}),
    (make_record(A, events=(Closed("x"), SessionsRemoved(NOW))), {}),
])
def test_states_with_nothing_to_do_get_no_action(record, sessions):
    assert names(record, sessions) == []


def test_held_job_gets_no_action():
    records = [make_record(A, approved=True), make_record(B, approved=True)]
    view = {v.record.id: v for v in derive(records, {}, NOW)}[B]
    assert view.state is State.HELD
    assert actions(view, {}) == []


def test_awaiting_approval_job_gets_ask_approval():
    assert names(make_record(A, goal=True)) == ["ask-approval"]


def test_timeout_as_only_question_gets_ask_timeout_with_resource_and_holder():
    record = make_record(A, events=(launched(A), Reported(1, NOW)),
                         result=Result(ResultStatus.NEEDS_INPUT, (), None, (), (TIMEOUT,)))
    view = derive([record], {}, NOW)[0]
    assert actions(view, {}) == [Action("ask-timeout", {"resource": "device:bench", "holder": B})]


def _timeout_actions(questions):
    record = make_record(A, events=(launched(A), Reported(1, NOW)),
                         result=Result(ResultStatus.NEEDS_INPUT, (), None, (), questions))
    return actions(derive([record], {}, NOW)[0], {})


@pytest.mark.parametrize("question, resource, holder", [
    ("short-hold timeout:", "", None),
    ("short-hold timeout: device:bench", "device:bench", None),
    ("short-hold timeout: device:bench repo:x held by " + A + " " + B, "device:bench repo:x", A + " " + B),
])
def test_timeout_question_without_a_single_holder_still_gets_ask_timeout(question, resource, holder):
    assert _timeout_actions((question,)) == [Action("ask-timeout", {"resource": resource, "holder": holder})]


@pytest.mark.parametrize("questions", [
    (TIMEOUT, "another question"),
])
def test_shared_timeout_question_gets_ask_input(questions):
    record = make_record(A, events=(launched(A), Reported(1, NOW)),
                         result=Result(ResultStatus.NEEDS_INPUT, (), None, (), questions))
    assert names(record) == ["ask-input"]
