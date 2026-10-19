"""``JobsProvider``: the seven operations, their refusals and the writes they make, with fake seams."""
from __future__ import annotations

from datetime import timedelta

import pytest

from cure_job.errors import (ClaudeError, HandoffError, JobStateError, ResourceHeld, StoreError, UnknownJob)
from cure_job.claude import SessionStatus
from cure_job.events import Claim, Closed, Launched
from cure_job.frontmatter import parse
from cure_job.providers.jobs import JobsProvider
from cure_job.resource import DEVICE_BENCH
from cure_job.state import LAUNCH_GRACE, State
from cure_job.store import JobStore
from tests.builders import NOW, handoff_text, set_age
from tests.fakes import FakeClaude, FakeClock

REPO = "/work/video-core"


@pytest.fixture
def store(tmp_path):
    return JobStore(tmp_path / "state")


@pytest.fixture
def claude():
    return FakeClaude()


@pytest.fixture
def clock():
    return FakeClock(NOW)


class Harness(JobsProvider):
    """A provider that also exposes its store, so tests can write goal.md and result.md beside it."""

    def __init__(self, store, claude, clock):
        super().__init__(store, claude, clock)
        self.store = store


@pytest.fixture
def jobs(store, claude, clock):
    return Harness(store, claude, clock)


def state_map(jobs):
    return {view.record.id: view.state for view in jobs.views()}


def new_job(jobs, clock, slug="x", repos=(REPO,), device="none", approved=False):
    """Create a job; advance the clock one minute first so that ids sort in creation order."""
    clock.advance(timedelta(minutes=1))
    job_id = jobs.new(handoff_text(repos, device), slug)
    if approved:
        jobs.store.goal_path(job_id).write_text("goal", encoding="utf-8")
    return job_id


# --- new --------------------------------------------------------------------------------------------

def test_new_returns_the_id_built_from_clock_repo_and_slug(jobs):
    assert jobs.new(handoff_text(), "FPS clamp") == "261013-1800-video-core-fps-clamp"


def test_new_stamps_id_and_created_into_the_stored_handoff(jobs, store):
    job_id = jobs.new(handoff_text(), "x")
    fields = parse((store.job_dir(job_id) / "handoff.md").read_text(encoding="utf-8"))
    assert fields["id"] == job_id
    assert fields["created"] == "2026-10-13T18:00:00+00:00"


def test_new_uses_the_basename_of_the_first_repo(jobs):
    assert jobs.new(handoff_text(("/work/Other_Repo", REPO)), "x") == "261013-1800-other-repo-x"


def test_new_twice_in_the_same_minute_suffixes_the_second(jobs):
    first = jobs.new(handoff_text(), "x")
    second = jobs.new(handoff_text(), "x")
    assert second == first + "-2"


def test_new_does_not_start_a_session_or_ask_for_sessions(jobs, claude):
    jobs.new(handoff_text(), "x")
    assert claude.started == [] and claude.sessions_calls == 0


def test_new_rejects_an_invalid_handoff_and_writes_nothing(jobs, store):
    with pytest.raises(HandoffError):
        jobs.new("no frontmatter", "x")
    assert store.load_all() == []


def test_new_rejects_a_slug_that_slugifies_to_nothing(jobs):
    with pytest.raises(HandoffError):
        jobs.new(handoff_text(), "!!!")


def test_new_does_not_require_the_repo_to_exist(jobs):
    jobs.new(handoff_text(("/definitely/not/there",)), "x")


# --- views ------------------------------------------------------------------------------------------

def test_views_are_empty_without_jobs(jobs):
    assert jobs.views() == []


def test_views_first_job_queued_second_held(jobs, clock):
    first = new_job(jobs, clock)
    second = new_job(jobs, clock)
    assert state_map(jobs) == {first: State.QUEUED, second: State.HELD}


def test_views_ask_for_sessions_only_when_a_state_depends_on_them(jobs, claude, clock):
    new_job(jobs, clock, approved=True)
    jobs.views()
    assert claude.sessions_calls == 0


def test_views_ask_for_sessions_once_per_call(jobs, claude, clock):
    first = new_job(jobs, clock, approved=True)
    jobs.launch(first)
    claude.sessions_calls = 0
    jobs.views()
    assert claude.sessions_calls == 1


def test_views_report_running_then_lost_as_the_session_changes(jobs, claude, clock):
    job_id = new_job(jobs, clock, approved=True)
    jobs.launch(job_id)
    assert state_map(jobs)[job_id] is State.RUNNING
    claude.statuses[job_id] = SessionStatus.STOPPED
    # Stopped is launched in the grace: row 9 of ~/.claude/retros/2026-10-16-cure-dispatcher-first-run.md.
    clock.advance(LAUNCH_GRACE + timedelta(seconds=1))
    assert state_map(jobs)[job_id] is State.LOST
    del claude.statuses[job_id]
    clock.advance(timedelta(seconds=61))
    assert state_map(jobs)[job_id] is State.LOST


def test_launched_becomes_lost_after_the_grace_period(jobs, claude, clock):
    job_id = new_job(jobs, clock, approved=True)
    jobs.launch(job_id)
    del claude.statuses[job_id]
    assert state_map(jobs)[job_id] is State.LAUNCHED
    clock.advance(timedelta(seconds=61))
    assert state_map(jobs)[job_id] is State.LOST


def test_views_propagate_a_claude_failure(jobs, claude, clock):
    job_id = new_job(jobs, clock, approved=True)
    jobs.launch(job_id)
    claude.fail_sessions = ClaudeError("cannot list")
    with pytest.raises(ClaudeError):
        jobs.views()


def test_listing_names_a_malformed_dispatch_file(jobs, store, clock):
    job_id = new_job(jobs, clock)
    (store.job_dir(job_id) / "dispatch.jsonl").write_text("garbage\n", encoding="utf-8")
    assert jobs.views() == []
    assert "dispatch.jsonl" in jobs.listing().invalid[0].problem


# --- launch -----------------------------------------------------------------------------------------

def test_launch_starts_the_session_in_the_first_repo_with_the_goal_prompt(jobs, claude, store, clock):
    job_id = new_job(jobs, clock, approved=True)
    session = jobs.launch(job_id)
    assert session == job_id
    assert claude.started == [(job_id, REPO, f"/goal @{store.goal_path(job_id)}", ())]


def test_launch_passes_claude_arguments_through(jobs, claude, clock):
    job_id = new_job(jobs, clock, approved=True)
    jobs.launch(job_id, ["--add-dir", "/work/other"])
    assert claude.started[0][3] == ("--add-dir", "/work/other")


def test_launch_records_a_launched_event(jobs, store, clock):
    job_id = new_job(jobs, clock, approved=True)
    jobs.launch(job_id)
    assert store.load(job_id).events == (Launched(1, job_id, clock.now),)


def test_launch_leaves_the_job_launched_then_running(jobs, claude, clock):
    job_id = new_job(jobs, clock, approved=True)
    jobs.launch(job_id)
    assert state_map(jobs)[job_id] is State.RUNNING
    del claude.statuses[job_id]
    assert state_map(jobs)[job_id] is State.LAUNCHED


def test_launch_unknown_job(jobs):
    with pytest.raises(UnknownJob):
        jobs.launch("261013-1800-video-core-nothing")


@pytest.mark.parametrize("prepare", ["queued", "held", "running", "done", "failed", "abandoned"])
def test_launch_refuses_states_other_than_launchable(jobs, claude, store, clock, prepare):
    first = new_job(jobs, clock, approved=True)
    target = first
    if prepare == "held":
        target = new_job(jobs, clock, approved=False)
    elif prepare == "queued":
        store.goal_path(first).unlink()
    elif prepare == "running":
        jobs.launch(first)
        claude.started.clear()
    elif prepare == "done":
        (store.job_dir(first) / "result.md").write_text("---\nstatus: done\n---\n", encoding="utf-8")
    elif prepare == "failed":
        (store.job_dir(first) / "result.md").write_text("---\nstatus: failed\n---\n", encoding="utf-8")
    elif prepare == "abandoned":
        jobs.close(first)
    with pytest.raises(JobStateError):
        jobs.launch(target)
    assert claude.started == []


def test_launch_refuses_a_job_whose_resource_is_held_naming_holder_and_resource(jobs, claude, clock):
    holder = new_job(jobs, clock)
    waiting = new_job(jobs, clock, approved=True)
    with pytest.raises(ResourceHeld) as caught:
        jobs.launch(waiting)
    assert caught.value.holder == holder and caught.value.resource == REPO
    assert str(caught.value) == f"{REPO} is held by {holder}"
    assert claude.started == []


def test_launch_of_a_lost_job_uses_the_next_run_and_session_name(jobs, claude, clock):
    job_id = new_job(jobs, clock, approved=True)
    jobs.launch(job_id)
    claude.statuses[job_id] = SessionStatus.STOPPED
    # Stopped is launched in the grace: row 9 of ~/.claude/retros/2026-10-16-cure-dispatcher-first-run.md.
    clock.advance(LAUNCH_GRACE + timedelta(seconds=1))
    assert jobs.launch(job_id) == job_id + "-r2"
    assert state_map(jobs)[job_id] is State.RUNNING
    assert jobs.store.load(job_id).run == 2


def test_launch_of_a_needs_input_job_archives_result_as_the_previous_run(jobs, claude, store, clock):
    job_id = new_job(jobs, clock, approved=True)
    del claude.statuses[jobs.launch(job_id)]  # launch refuses while the needs-input session is live
    result = store.job_dir(job_id) / "result.md"
    result.write_text("---\nstatus: needs-input\n---\nquestion", encoding="utf-8")
    assert state_map(jobs)[job_id] is State.NEEDS_INPUT
    jobs.launch(job_id)
    directory = store.job_dir(job_id)
    assert not result.exists()
    assert "question" in (directory / "result-1.md").read_text(encoding="utf-8")
    assert state_map(jobs)[job_id] is State.RUNNING


def test_launch_of_a_first_run_without_result_archives_nothing(jobs, store, clock):
    job_id = new_job(jobs, clock, approved=True)
    jobs.launch(job_id)
    assert [p.name for p in store.job_dir(job_id).glob("result*")] == []


def test_launch_rolls_back_the_archive_when_the_start_fails(jobs, claude, store, clock):
    job_id = new_job(jobs, clock, approved=True)
    del claude.statuses[jobs.launch(job_id)]  # launch refuses while the needs-input session is live
    result = store.job_dir(job_id) / "result.md"
    result.write_text("---\nstatus: needs-input\n---\n", encoding="utf-8")
    claude.fail_start = ClaudeError("cannot start")
    with pytest.raises(ClaudeError):
        jobs.launch(job_id)
    assert result.is_file()
    assert not (store.job_dir(job_id) / "result-1.md").exists()
    assert store.load(job_id).run == 1


def test_launch_retry_after_a_failed_start_reuses_the_run_number(jobs, claude, clock):
    job_id = new_job(jobs, clock, approved=True)
    claude.fail_start = ClaudeError("cannot start")
    with pytest.raises(ClaudeError):
        jobs.launch(job_id)
    assert jobs.store.load(job_id).events == ()
    claude.fail_start = None
    assert jobs.launch(job_id) == job_id
    assert jobs.store.load(job_id).run == 1


def test_launch_start_failure_records_no_event(jobs, claude, store, clock):
    job_id = new_job(jobs, clock, approved=True)
    claude.fail_start = ClaudeError("cannot start")
    with pytest.raises(ClaudeError):
        jobs.launch(job_id)
    assert not (store.job_dir(job_id) / "dispatch.jsonl").exists()


def test_launch_event_write_failure_names_the_unrecorded_session(jobs, claude, store, clock, monkeypatch):
    job_id = new_job(jobs, clock, approved=True)

    def fail(*args, **kwargs):
        raise StoreError("disk full")

    monkeypatch.setattr(store, "append_event", fail)
    with pytest.raises(StoreError) as caught:
        jobs.launch(job_id)
    assert job_id in str(caught.value)
    assert "not recorded" in str(caught.value)
    assert claude.started


def test_launch_runs_sessions_at_most_once(jobs, claude, clock):
    job_id = new_job(jobs, clock, approved=True)
    jobs.launch(job_id)
    claude.statuses[job_id] = SessionStatus.STOPPED
    # Stopped is launched in the grace: row 9 of ~/.claude/retros/2026-10-16-cure-dispatcher-first-run.md.
    clock.advance(LAUNCH_GRACE + timedelta(seconds=1))
    claude.sessions_calls = 0
    jobs.launch(job_id)
    assert claude.sessions_calls == 1


# --- claim ------------------------------------------------------------------------------------------

def launched_job(jobs, clock, **kwargs):
    return jobs.launch(new_job(jobs, clock, approved=True, **kwargs))


def test_claim_a_new_resource_appends_a_claim_event(jobs, store, clock):
    job_id = launched_job(jobs, clock)
    jobs.claim(job_id, [DEVICE_BENCH])
    assert store.load(job_id).events[-1] == Claim(DEVICE_BENCH, 1)
    assert DEVICE_BENCH in store.load(job_id).resources


def test_claim_of_a_resource_the_job_already_names_writes_nothing(jobs, store, clock):
    job_id = launched_job(jobs, clock)
    before = store.load(job_id).events
    jobs.claim(job_id, [REPO])
    assert store.load(job_id).events == before


def test_claim_twice_writes_one_event(jobs, store, clock):
    job_id = launched_job(jobs, clock)
    jobs.claim(job_id, [DEVICE_BENCH])
    jobs.claim(job_id, [DEVICE_BENCH])
    claims = [event for event in store.load(job_id).events if isinstance(event, Claim)]
    assert claims == [Claim(DEVICE_BENCH, 1)]


def test_claim_makes_a_higher_job_that_names_the_resource_held(jobs, clock):
    first = launched_job(jobs, clock, repos=("/work/a",))
    second = new_job(jobs, clock, repos=("/work/b", "/work/c"))
    jobs.claim(first, ["/work/c"])
    assert state_map(jobs) == {first: State.RUNNING, second: State.HELD}


def test_claim_unknown_job(jobs):
    with pytest.raises(UnknownJob):
        jobs.claim("261013-1800-video-core-nothing", [DEVICE_BENCH])


def test_claim_refuses_a_job_that_is_not_launched(jobs, clock):
    job_id = new_job(jobs, clock, approved=True)
    with pytest.raises(JobStateError, match="no launched run"):
        jobs.claim(job_id, [DEVICE_BENCH])


@pytest.mark.parametrize("finish", ["close", "done", "failed"])
def test_claim_refuses_a_job_that_is_not_open(jobs, store, clock, finish):
    job_id = launched_job(jobs, clock)
    if finish == "close":
        jobs.stop(job_id)
        jobs.close(job_id)
    else:
        (store.job_dir(job_id) / "result.md").write_text(f"---\nstatus: {finish}\n---\n", encoding="utf-8")
    with pytest.raises(JobStateError):
        jobs.claim(job_id, [DEVICE_BENCH])


def test_claim_refused_when_a_lower_open_job_names_the_resource(jobs, store, clock):
    low = launched_job(jobs, clock, repos=("/work/a", "/work/c"))
    high = launched_job(jobs, clock, repos=("/work/b",))
    before = store.load(high).events
    with pytest.raises(ResourceHeld) as caught:
        jobs.claim(high, ["/work/c"])
    assert (caught.value.resource, caught.value.holder) == ("/work/c", low)
    assert store.load(high).events == before


def test_claim_refused_when_a_higher_job_that_names_it_has_been_launched(jobs, clock):
    low = launched_job(jobs, clock, repos=("/work/a",))
    high = launched_job(jobs, clock, repos=("/work/b",))
    jobs.claim(high, [DEVICE_BENCH])
    with pytest.raises(ResourceHeld) as caught:
        jobs.claim(low, [DEVICE_BENCH])
    assert (caught.value.resource, caught.value.holder) == (DEVICE_BENCH, high)


def test_claim_allowed_when_the_lower_job_naming_it_is_closed(jobs, clock):
    low = new_job(jobs, clock, repos=("/work/a", "/work/c"))
    high = launched_job(jobs, clock, repos=("/work/b",))
    jobs.close(low)
    jobs.claim(high, ["/work/c"])
    assert "/work/c" in jobs.store.load(high).resources


def test_claim_allowed_over_a_higher_job_that_was_not_launched(jobs, clock):
    low = launched_job(jobs, clock, repos=("/work/a",))
    new_job(jobs, clock, repos=("/work/b", "/work/c"), approved=True)
    jobs.claim(low, ["/work/c"])
    assert "/work/c" in jobs.store.load(low).resources


# --- close ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("setup, expected", [
    ("queued", State.QUEUED), ("held", State.HELD), ("awaiting-approval", State.AWAITING_APPROVAL),
    ("lost", State.LOST), ("needs-input", State.NEEDS_INPUT),
])
def test_close_abandons_a_job_in_each_closable_state(jobs, claude, store, clock, setup, expected):
    first = new_job(jobs, clock, approved=setup != "queued")
    target = first
    if setup == "held":
        target = new_job(jobs, clock)
    elif setup in ("lost", "needs-input"):
        jobs.launch(first)
        if setup == "lost":
            claude.statuses[first] = SessionStatus.STOPPED
            # Stopped is launched in the grace: row 9 of ~/.claude/retros/2026-10-16-cure-dispatcher-first-run.md.
            clock.advance(LAUNCH_GRACE + timedelta(seconds=1))
        else:
            (store.job_dir(first) / "result.md").write_text("---\nstatus: needs-input\n---\n", encoding="utf-8")
            claude.statuses.pop(first)
    assert state_map(jobs)[target] is expected
    jobs.close(target, "no longer needed")
    assert state_map(jobs)[target] is State.ABANDONED
    assert store.load(target).closed == Closed("no longer needed")


def test_close_default_reason_is_empty(jobs, store, clock):
    job_id = new_job(jobs, clock)
    jobs.close(job_id)
    assert store.load(job_id).closed == Closed("")


@pytest.mark.parametrize("live", [True, False])
def test_close_refuses_launched_and_running_and_says_to_stop_the_session(jobs, claude, clock, live):
    job_id = new_job(jobs, clock, approved=True)
    jobs.launch(job_id)
    if not live:
        del claude.statuses[job_id]
    with pytest.raises(JobStateError, match=job_id):
        jobs.close(job_id)
    assert not any(isinstance(e, Closed) for e in jobs.store.load(job_id).events)


@pytest.mark.parametrize("final", ["done", "failed", "abandoned"])
def test_close_refuses_finished_jobs(jobs, store, clock, final):
    job_id = new_job(jobs, clock)
    if final == "abandoned":
        jobs.close(job_id)
    else:
        (store.job_dir(job_id) / "result.md").write_text(f"---\nstatus: {final}\n---\n", encoding="utf-8")
    with pytest.raises(JobStateError):
        jobs.close(job_id)


def test_close_unknown_job(jobs):
    with pytest.raises(UnknownJob):
        jobs.close("261013-1800-video-core-nothing")


def test_close_releases_the_lock_for_the_next_job(jobs, clock):
    first = new_job(jobs, clock)
    second = new_job(jobs, clock)
    jobs.close(first)
    assert state_map(jobs) == {first: State.ABANDONED, second: State.QUEUED}


# --- prune ------------------------------------------------------------------------------------------

def finish(store, job_id, status, age, now=NOW):
    path = store.job_dir(job_id) / "result.md"
    path.write_text(f"---\nstatus: {status}\n---\n", encoding="utf-8")
    set_age(path, now, age)


def test_prune_removes_done_jobs_older_than_fourteen_days(jobs, store, clock):
    old = new_job(jobs, clock, repos=("/work/a",))
    new = new_job(jobs, clock, repos=("/work/b",))
    finish(store, old, "done", timedelta(days=14, hours=1), clock.now)
    finish(store, new, "done", timedelta(days=13), clock.now)
    assert jobs.prune() == [old]
    assert not store.job_dir(old).exists()
    assert store.job_dir(new).is_dir()


def test_prune_keeps_failed_jobs_for_thirty_days(jobs, store, clock):
    young = new_job(jobs, clock, repos=("/work/a",))
    old = new_job(jobs, clock, repos=("/work/b",))
    finish(store, young, "failed", timedelta(days=29), clock.now)
    finish(store, old, "failed", timedelta(days=31), clock.now)
    assert jobs.prune() == [old]


def test_prune_measures_an_abandoned_job_from_dispatch_jsonl(jobs, store, clock):
    young = new_job(jobs, clock, repos=("/work/a",))
    old = new_job(jobs, clock, repos=("/work/b",))
    for job_id, age in ((young, timedelta(days=29)), (old, timedelta(days=31))):
        jobs.close(job_id)
        set_age(store.job_dir(job_id) / "dispatch.jsonl", clock.now, age)
    assert jobs.prune() == [old]


def test_prune_never_removes_an_open_job_however_old(jobs, store, clock):
    queued = new_job(jobs, clock, repos=("/work/a",))
    waiting = new_job(jobs, clock, repos=("/work/b",), approved=True)
    needs = new_job(jobs, clock, repos=("/work/c",))
    finish(store, needs, "needs-input", timedelta(days=400), clock.now)
    for job_id in (queued, waiting, needs):
        for path in store.job_dir(job_id).iterdir():
            set_age(path, clock.now, timedelta(days=400))
    assert jobs.prune() == []
    assert {r.id for r in store.load_all()} == {queued, waiting, needs}


def test_prune_returns_ascending_ids_and_removes_the_whole_directory(jobs, store, clock):
    ids = [new_job(jobs, clock, repos=(f"/work/{n}",)) for n in "abc"]
    for job_id in reversed(ids):
        finish(store, job_id, "failed", timedelta(days=40), clock.now)
    (store.job_dir(ids[0]) / "result-1.md").write_text("archived", encoding="utf-8")
    assert jobs.prune() == ids
    assert store.load_all() == []
    assert not any(store.job_dir(i).exists() for i in ids)


def test_prune_compares_file_mtime_with_the_clock(jobs, store, clock):
    job_id = new_job(jobs, clock)
    finish(store, job_id, "done", timedelta(days=1), clock.now)
    clock.advance(timedelta(days=20))
    assert jobs.prune() == [job_id]


def test_prune_with_no_jobs_is_empty(jobs):
    assert jobs.prune() == []


# --- stalled: close and launch refuse while the idle session is alive -------------------------------------

def stall(jobs, claude, clock):
    """A launched job whose session is idle with no result, past the launch grace."""
    job_id = new_job(jobs, clock, approved=True)
    jobs.launch(job_id)
    claude.statuses[job_id] = SessionStatus.IDLE
    clock.advance(LAUNCH_GRACE + timedelta(seconds=1))
    return job_id


def test_idle_session_is_running_within_the_grace_and_stalled_after_it(jobs, claude, clock):
    job_id = new_job(jobs, clock, approved=True)
    jobs.launch(job_id)
    claude.statuses[job_id] = SessionStatus.IDLE
    clock.advance(LAUNCH_GRACE)
    assert state_map(jobs)[job_id] is State.RUNNING
    clock.advance(timedelta(seconds=1))
    assert state_map(jobs)[job_id] is State.STALLED


def test_close_refuses_a_stalled_job_and_names_the_session(jobs, claude, clock):
    job_id = stall(jobs, claude, clock)
    with pytest.raises(JobStateError, match=job_id):
        jobs.close(job_id)
    assert not any(isinstance(e, Closed) for e in jobs.store.load(job_id).events)


def test_launch_refuses_a_stalled_job_and_starts_nothing(jobs, claude, clock):
    job_id = stall(jobs, claude, clock)
    started = len(claude.started)
    with pytest.raises(JobStateError, match="stalled"):
        jobs.launch(job_id)
    assert len(claude.started) == started
    assert jobs.store.load(job_id).run == 1


def test_stalled_job_can_be_closed_once_its_session_is_stopped(jobs, claude, clock):
    job_id = stall(jobs, claude, clock)
    claude.statuses[job_id] = SessionStatus.STOPPED
    jobs.close(job_id, "abandoned by the user")
    assert state_map(jobs)[job_id] is State.ABANDONED


def test_stalled_job_can_be_launched_again_once_its_session_is_stopped(jobs, claude, clock):
    job_id = stall(jobs, claude, clock)
    claude.statuses[job_id] = SessionStatus.STOPPED
    assert jobs.launch(job_id) == job_id + "-r2"
