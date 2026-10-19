"""Issue 34: approval of a goal, the state ``approved``, the lock holders of unlaunched jobs, the ``next`` actions.

Each test names the "Done when" item of the issue it pins."""
from __future__ import annotations

import json
from datetime import timedelta

import pytest

from cure_job.actions import Action, actions
from cure_job.claude import SessionStatus
from cure_job.errors import ResourceHeld
from cure_job.goal import digest
from cure_job.store import JobStore
from cure_job.state import LAUNCH_GRACE, State, derive
from tests.builders import NOW, make_record
from tests.test_cli import Harness
from tests.test_jobs import Harness as ProviderHarness, new_job
from tests.test_state import A, B, C, launched, states
from tests.fakes import FakeClaude, FakeClock

NEEDS_INPUT_RESULT = "---\nstatus: needs-input\nquestion: which branch?\n---\n"
DONE_RESULT = "---\nstatus: done\n---\n"


@pytest.fixture
def h(root):
    return Harness(root)


def rows(h):
    h.lines.clear()
    assert h.run("list", "--json") == 0
    return {row["id"]: row for row in json.loads(h.lines[0])}


def goal_file(h, job_id):
    return h.root / "jobs" / job_id / "goal.md"


def event_lines(h, job_id):
    path = h.root / "jobs" / job_id / "dispatch.jsonl"
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def view_of(records, job_id):
    return {view.record.id: view for view in derive(records, {}, NOW, frozenset())}[job_id]


# --- Done when 1 ---------------------------------------------------------------------------------------

def test_done_when_1_blocked_job_with_a_goal_lists_held_with_goal_true(h, tmp_path):
    first = h.new(tmp_path)
    h.approve(first)
    second = h.new(tmp_path)
    goal_file(h, second).write_text("goal", encoding="utf-8")
    row = rows(h)[second]
    assert (row["state"], row["goal"], row["approved"]) == ("held", True, False)
    assert row["blocked-by"] == [first]


def test_done_when_1_blocked_job_without_a_goal_lists_held_with_goal_false(h, tmp_path):
    h.approve(h.new(tmp_path))
    second = h.new(tmp_path)
    row = rows(h)[second]
    assert (row["state"], row["goal"], row["approved"]) == ("held", False, False)


# --- Done when 2 ---------------------------------------------------------------------------------------

def test_done_when_2_approve_then_launch_succeeds(h, tmp_path):
    job_id = h.new(tmp_path)
    h.approve(job_id)
    assert h.run("launch", job_id) == 0
    assert rows(h)[job_id]["state"] == "running"


def test_done_when_2_launch_without_approve_exits_one_naming_approve(h, tmp_path, capsys):
    job_id = h.new(tmp_path)
    goal_file(h, job_id).write_text("goal", encoding="utf-8")
    assert h.run("launch", job_id) == 1
    assert f"cure-job approve {job_id}" in capsys.readouterr().err
    assert h.claude.started == []


def test_done_when_2_launch_of_a_queued_job_exits_one(h, tmp_path):
    job_id = h.new(tmp_path)
    assert h.run("launch", job_id) == 1
    assert h.claude.started == []


# --- Done when 3 ---------------------------------------------------------------------------------------

def test_done_when_3_editing_the_goal_after_approve_returns_to_awaiting_approval(h, tmp_path):
    job_id = h.new(tmp_path)
    h.approve(job_id)
    assert rows(h)[job_id]["state"] == "approved"
    goal_file(h, job_id).write_text("goal, edited", encoding="utf-8")
    row = rows(h)[job_id]
    assert (row["state"], row["approved"]) == ("awaiting-approval", False)


def test_done_when_3_edited_goal_cannot_be_launched(h, tmp_path):
    job_id = h.new(tmp_path)
    h.approve(job_id)
    goal_file(h, job_id).write_text("goal, edited", encoding="utf-8")
    assert h.run("launch", job_id) == 1
    assert h.claude.started == []


def test_done_when_3_editing_the_goal_of_a_held_approved_job_revokes_the_approval(h, tmp_path):
    first = h.new(tmp_path)
    h.approve(first)
    second = h.new(tmp_path)
    h.approve(second)
    assert (rows(h)[second]["state"], rows(h)[second]["approved"]) == ("held", True)
    goal_file(h, second).write_text("goal, edited", encoding="utf-8")
    row = rows(h)[second]
    assert (row["state"], row["approved"]) == ("held", False)


def test_done_when_3_restoring_the_goal_bytes_restores_the_approval(h, tmp_path):
    job_id = h.new(tmp_path)
    h.approve(job_id)
    goal_file(h, job_id).write_text("goal, edited", encoding="utf-8")
    goal_file(h, job_id).write_text("goal", encoding="utf-8")
    assert rows(h)[job_id]["state"] == "approved"


# --- Done when 4 ---------------------------------------------------------------------------------------

def test_done_when_4_held_approved_job_lists_approved_after_the_blocker_is_done_with_no_new_event(h, tmp_path):
    first = h.new(tmp_path)
    h.approve(first)
    assert h.run("launch", first) == 0
    second = h.new(tmp_path)
    h.approve(second)
    assert rows(h)[second]["state"] == "held"
    before = event_lines(h, second)
    (h.root / "jobs" / first / "result.md").write_text(DONE_RESULT, encoding="utf-8")
    row = rows(h)[second]
    assert (row["state"], row["approved"], row["blocked-by"]) == ("approved", True, [])
    assert event_lines(h, second) == before


def test_done_when_4_held_approved_job_lists_approved_after_the_blocker_is_closed(h, tmp_path):
    first = h.new(tmp_path)
    h.approve(first)
    second = h.new(tmp_path)
    h.approve(second)
    assert h.run("close", first) == 0
    assert rows(h)[second]["state"] == "approved"


def test_done_when_4_held_unapproved_job_lists_awaiting_approval_after_the_blocker_is_done(h, tmp_path):
    first = h.new(tmp_path)
    h.approve(first)
    assert h.run("launch", first) == 0
    second = h.new(tmp_path)
    goal_file(h, second).write_text("goal", encoding="utf-8")
    (h.root / "jobs" / first / "result.md").write_text(DONE_RESULT, encoding="utf-8")
    assert rows(h)[second]["state"] == "awaiting-approval"


# --- Done when 5 ---------------------------------------------------------------------------------------

def _needs_input_job(h, tmp_path):
    job_id = h.new(tmp_path)
    h.approve(job_id)
    assert h.run("launch", job_id) == 0
    session = h.lines[-1]
    goal_file(h, job_id).write_text("goal, answered", encoding="utf-8")
    (h.root / "jobs" / job_id / "result.md").write_text(NEEDS_INPUT_RESULT, encoding="utf-8")
    return job_id, session


def test_done_when_5_launch_of_a_needs_input_job_needs_no_approval(h, tmp_path):
    job_id, session = _needs_input_job(h, tmp_path)
    del h.claude.statuses[session]
    assert rows(h)[job_id]["approved"] is False
    assert h.run("launch", job_id) == 0
    assert len(h.claude.started) == 2


def test_done_when_5_resume_of_a_needs_input_job_needs_no_approval(h, tmp_path):
    job_id, session = _needs_input_job(h, tmp_path)
    h.claude.statuses[session] = SessionStatus.IDLE
    assert rows(h)[job_id]["approved"] is False
    assert h.run("resume", job_id) == 0
    assert len(h.claude.resumed) == 1


def test_done_when_5_relaunch_of_a_lost_job_needs_no_approval(h, tmp_path):
    job_id = h.new(tmp_path)
    h.approve(job_id)
    assert h.run("launch", job_id) == 0
    goal_file(h, job_id).write_text("goal, edited", encoding="utf-8")
    h.claude.statuses[h.lines[-1]] = SessionStatus.STOPPED
    h.clock.advance(LAUNCH_GRACE + timedelta(seconds=1))
    assert rows(h)[job_id]["state"] == "lost"
    assert h.run("launch", job_id) == 0


# --- Done when 6 ---------------------------------------------------------------------------------------

def test_done_when_6_approved_higher_id_holds_and_unapproved_lower_id_is_held_behind_it():
    result = derive([make_record(A, goal=True), make_record(B, approved=True)], {}, NOW, frozenset())
    by_id = {view.record.id: view for view in result}
    assert by_id[B].state is State.APPROVED and by_id[B].blocked_by == ()
    assert by_id[A].state is State.HELD and by_id[A].blocked_by == (B,)


def test_done_when_6_unapproved_lower_id_without_a_goal_is_held_behind_the_approved_higher_id():
    by_id = {v.record.id: v for v in derive([make_record(A), make_record(B, approved=True)], {}, NOW, frozenset())}
    assert by_id[A].state is State.HELD and by_id[A].blocked_by == (B,)


def test_done_when_6_lower_id_regains_its_place_when_the_approval_of_the_higher_id_is_revoked():
    result = states([make_record(A, goal=True), make_record(B, goal=True)])
    assert result == {A: State.AWAITING_APPROVAL, B: State.AWAITING_APPROVAL}


# --- Done when 7 ---------------------------------------------------------------------------------------

X, Y = "/work/x", "/work/y"


def test_done_when_7_approved_job_on_two_repos_with_one_held_holds_nothing():
    holder = make_record(A, repos=(X,), events=(launched(A),))
    wide = make_record(B, repos=(X, Y), approved=True)
    view = view_of([holder, wide], B)
    assert view.state is State.HELD and view.blocked_by == (A,)


def test_done_when_7_a_later_approved_job_on_the_free_repo_is_approved():
    holder = make_record(A, repos=(X,), events=(launched(A),))
    wide = make_record(B, repos=(X, Y), approved=True)
    later = make_record(C, repos=(Y,), approved=True)
    result = derive([holder, wide, later], {A: SessionStatus.BUSY}, NOW, frozenset())
    by_id = {view.record.id: view for view in result}
    assert by_id[C].state is State.APPROVED and by_id[C].blocked_by == ()
    assert by_id[B].state is State.HELD and by_id[B].blocked_by == (A, C)


def test_done_when_7_approved_job_on_two_repos_with_one_held_by_a_lower_ready_job_holds_nothing():
    lower = make_record(A, repos=(X,), approved=True)
    wide = make_record(B, repos=(X, Y), approved=True)
    later = make_record(C, repos=(Y,), approved=True)
    result = states([lower, wide, later])
    assert result == {A: State.APPROVED, B: State.HELD, C: State.APPROVED}


# --- Done when 8 ---------------------------------------------------------------------------------------

SESSION_STATES = {State.LAUNCHED, State.RUNNING, State.STALLED, State.BLOCKED, State.LOST, State.NEEDS_INPUT,
                  State.APPROVED}


def test_done_when_8_no_blocked_by_names_a_job_in_queued_held_or_awaiting_approval():
    records = [
        make_record(A, repos=(X,), events=(launched(A),)),
        make_record(B, repos=(X, Y), goal=True),
        make_record(C, repos=(Y,), approved=True),
        make_record("261013-1003-video-core-d", repos=(X, Y), approved=True),
        make_record("261013-1004-video-core-e", repos=(Y,)),
        make_record("261013-1005-video-core-f", repos=(X,), goal=True),
        make_record("261013-1006-video-core-g", repos=(Y,), approved=True),
    ]
    views = derive(records, {A: SessionStatus.BUSY}, NOW, frozenset())
    state_of = {view.record.id: view.state for view in views}
    named = {holder for view in views for holder in view.blocked_by}
    assert named
    assert {state_of[holder] for holder in named} <= SESSION_STATES


def test_done_when_8_a_held_approved_job_is_not_named_as_a_blocker():
    wide = make_record(B, repos=(X, Y), approved=True)
    holder = make_record(A, repos=(X,), events=(launched(A),))
    later = make_record(C, repos=(X, Y), approved=True)
    views = {view.record.id: view for view in derive([holder, wide, later], {A: SessionStatus.BUSY}, NOW, frozenset())}
    assert views[B].state is State.HELD and views[C].state is State.HELD
    assert views[C].blocked_by == (A,)


# --- Done when 9 ---------------------------------------------------------------------------------------

def test_done_when_9_derive_does_not_raise_when_a_resource_is_unheld():
    views = derive([make_record(A, repos=(X, Y), goal=True)], {}, NOW, frozenset())
    assert views[0].state is State.AWAITING_APPROVAL and views[0].blocked_by == ()


def test_done_when_9_derive_does_not_raise_when_a_job_holds_only_some_of_its_resources():
    holder = make_record(A, repos=(X,), events=(launched(A),))
    partial = make_record(B, repos=(X, Y), goal=True)
    view = view_of([holder, partial], B)
    assert view.state is State.HELD and view.blocked_by == (A,)


def test_done_when_9_launch_of_a_blocked_ready_job_with_an_unheld_resource_raises_resource_held(tmp_path):
    claude, clock = FakeClaude(), FakeClock(NOW)
    jobs = ProviderHarness(JobStore(tmp_path / "state"), claude, clock)
    holder = new_job(jobs, clock, repos=(X,), approved=True)
    jobs.launch(holder)
    wide = new_job(jobs, clock, repos=(X, Y), approved=True)
    with pytest.raises(ResourceHeld) as caught:
        jobs.launch(wide)
    assert (caught.value.resource, caught.value.holder) == (X, holder)
    assert claude.started[1:] == []


def test_done_when_9_launch_after_the_holder_ends_succeeds_with_resources_unheld(tmp_path):
    claude, clock = FakeClaude(), FakeClock(NOW)
    jobs = ProviderHarness(JobStore(tmp_path / "state"), claude, clock)
    holder = new_job(jobs, clock, repos=(X,), approved=True)
    jobs.launch(holder)
    wide = new_job(jobs, clock, repos=(X, Y), approved=True)
    (jobs.store.job_dir(holder) / "result.md").write_text(DONE_RESULT, encoding="utf-8")
    assert jobs.launch(wide) == wide


# --- Done when 10 --------------------------------------------------------------------------------------

def _names(records, job_id, sessions=None):
    view = {v.record.id: v for v in derive(records, sessions or {}, NOW, frozenset())}[job_id]
    return [action.name for action in actions(view, {})]


def test_done_when_10_held_job_without_a_goal_gets_draft():
    assert _names([make_record(A, approved=True), make_record(B)], B) == ["draft"]


def test_done_when_10_held_job_with_an_unapproved_goal_gets_ask_approval():
    assert _names([make_record(A, approved=True), make_record(B, goal=True)], B) == ["ask-approval"]


def test_done_when_10_approved_job_gets_launch():
    assert _names([make_record(A, approved=True)], A) == ["launch"]


def test_done_when_10_held_approved_job_blocked_by_a_higher_id_gets_note_starved():
    records = [make_record(A, repos=(X, Y), approved=True), make_record(C, repos=(Y,), events=(launched(C),))]
    sessions = {C: SessionStatus.BUSY}
    assert _names(records, A, sessions) == ["note-starved"]


def test_done_when_10_held_approved_job_blocked_by_a_lower_id_gets_no_action():
    holder = make_record(A, events=(launched(A),))
    records = [holder, make_record(B, approved=True)]
    assert _names(records, B, {A: SessionStatus.BUSY}) == []


def test_done_when_10_next_json_reports_the_actions_through_the_command(h, tmp_path):
    first = h.new(tmp_path)
    h.approve(first)
    second = h.new(tmp_path)
    third = h.new(tmp_path, repos=("/work/other",))
    goal_file(h, third).write_text("goal", encoding="utf-8")
    h.lines.clear()
    assert h.run("next", "--json") == 0
    by_id = {entry["id"]: entry["actions"] for entry in json.loads(h.lines[0])}
    assert by_id[first] == ["launch"]
    assert by_id[second] == ["draft"]
    assert by_id[third] == ["ask-approval"]


# --- Done when 12 --------------------------------------------------------------------------------------

def test_done_when_12_approve_writes_one_approved_event_with_the_goal_digest(h, tmp_path):
    job_id = h.new(tmp_path)
    goal_file(h, job_id).write_text("goal", encoding="utf-8")
    assert h.run("approve", job_id) == 0
    events = [json.loads(line) for line in event_lines(h, job_id)]
    assert len(events) == 1
    assert events[0]["event"] == "approved"
    assert events[0]["goal"] == digest(b"goal")
    assert events[0]["by"] == "user"
    assert "at" in events[0]


def test_done_when_12_the_same_digest_again_writes_nothing(h, tmp_path):
    job_id = h.new(tmp_path)
    goal_file(h, job_id).write_text("goal", encoding="utf-8")
    assert h.run("approve", job_id) == 0
    before = event_lines(h, job_id)
    assert h.run("approve", job_id) == 0
    assert h.run("approve", job_id, "--by", "auto") == 0
    assert event_lines(h, job_id) == before


def test_done_when_12_a_changed_goal_gets_a_new_approved_event(h, tmp_path):
    job_id = h.new(tmp_path)
    goal_file(h, job_id).write_text("goal", encoding="utf-8")
    h.run("approve", job_id)
    goal_file(h, job_id).write_text("goal, edited", encoding="utf-8")
    assert h.run("approve", job_id) == 0
    digests = [json.loads(line)["goal"] for line in event_lines(h, job_id)]
    assert len(digests) == 2 and digests[0] != digests[1]
    assert rows(h)[job_id]["state"] == "approved"


def test_done_when_12_by_auto_is_recorded(h, tmp_path):
    job_id = h.new(tmp_path)
    goal_file(h, job_id).write_text("goal", encoding="utf-8")
    assert h.run("approve", job_id, "--by", "auto") == 0
    assert json.loads(event_lines(h, job_id)[0])["by"] == "auto"


def test_done_when_12_by_rejects_an_unknown_approver(h, tmp_path):
    job_id = h.new(tmp_path)
    goal_file(h, job_id).write_text("goal", encoding="utf-8")
    with pytest.raises(SystemExit) as caught:
        h.run("approve", job_id, "--by", "robot")
    assert caught.value.code != 0
    assert event_lines(h, job_id) == []


def test_done_when_12_approve_without_a_goal_exits_one_and_writes_nothing(h, tmp_path, capsys):
    job_id = h.new(tmp_path)
    assert h.run("approve", job_id) == 1
    assert "goal" in capsys.readouterr().err
    assert event_lines(h, job_id) == []


def test_done_when_12_approve_of_a_launched_closed_or_finished_job_exits_one(h, tmp_path):
    launched_id = h.new(tmp_path, repos=("/work/a",))
    h.approve(launched_id)
    h.run("launch", launched_id)
    closed_id = h.new(tmp_path, repos=("/work/b",))
    goal_file(h, closed_id).write_text("goal", encoding="utf-8")
    h.run("close", closed_id)
    for job_id in (launched_id, closed_id):
        before = event_lines(h, job_id)
        assert h.run("approve", job_id) == 1
        assert event_lines(h, job_id) == before


def test_done_when_12_list_json_shows_goal_and_approved_for_each_stage(h, tmp_path):
    queued = h.new(tmp_path, repos=("/work/a",))
    awaiting = h.new(tmp_path, repos=("/work/b",))
    goal_file(h, awaiting).write_text("goal", encoding="utf-8")
    approved = h.new(tmp_path, repos=("/work/c",))
    h.approve(approved)
    data = rows(h)
    assert [(data[j]["goal"], data[j]["approved"]) for j in (queued, awaiting, approved)] == [
        (False, False), (True, False), (True, True)]
