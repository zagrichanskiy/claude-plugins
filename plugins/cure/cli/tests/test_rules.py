"""The rules table: refusal precedence per row, the per-kind start guards, a settled goal and one live session."""
from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from cure_job.claude import Session, SessionStatus
from cure_job.errors import CureJobError, JobStateError, ResourceHeld, SessionGone, StoreError
from cure_job.events import Claim, Closed, Origin, SessionStarted
from cure_job.job_id import session_name
from cure_job.kinds import KINDS, WORK, End
from cure_job.result import ResultStatus
from cure_job.rules import RULES, Artifact, Check, Op, Reads, check, goal_settled, state_in_start_states
from cure_job.state import LAUNCH_GRACE, State, derive
from cure_job.store import InvalidJob
from tests.builders import NOW, REPO, make_record, result_of

A = "261013-1000-video-core-a"
B = "261013-1001-video-core-b"
BAD = "261013-0900-video-core-bad"
INVALID = (InvalidJob(BAD, Path("/state/jobs") / BAD, "dispatch.jsonl line 1 does not read"),)
OLD = timedelta(minutes=5)

GOAL_KIND = replace(WORK, name="goal-writer", start_states=frozenset({State.QUEUED}), start_guards=(),
                    writes=frozenset({Artifact.GOAL}), end=End.EVENT)
PROBE_KIND = replace(WORK, name="probe", start_states=frozenset({State.APPROVED}), start_guards=(),
                     writes=frozenset(), end=End.EVENT)
ALL_KINDS = {**KINDS, GOAL_KIND.name: GOAL_KIND, PROBE_KIND.name: PROBE_KIND}


def work(run: int = 1, job_id: str = A) -> SessionStarted:
    return SessionStarted("work", run, session_name(job_id, run), NOW - OLD, run)


def other(kind: str, job_id: str = A) -> SessionStarted:
    return SessionStarted(kind, 1, f"{job_id}-{kind}", NOW - OLD, 0)


def facts(record, *, others=(), listing=None, invalid=(), operation="launch", kind=WORK, kinds=ALL_KINDS,
          names=()) -> Check:
    listing = listing or {}
    views = derive([record, *others], listing, NOW, frozenset(), LAUNCH_GRACE)
    view = next(view for view in views if view.record.id == record.id)
    return Check(record, operation, view=view, views=views, invalid=invalid, sessions=lambda: listing, kind=kind,
                 kinds=kinds, names=names)


def record_facts(record, operation, invalid=(), names=(), kind=None) -> Check:
    return Check(record, operation, invalid=invalid, names=names, kind=kind)


def refusal(op: Op, given: Check) -> CureJobError:
    with pytest.raises(CureJobError) as raised:
        check(op, given)
    return raised.value


def after_a(record):
    return replace(record, handoff=replace(record.handoff, after=A))


LAUNCHED_A = make_record(A, approved=True, events=(work(),))
LOST = make_record(B, approved=True, events=(work(job_id=B),))
NEEDS_INPUT = make_record(B, approved=True, events=(work(job_id=B),), result=result_of(ResultStatus.NEEDS_INPUT))
LIVE_B = {session_name(B, 1): Session(SessionStatus.BUSY, uuid="u")}


# --- precedence: each case trips two guards of one row, and the earlier one wins -----------------------------------

@pytest.mark.parametrize("op, given, error, text", [
    (Op.START, facts(make_record(B, goal=True), invalid=INVALID),
     JobStateError, f"job {B} is awaiting-approval; approve its goal first"),
    (Op.START, facts(after_a(make_record(B, approved=True)), others=(make_record(A),), invalid=INVALID),
     JobStateError, f"after {A} is queued"),
    (Op.START, facts(make_record(B, approved=True), others=(LAUNCHED_A,), invalid=INVALID),
     ResourceHeld, f"{REPO} is held by {A}"),
    (Op.START, facts(make_record(B), invalid=INVALID),
     JobStateError, f"job {B} is queued; launch needs approved, lost, needs-input"),
    (Op.START, facts(replace(NEEDS_INPUT, goal_digest=None), listing=LIVE_B, invalid=INVALID),
     JobStateError, f"job {B} is needs-input and its session {session_name(B, 1)} is live"),
    (Op.START, facts(replace(LOST, goal_digest=None), others=(LAUNCHED_A,), invalid=INVALID),
     JobStateError, f"job {B} has no goal file"),
    (Op.START, facts(LOST, others=(LAUNCHED_A,), invalid=INVALID),
     ResourceHeld, f"{REPO} is held by {A}"),
    (Op.START, facts(LOST, invalid=INVALID),
     StoreError, f"launch refused: job {BAD} is invalid"),
    (Op.CONTINUE, facts(LOST, operation="resume", invalid=INVALID),
     JobStateError, f"job {B} is lost; resume needs needs-input"),
    (Op.CONTINUE, facts(replace(NEEDS_INPUT, goal_digest=None), operation="resume", invalid=INVALID),
     SessionGone, f"job {B}: session {session_name(B, 1)} no longer exists"),
    (Op.CONTINUE, facts(replace(NEEDS_INPUT, goal_digest=None), operation="resume", listing=LIVE_B, invalid=INVALID),
     JobStateError, f"job {B} has no goal file"),
    (Op.CONTINUE, facts(NEEDS_INPUT, operation="resume", listing=LIVE_B, others=(LAUNCHED_A,), invalid=INVALID),
     ResourceHeld, f"{REPO} is held by {A}"),
    (Op.ORIGIN, facts(replace(LOST, events=LOST.events + (Origin("o", NOW),)), operation="origin"),
     JobStateError, f"job {B} already has origin o"),
    (Op.CLAIM, record_facts(make_record(B, events=(Closed(""),)), "claim", INVALID),
     JobStateError, f"job {B} is abandoned; claim needs a launched run"),
    (Op.CLAIM, record_facts(make_record(B, result=result_of(ResultStatus.DONE)), "claim", INVALID),
     JobStateError, f"job {B} has no launched run"),
    (Op.CLAIM, record_facts(replace(LOST, result=result_of(ResultStatus.DONE)), "claim", INVALID),
     JobStateError, f"job {B} has a result for run 1"),
    (Op.CLAIM, record_facts(replace(LOST, events=LOST.events + (Claim("device:bench", 1),)), "claim", INVALID,
                            ("build:x",)),
     CureJobError, f"job {B} holds device:bench; release device:bench first"),
    (Op.APPROVE, record_facts(replace(LOST, events=LOST.events + (Closed(""),)), "approve"),
     JobStateError, f"job {B} is abandoned; approve needs an open job"),
    (Op.APPROVE, record_facts(replace(LOST, result=result_of(ResultStatus.DONE)), "approve"),
     JobStateError, f"job {B} has a launched run"),
    (Op.APPROVE, record_facts(make_record(B, result=result_of(ResultStatus.DONE)), "approve"),
     JobStateError, f"job {B} has a result"),
    (Op.END, record_facts(make_record(B, events=(Closed(""),), result=result_of(ResultStatus.DONE)), "finish",
                          kind=WORK),
     JobStateError, f"job {B} is abandoned; finish needs an open launched job"),
    (Op.END, record_facts(make_record(B, result=result_of(ResultStatus.DONE)), "finish", kind=WORK),
     JobStateError, f"job {B} already has /state/jobs/{B}/result.md"),
    (Op.REPORTED, record_facts(make_record(B), "reported"),
     JobStateError, f"job {B} has no launched run; nothing to report"),
])
def test_the_earlier_guard_of_a_row_wins(op, given, error, text):
    raised = refusal(op, given)
    assert type(raised) is error
    assert str(raised).startswith(text)


def test_a_resource_held_refusal_keeps_its_resource_and_holder():
    raised = refusal(Op.START, facts(LOST, others=(LAUNCHED_A,)))
    assert (raised.resource, raised.holder) == (REPO, A)


# --- the rows -------------------------------------------------------------------------------------------------------

def test_every_operation_has_a_row():
    assert set(RULES) == set(Op)


@pytest.mark.parametrize("op", [op for op in Op if RULES[op].reads is Reads.LISTING])
def test_a_listing_row_refuses_to_run_without_a_view(op):
    with pytest.raises(AssertionError):
        check(op, record_facts(LOST, op.value))


def test_the_kept_session_is_read_only_for_a_needs_input_job():
    def unread():
        raise AssertionError("the session list was read")

    check(Op.START, replace(facts(make_record(B, approved=True)), sessions=unread))


def test_a_kind_prints_its_own_start_states_in_state_order():
    kind = replace(PROBE_KIND, start_states=frozenset({State.LOST, State.APPROVED}),
                   start_guards=(state_in_start_states,))
    raised = refusal(Op.START, facts(make_record(B), kind=kind, operation="start"))
    assert str(raised) == f"job {B} is queued; start needs approved, lost"


def test_work_is_the_only_kind_and_declares_no_artifact():
    assert WORK.writes == frozenset()
    assert KINDS == {"work": WORK}


@pytest.mark.parametrize("op, given, fact", [
    (Op.START, replace(facts(LOST), kinds={}), "kinds"),
    (Op.START, replace(facts(LOST), kind=None), "kind"),
    (Op.START, replace(facts(LOST), sessions=None), "sessions"),
    (Op.CONTINUE, replace(facts(NEEDS_INPUT, operation="resume", listing=LIVE_B), kinds={}), "kinds"),
    (Op.END, record_facts(LOST, "finish"), "kind"),
])
def test_a_row_refuses_to_run_without_a_fact_it_needs(op, given, fact):
    with pytest.raises(AssertionError, match=f"needs {fact} "):
        check(op, given)


# --- a settled goal -------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("record, settled", [
    (make_record(B, approved=True), True),
    (make_record(B), False),
    (make_record(B, goal=True, events=(other(GOAL_KIND.name, B),)), False),
    (make_record(B, goal=True, events=(other(PROBE_KIND.name, B),)), True),
])
def test_a_goal_is_settled_when_no_open_session_writes_it(record, settled):
    assert goal_settled(record, ALL_KINDS) is settled


def test_start_refuses_while_a_session_that_writes_the_goal_is_open():
    record = make_record(B, approved=True, events=(other(GOAL_KIND.name, B),))
    raised = refusal(Op.START, facts(record))
    assert type(raised) is JobStateError
    assert str(raised) == (f"job {B}: its {GOAL_KIND.name} session {B}-{GOAL_KIND.name} writes the goal; "
                           "launch needs a settled goal")


def test_a_kind_that_writes_the_goal_starts_on_a_queued_job_without_one():
    check(Op.START, facts(make_record(B), kind=GOAL_KIND, operation="start"))


def test_a_kind_that_writes_the_goal_restarts_past_its_own_open_session():
    record = make_record(B, goal=True, events=(other(GOAL_KIND.name, B),))
    check(Op.START, facts(record, kind=GOAL_KIND, operation="start"))


def test_resume_refuses_while_a_session_that_writes_the_goal_is_open():
    record = replace(NEEDS_INPUT, events=NEEDS_INPUT.events + (other(GOAL_KIND.name, B),))
    raised = refusal(Op.CONTINUE, facts(record, operation="resume", listing=LIVE_B))
    assert str(raised) == (f"job {B}: its {GOAL_KIND.name} session {B}-{GOAL_KIND.name} writes the goal; "
                           "resume needs a settled goal")


def test_resume_of_a_needs_input_job_whose_kept_session_is_listed_live_goes_ahead():
    check(Op.CONTINUE, facts(NEEDS_INPUT, operation="resume", listing=LIVE_B))


# --- one live session per job ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("status, refused", [(SessionStatus.BUSY, True), (SessionStatus.IDLE, True), (None, False)])
def test_start_refuses_while_another_session_of_the_job_is_live(status, refused):
    record = make_record(B, approved=True, events=(other(PROBE_KIND.name, B),))
    listing = {f"{B}-probe": Session(status)} if status is not None else {}
    given = facts(record, listing=listing)
    if not refused:
        check(Op.START, given)
        return
    raised = refusal(Op.START, given)
    assert str(raised) == f"job {B} has live probe session {B}-probe; stop it first: cure-job stop {B}"


def test_close_refuses_while_a_session_of_any_kind_is_live():
    record = make_record(B, approved=True, events=(other(PROBE_KIND.name, B),))
    raised = refusal(Op.CLOSE, facts(record, listing={f"{B}-probe": Session(SessionStatus.BUSY)}, operation="close"))
    assert str(raised) == f"job {B} is approved; stop session {B}-probe first: cure-job stop {B}"


def test_close_passes_a_needs_input_job_whose_ended_session_is_listed_live():
    check(Op.CLOSE, facts(NEEDS_INPUT, listing=LIVE_B, operation="close"))
