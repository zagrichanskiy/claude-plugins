"""Phase, session liveness and the projection to ``state``, and the ``phase`` and ``sessions`` of ``list --json``."""
from __future__ import annotations

import itertools
import json
from dataclasses import replace
from datetime import timedelta

import pytest

from cure_job.claude import Session, SessionStatus
from cure_job.events import Closed, SessionStarted, SessionStopped
from cure_job.handoff import Device, Handoff
from cure_job.job_id import session_name
from cure_job.result import ResultStatus
from cure_job.sessions import JobSession, Liveness, liveness
from cure_job.state import (LAUNCH_GRACE, Phase, State, derive, is_open, is_ready, needs_sessions, phase_of,
                            project)
from tests.builders import NOW, make_record, result_of
from tests.test_cli import Harness

A = "261013-1000-video-core-a"
B = "261013-1001-video-core-b"
INSIDE = timedelta(seconds=1)
PAST = LAUNCH_GRACE + timedelta(seconds=1)


def work(run: int = 1, age: timedelta = timedelta(minutes=5), job_id: str = A) -> SessionStarted:
    return SessionStarted("work", run, session_name(job_id, run), NOW - age, run)


def job_session(age: timedelta = timedelta(minutes=5), ended: bool = False, stop_recorded: bool = False) -> JobSession:
    return JobSession(kind="work", n=1, name=A, run=1, started_at=NOW - age, inputs=(), ended=ended, summary=(),
                      stop_recorded=stop_recorded)


def view_of(record, sessions=None):
    return derive([record], sessions or {}, NOW, frozenset())[0]


# --- liveness ---------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("status, age, stop_recorded, expected", [
    (SessionStatus.BUSY, INSIDE, False, Liveness.BUSY),
    (SessionStatus.BUSY, PAST, False, Liveness.BUSY),
    (SessionStatus.WAITING, INSIDE, False, Liveness.WAITING),
    (SessionStatus.WAITING, PAST, False, Liveness.WAITING),
    (SessionStatus.IDLE, INSIDE, False, Liveness.IDLE),
    (SessionStatus.IDLE, LAUNCH_GRACE, False, Liveness.IDLE),
    (SessionStatus.IDLE, PAST, False, Liveness.STALLED),
    (None, INSIDE, False, Liveness.STARTING),
    (None, LAUNCH_GRACE, False, Liveness.STARTING),
    (None, PAST, False, Liveness.GONE),
    (None, INSIDE, True, Liveness.STARTING),
    (SessionStatus.STOPPED, INSIDE, False, Liveness.STARTING),
    (SessionStatus.STOPPED, INSIDE, True, Liveness.GONE),
    (SessionStatus.STOPPED, PAST, False, Liveness.GONE),
])
def test_liveness_follows_the_listing_the_grace_and_the_recorded_stop(status, age, stop_recorded, expected):
    listed = Session(status) if status is not None else None
    assert liveness(job_session(age, stop_recorded=stop_recorded), listed, NOW, LAUNCH_GRACE) is expected


@pytest.mark.parametrize("status", [None, *SessionStatus])
def test_an_ended_session_is_ended_whatever_the_listing(status):
    listed = Session(status) if status is not None else None
    assert liveness(job_session(ended=True), listed, NOW, LAUNCH_GRACE) is Liveness.ENDED


def test_live_is_every_liveness_but_gone_and_ended():
    assert {item for item in Liveness if item.is_live} == set(Liveness) - {Liveness.GONE, Liveness.ENDED}


# --- phase ------------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("record, expected", [
    (make_record(A), Phase.QUEUED),
    (make_record(A, goal=True), Phase.AWAITING_APPROVAL),
    (make_record(A, approved=True), Phase.APPROVED),
    (make_record(A, approved=True, events=(work(),)), Phase.WORKING),
    (make_record(A, events=(work(),), result=result_of(ResultStatus.NEEDS_INPUT)), Phase.NEEDS_INPUT),
    (make_record(A, events=(work(),), result=result_of(ResultStatus.DONE, unproven=("x",))), Phase.NEEDS_INPUT),
    (make_record(A, events=(work(),), result=result_of(ResultStatus.DONE)), Phase.DONE),
    (make_record(A, events=(work(),), result=result_of(ResultStatus.FAILED)), Phase.FAILED),
    (make_record(A, events=(work(), Closed("x")), result=result_of(ResultStatus.DONE)), Phase.ABANDONED),
])
def test_phase_reads_the_files_and_events_only(record, expected):
    assert phase_of(record) is expected
    assert is_open(record) is not expected.is_terminal


def test_terminal_phases_are_done_failed_and_abandoned():
    assert {phase for phase in Phase if phase.is_terminal} == {Phase.DONE, Phase.FAILED, Phase.ABANDONED}


# --- projection -------------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("work_liveness, expected", [
    (Liveness.STARTING, State.LAUNCHED), (Liveness.BUSY, State.RUNNING), (Liveness.IDLE, State.RUNNING),
    (Liveness.WAITING, State.BLOCKED), (Liveness.STALLED, State.STALLED), (Liveness.GONE, State.LOST),
])
@pytest.mark.parametrize("held", [False, True])
def test_a_working_job_projects_its_work_liveness(work_liveness, expected, held):
    assert project(Phase.WORKING, held, work_liveness) is expected


@pytest.mark.parametrize("work_liveness", [None, Liveness.ENDED])
def test_a_working_job_without_a_live_or_gone_work_session_cannot_project(work_liveness):
    with pytest.raises(AssertionError):
        project(Phase.WORKING, False, work_liveness)


@pytest.mark.parametrize("phase", [Phase.QUEUED, Phase.AWAITING_APPROVAL, Phase.APPROVED])
def test_a_held_job_before_its_launch_projects_held(phase):
    assert project(phase, True, None) is State.HELD
    assert project(phase, False, None) is State(phase.value)


@pytest.mark.parametrize("phase", [Phase.NEEDS_INPUT, Phase.DONE, Phase.FAILED, Phase.ABANDONED])
@pytest.mark.parametrize("held", [False, True])
def test_a_job_past_its_work_projects_its_phase(phase, held):
    assert project(phase, held, Liveness.ENDED if phase is Phase.NEEDS_INPUT else None) is State(phase.value)


# --- views ------------------------------------------------------------------------------------------------------------

def test_a_job_without_sessions_has_an_empty_session_map():
    view = view_of(make_record(A, approved=True))
    assert view.phase is Phase.APPROVED and view.sessions == {}


def test_the_session_map_holds_the_latest_session_of_each_kind():
    goal_start = SessionStarted("goal", 1, A + "-goal-1", NOW, 1, ("answers-1.md",))
    record = make_record(A, events=(work(1), work(2), goal_start))
    view = view_of(record, {session_name(A, 2): Session(SessionStatus.BUSY)})
    assert {kind: item.session.n for kind, item in view.sessions.items()} == {"work": 2, "goal": 1}
    assert view.sessions["work"].liveness is Liveness.BUSY
    assert view.sessions["goal"].liveness is Liveness.STARTING
    assert view.state is State.RUNNING


def test_waiting_for_is_set_only_for_a_waiting_session():
    record = make_record(A, events=(work(),))
    waiting = view_of(record, {A: Session(SessionStatus.WAITING, "permission")})
    busy = view_of(record, {A: Session(SessionStatus.BUSY, "stale")})
    assert waiting.sessions["work"].waiting_for == "permission" and waiting.state is State.BLOCKED
    assert busy.sessions["work"].waiting_for is None


def test_the_work_session_of_a_needs_input_job_is_ended_even_while_listed_live():
    record = make_record(A, events=(work(),), result=result_of(ResultStatus.NEEDS_INPUT))
    view = view_of(record, {A: Session(SessionStatus.BUSY)})
    assert view.sessions["work"].liveness is Liveness.ENDED and view.state is State.NEEDS_INPUT


@pytest.mark.parametrize("record", [
    make_record(A, events=(work(),), result=result_of(ResultStatus.DONE)),
    make_record(A, events=(work(),), result=result_of(ResultStatus.FAILED)),
    make_record(A, events=(work(), Closed("x"))),
])
def test_a_terminal_job_reports_no_liveness(record):
    assert view_of(record, {A: Session(SessionStatus.BUSY)}).sessions["work"].liveness is None


def test_held_is_set_from_the_holders_and_the_after_wait():
    holder = make_record(A, approved=True)
    blocked = make_record(B, approved=True)
    views = {view.record.id: view for view in derive([holder, blocked], {}, NOW, frozenset())}
    assert not views[A].held and views[B].held and views[B].blocked_by == (A,)
    assert views[B].phase is Phase.APPROVED and views[B].state is State.HELD


def test_held_is_set_for_an_unmet_after_without_a_holder():
    base = make_record(B, repos=("/work/other",), approved=True)
    waiting = replace(base, handoff=Handoff(base.handoff.repos, Device.NONE, after=A))
    view = derive([make_record(A, goal=True), waiting], {}, NOW, frozenset())[1]
    assert view.held and view.blocked_by == () and view.state is State.HELD


def test_a_terminal_job_is_never_held():
    holder = make_record(A, approved=True)
    closed = make_record(B, approved=True, events=(Closed("x"),))
    view = derive([holder, closed], {}, NOW, frozenset())[1]
    assert not view.held and view.blocked_by == ()


# --- needs_sessions ---------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("record, expected", [
    (make_record(A, approved=True), False),
    (make_record(A, events=(work(),)), True),
    (make_record(A, events=(work(),), result=result_of(ResultStatus.NEEDS_INPUT)), False),
    (make_record(A, events=(work(),), result=result_of(ResultStatus.DONE)), False),
    (make_record(A, events=(work(), Closed("x"))), False),
])
def test_the_session_list_is_needed_exactly_for_an_open_job_with_an_open_session(record, expected):
    assert needs_sessions([record]) is expected


# --- the 0.62.0 rules -------------------------------------------------------------------------------------------------

def reference_state(record, status, blocked_by, waits):
    """The open-job rule of 0.62.0, before the split into phase and liveness."""
    if record.result is not None:
        return State.NEEDS_INPUT
    latest = record.latest("work")
    if latest is not None:
        within_grace = NOW - latest.started_at <= LAUNCH_GRACE
        if status is SessionStatus.BUSY:
            return State.RUNNING
        if status is SessionStatus.WAITING:
            return State.BLOCKED
        if status is SessionStatus.IDLE:
            return State.RUNNING if within_grace else State.STALLED
        starting = status is None or (status is SessionStatus.STOPPED and not latest.stop_recorded)
        return State.LAUNCHED if starting and within_grace else State.LOST
    if blocked_by or waits:
        return State.HELD
    if not record.has_goal:
        return State.QUEUED
    return State.APPROVED if is_ready(record) else State.AWAITING_APPROVAL


EVENT_SETS = [(), (work(age=INSIDE),), (work(age=PAST),), (work(age=INSIDE), SessionStopped("work", 1, NOW)),
              (work(1), work(2, age=INSIDE)), (work(1), SessionStopped("work", 1, NOW), work(2, age=PAST))]
RESULTS = [None, ResultStatus.NEEDS_INPUT]


@pytest.mark.parametrize("events, result, goal, approved, status, holder", itertools.product(
    EVENT_SETS, RESULTS, [False, True], [False, True], [None, *SessionStatus], [False, True]))
def test_state_matches_the_0_62_rules(events, result, goal, approved, status, holder):
    record = make_record(B, goal=goal, approved=approved, events=events,
                         result=result_of(result) if result is not None else None)
    records = [make_record(A, events=(work(job_id=A),))] if holder else []
    latest = record.latest("work")
    listing = {latest.name: Session(status)} if latest is not None and status is not None else {}
    view = derive([*records, record], listing, NOW, frozenset())[-1]
    assert view.state is reference_state(record, status, view.blocked_by, False)


# --- list --json ------------------------------------------------------------------------------------------------------

def test_list_json_adds_the_phase_and_the_latest_session_of_each_kind(root, tmp_path):
    h = Harness(root)
    job_id = h.new(tmp_path)
    h.approve(job_id)
    assert h.run("launch", job_id) == 0
    h.claude.statuses[job_id] = SessionStatus.WAITING
    h.claude.waiting_for[job_id] = "permission"
    h.lines.clear()
    assert h.run("list", "--json") == 0
    row = json.loads(h.lines[0])[0]
    assert row["state"] == "blocked" and row["phase"] == "working" and row["waiting-for"] == "permission"
    assert row["sessions"] == {"work": {"n": 1, "session": job_id, "liveness": "waiting", "waiting-for": "permission",
                                        "run": 1, "inputs": [], "restarts": 0, "summary": []}}


def test_list_json_reports_no_liveness_for_a_finished_job(root, tmp_path):
    h = Harness(root)
    job_id = h.new(tmp_path)
    h.approve(job_id)
    h.run("launch", job_id)
    (h.root / "jobs" / job_id / "result.md").write_text("---\nstatus: done\n---\n", encoding="utf-8")
    h.lines.clear()
    h.run("list", "--json")
    row = json.loads(h.lines[0])[0]
    assert row["state"] == "done" and row["phase"] == "done"
    assert row["sessions"]["work"]["liveness"] is None


def test_list_json_gives_an_invalid_job_no_phase_and_no_sessions(root, tmp_path):
    h = Harness(root)
    job_id = h.new(tmp_path)
    (h.root / "jobs" / job_id / "dispatch.jsonl").write_text("garbage\n", encoding="utf-8")
    h.lines.clear()
    h.run("list", "--json")
    row = json.loads(h.lines[0])[0]
    assert row["state"] == "invalid" and row["phase"] is None and row["sessions"] == {}
