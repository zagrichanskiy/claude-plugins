"""``actions``: the dispatcher's action table, one test per row, from hand-built records."""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import pytest

from cure_job.actions import STALLED_CONFIRM_SECONDS, Action, actions
from cure_job.claude import SessionStatus
from cure_job.events import Closed, Reported, SessionEnded, SessionsRemoved, SessionStarted
from cure_job.handoff import Device, Handoff
from cure_job.result import Result, ResultStatus
from cure_job.state import State, derive
from tests.builders import NOW, make_record, result_of, listed
from tests.test_state import A, B, launched

TIMEOUT = "short-hold timeout: device:bench held by " + B


def names(record, sessions=None, row=None):
    view = derive([record], listed(sessions or {}), NOW, frozenset())[0]
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
    view = derive([record], listed({A: SessionStatus.IDLE}), NOW, frozenset())[0]
    assert actions(view, {}) == [Action("confirm-stalled", {"stalled-confirm-seconds": STALLED_CONFIRM_SECONDS})]


def test_lost_job_gets_ask_relaunch():
    record = make_record(A, events=(launched(A, age=timedelta(minutes=5)),))
    assert names(record, {A: SessionStatus.STOPPED}) == ["ask-relaunch"]


def test_blocked_job_gets_tell_blocked_with_waiting_for():
    record = make_record(A, events=(launched(A),))
    view = derive([record], listed({A: SessionStatus.WAITING}), NOW, frozenset())[0]
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
    view = {v.record.id: v for v in derive(records, {}, NOW, frozenset())}[B]
    assert view.state is State.HELD
    assert actions(view, {}) == []


def test_awaiting_approval_job_gets_ask_approval():
    assert names(make_record(A, goal=True)) == ["ask-approval"]


def test_timeout_as_only_question_gets_ask_timeout_with_resource_and_holder():
    record = make_record(A, events=(launched(A), Reported(1, NOW)),
                         result=Result(ResultStatus.NEEDS_INPUT, (), None, (), (TIMEOUT,)))
    view = derive([record], {}, NOW, frozenset())[0]
    assert actions(view, {}) == [Action("ask-timeout", {"resource": "device:bench", "holder": B})]


def _timeout_actions(questions):
    record = make_record(A, events=(launched(A), Reported(1, NOW)),
                         result=Result(ResultStatus.NEEDS_INPUT, (), None, (), questions))
    return actions(derive([record], {}, NOW, frozenset())[0], {})


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


def successor(*, goal=False, approved=False, **kwargs):
    record = make_record(B, goal=goal, approved=approved, **kwargs)
    return replace(record, handoff=Handoff(record.handoff.repos, Device.NONE, after=A))


def successor_names(record, predecessors=(), invalid=frozenset()):
    view = {v.record.id: v for v in derive([*predecessors, record], {}, NOW, invalid)}[B]
    return [action.name for action in actions(view, {})]


def test_job_without_after_gets_draft():
    assert names(make_record(A)) == ["draft"]


def test_held_job_after_a_predecessor_without_a_goal_gets_no_draft():
    assert successor_names(successor(), [make_record(A)]) == []


def test_held_job_after_a_predecessor_with_a_goal_gets_draft():
    assert successor_names(successor(), [make_record(A, goal=True)]) == ["draft"]


def test_held_job_with_an_unapproved_goal_after_a_valid_predecessor_gets_ask_approval():
    assert successor_names(successor(goal=True), [make_record(A)]) == ["ask-approval"]


def test_held_job_with_an_unapproved_goal_after_an_invalid_predecessor_gets_no_ask_approval():
    assert successor_names(successor(goal=True), invalid=frozenset({A})) == []


def test_held_job_after_an_invalid_predecessor_gets_no_draft():
    assert successor_names(successor(), invalid=frozenset({A})) == []


def goal_session(*, age=timedelta(minutes=5), ended=False, run=1, inputs=()):
    started = SessionStarted("goal", 1, "g", NOW - age, run, inputs)
    return (started, SessionEnded("goal", 1, ("a", "b", "c"), NOW)) if ended else (started,)


@pytest.mark.parametrize("held", [False, True])
@pytest.mark.parametrize("ended, expected", [(False, []), (True, ["draft"])])
def test_draft_waits_while_a_goal_session_is_open(held, ended, expected):
    if held:
        record = successor(events=goal_session(ended=ended, run=0))
        view = {v.record.id: v for v in derive([make_record(A, goal=True), record], listed({"g": SessionStatus.BUSY}),
                                               NOW, frozenset())}[B]
        assert view.state is State.HELD
        assert [action.name for action in actions(view, {})] == expected
    else:
        assert names(make_record(A, events=goal_session(ended=ended, run=0)), {"g": SessionStatus.BUSY}) == expected


ANSWERS = ("answers-1.md",)


def answered(*, ended, open_items=0, inputs=ANSWERS, result=None):
    record = finished(ResultStatus.NEEDS_INPUT, Reported(1, NOW), *goal_session(ended=ended, inputs=inputs))
    record = replace(record, open_items=open_items)
    return record if result is None else replace(record, result=result)


def test_ask_input_waits_while_a_goal_session_is_open():
    assert names(answered(ended=False), {"g": SessionStatus.BUSY}) == []


@pytest.mark.parametrize("open_items, expected", [(2, ["ask-open"]), (0, ["resume"])])
def test_an_ended_answers_session_gets_ask_open_or_resume(open_items, expected):
    assert names(answered(ended=True, open_items=open_items)) == expected


def test_a_goal_session_without_inputs_on_a_needs_input_job_is_not_the_answers_session():
    assert names(answered(ended=True, inputs=())) == ["ask-input"]


@pytest.mark.parametrize("inputs", [(), ANSWERS])
@pytest.mark.parametrize("open_items", [0, 2])
def test_only_a_goal_session_given_answers_leads_to_ask_open_or_resume(inputs, open_items):
    found = names(answered(ended=True, inputs=inputs, open_items=open_items))
    assert bool({"ask-open", "resume"} & set(found)) == bool(inputs)


TIMEOUT_RESULT = Result(ResultStatus.NEEDS_INPUT, (), None, (), (TIMEOUT,))


def test_a_timeout_job_with_an_open_answers_session_gets_no_ask_timeout():
    assert names(answered(ended=False, result=TIMEOUT_RESULT), {"g": SessionStatus.BUSY}) == []


def test_a_timeout_job_with_an_ended_answers_session_gets_resume():
    assert names(answered(ended=True, result=TIMEOUT_RESULT)) == ["resume"]
