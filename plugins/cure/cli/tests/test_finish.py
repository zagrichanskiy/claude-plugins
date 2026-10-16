"""``finish``, local-time stamps and half-created directory prune (design: dispatcher-cli-finish item 2)."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from cure_job.claude import SessionStatus
from cure_job.cli import Cli
from cure_job.clock import format_local, local_now, parse_local
from cure_job.errors import JobStateError, ResourceHeld
from cure_job.providers.jobs import JobsProvider
from cure_job.result import Report, ResultStatus, parse_result
from cure_job.store import JobStore
from tests.builders import handoff_text, set_age
from tests.fakes import FakeClaude, FakeClock

LOCAL = datetime(2026, 10, 14, 17, 42, 5, tzinfo=timezone(timedelta(hours=3)))
REPO = "/work/video-core"


@pytest.fixture
def clock():
    return FakeClock(LOCAL)


@pytest.fixture
def store(tmp_path):
    return JobStore(tmp_path / "state")


@pytest.fixture
def claude():
    return FakeClaude()


@pytest.fixture
def jobs(store, clock, claude):
    return JobsProvider(store, claude, clock)


def make_job(jobs, store, clock, repo=REPO, launched=True):
    clock.advance(timedelta(minutes=1))
    job_id = jobs.new(handoff_text((repo,)), "x")
    if launched:
        store.goal_path(job_id).write_text("goal", encoding="utf-8")
        jobs.launch(job_id)
    return job_id


def state_of(jobs, job_id):
    return {view.record.id: view.state.value for view in jobs.views()}[job_id]


# --- finish refusals (provider) ---------------------------------------------------------------------

def test_finish_refuses_a_job_without_a_launched_event(jobs, store, clock):
    job_id = make_job(jobs, store, clock, launched=False)
    with pytest.raises(JobStateError, match="no launched event"):
        jobs.finish(job_id, Report(ResultStatus.DONE))
    assert not store.job_dir(job_id).joinpath("result.md").exists()


def test_finish_refuses_a_closed_job(jobs, store, clock, claude):
    job_id = make_job(jobs, store, clock)
    # cure-job stop ends the grace: row 9 of ~/.claude/retros/2026-10-16-cure-dispatcher-first-run.md.
    jobs.stop(job_id)
    jobs.close(job_id, "stop")
    with pytest.raises(JobStateError, match="abandoned"):
        jobs.finish(job_id, Report(ResultStatus.DONE))


def test_finish_refuses_when_result_md_exists_and_keeps_it(jobs, store, clock):
    job_id = make_job(jobs, store, clock)
    path = jobs.finish(job_id, Report(ResultStatus.FAILED))
    before = path.read_text(encoding="utf-8")
    with pytest.raises(JobStateError, match="already has"):
        jobs.finish(job_id, Report(ResultStatus.DONE))
    assert path.read_text(encoding="utf-8") == before


# --- finish success: the file parses back to the state list derives ---------------------------------

@pytest.mark.parametrize("report, state, unproven", [
    (Report(ResultStatus.DONE), "done", ()),
    (Report(ResultStatus.FAILED), "failed", ()),
    (Report(ResultStatus.NEEDS_INPUT, questions=("Which board profile: nand or emmc?",)), "needs-input", ()),
    (Report(ResultStatus.DONE, unproven=("2", "10")), "needs-input", ("2", "10")),
])
def test_finish_writes_a_result_that_parses_back_and_derives_the_state(jobs, store, clock, report, state,
                                                                       unproven):
    job_id = make_job(jobs, store, clock)
    path = jobs.finish(job_id, report)
    parsed = parse_result(path.read_text(encoding="utf-8"))
    assert (parsed.status, parsed.unproven, parsed.problem) == (report.status, unproven, None)
    assert state_of(jobs, job_id) == state


def test_finish_makes_no_sessions_call(store, clock):
    claude = FakeClaude()
    jobs = JobsProvider(store, claude, clock)
    job_id = make_job(jobs, store, clock)
    calls = claude.sessions_calls
    jobs.finish(job_id, Report(ResultStatus.DONE))
    assert claude.sessions_calls == calls


# --- Report refusals --------------------------------------------------------------------------------

def test_report_refuses_unproven_without_done():
    with pytest.raises(ValueError, match="unproven"):
        Report(ResultStatus.FAILED, unproven=("1",))


def test_report_refuses_needs_input_without_a_question():
    with pytest.raises(ValueError, match="question"):
        Report(ResultStatus.NEEDS_INPUT)


# --- finish through the command line ----------------------------------------------------------------

class Harness:
    def __init__(self, root):
        self.root = root
        self.clock = FakeClock(LOCAL)
        self.lines: list[str] = []
        self.claude = FakeClaude()
        self.cli = Cli(root=root, claude=self.claude, clock=self.clock, out=self.lines.append)

    def run(self, *argv):
        return self.cli.run(list(argv))

    def job(self, tmp_path, launched=True):
        self.clock.advance(timedelta(minutes=1))
        source = tmp_path / "handoff.md"
        source.write_text(handoff_text((REPO,)), encoding="utf-8")
        assert self.run("new", "--slug", "x", str(source)) == 0
        job_id = self.lines[-1]
        if launched:
            (self.root / "jobs" / job_id / "goal.md").write_text("goal", encoding="utf-8")
            assert self.run("launch", job_id) == 0
        self.lines.clear()
        return job_id


@pytest.fixture
def h(root):
    return Harness(root)


def test_cli_finish_prints_the_result_path_and_list_shows_the_state(h, tmp_path):
    job_id = h.job(tmp_path)
    assert h.run("finish", job_id, "--status", "done") == 0
    assert h.lines == [str(h.root / "jobs" / job_id / "result.md")]
    h.lines.clear()
    h.run("list", "--json")
    assert json.loads(h.lines[0])[0]["state"] == "done"


@pytest.mark.parametrize("extra", [["--unproven", "1", "--status", "failed"], ["--status", "needs-input"]])
def test_cli_finish_value_refusals_exit_two(h, tmp_path, extra):
    job_id = h.job(tmp_path)
    with pytest.raises(SystemExit) as caught:
        h.run("finish", job_id, *extra)
    assert caught.value.code == 2


def test_cli_finish_without_a_launched_event_exits_one(h, tmp_path):
    job_id = h.job(tmp_path, launched=False)
    assert h.run("finish", job_id, "--status", "done") == 1


def test_cli_finish_of_a_closed_job_exits_one(h, tmp_path):
    job_id = h.job(tmp_path)
    # cure-job stop ends the grace: row 9 of ~/.claude/retros/2026-10-16-cure-dispatcher-first-run.md.
    assert h.run("stop", job_id) == 0
    assert h.run("close", job_id) == 0
    assert h.run("finish", job_id, "--status", "done") == 1


def test_cli_finish_with_existing_result_exits_one(h, tmp_path):
    job_id = h.job(tmp_path)
    assert h.run("finish", job_id, "--status", "done") == 0
    assert h.run("finish", job_id, "--status", "failed") == 1


# --- local time -------------------------------------------------------------------------------------

def test_new_job_id_uses_the_local_wall_clock_fields(jobs, clock):
    assert jobs.new(handoff_text((REPO,)), "x").startswith("261014-1742-")


def test_format_local_keeps_the_offset_of_its_argument():
    assert format_local(LOCAL) == "2026-10-14T17:42:05+03:00"


def test_parse_local_round_trips_an_offset_timestamp():
    assert parse_local(format_local(LOCAL)) == LOCAL


@pytest.mark.parametrize("text", ["2026-10-14T17:42:05", "2026-10-14 17:42:05"])
def test_parse_local_rejects_a_timestamp_without_offset(text):
    with pytest.raises(ValueError):
        parse_local(text)


def test_format_local_rejects_a_naive_datetime():
    with pytest.raises(ValueError):
        format_local(datetime(2026, 10, 14, 17, 42, 5))


def test_local_now_is_aware_with_whole_seconds():
    now = local_now()
    assert now.utcoffset() is not None and now.microsecond == 0


def test_events_are_stamped_with_an_offset(jobs, store, clock):
    job_id = make_job(jobs, store, clock)
    text = store.job_dir(job_id).joinpath("dispatch.jsonl").read_text(encoding="utf-8")
    assert "+03:00" in text


# --- prune of half-created directories --------------------------------------------------------------

def half_created(store, name):
    path = store.root / "jobs" / name
    path.mkdir(parents=True)
    return path


def test_prune_removes_a_stale_new_directory_and_an_empty_id_directory(jobs, store, clock):
    stale = half_created(store, ".new-abc")
    (stale / "handoff.md").write_text("x", encoding="utf-8")
    empty = half_created(store, "261001-0900-video-core-x")
    for path in (stale, empty):
        set_age(path, clock.now, timedelta(days=1, minutes=1))
    assert jobs.prune_half_created() == [stale, empty]
    assert not stale.exists() and not empty.exists()


def test_prune_keeps_half_created_directories_younger_than_a_day(jobs, store, clock):
    young = half_created(store, ".new-abc")
    empty = half_created(store, "261001-0900-video-core-x")
    for path in (young, empty):
        set_age(path, clock.now, timedelta(days=1) - timedelta(minutes=1))
    assert jobs.prune_half_created() == []
    assert young.exists() and empty.exists()


def test_prune_keeps_a_non_empty_id_directory_without_handoff(jobs, store, clock):
    path = half_created(store, "261001-0900-video-core-x")
    (path / "other").write_text("x", encoding="utf-8")
    set_age(path, clock.now, timedelta(days=5))
    assert jobs.prune_half_created() == []


def test_cli_prune_prints_a_half_created_path_before_job_ids(h, tmp_path):
    stale = h.root / "jobs" / ".new-abc"
    stale.mkdir(parents=True)
    set_age(stale, LOCAL, timedelta(days=2))
    assert h.run("prune") == 0
    assert h.lines == [str(stale)]


# --- F1: owner answer pending; remove this test alone to drop the os.link publish --------------------

def test_f1_write_result_never_replaces_an_existing_result_md(store, jobs, clock):
    job_id = make_job(jobs, store, clock)
    target = store.job_dir(job_id) / "result.md"
    target.write_text("---\nstatus: done\n---\n", encoding="utf-8")
    assert store.write_result(job_id, "---\nstatus: failed\n---\n") is False
    assert target.read_text(encoding="utf-8") == "---\nstatus: done\n---\n"
    assert [p.name for p in store.job_dir(job_id).glob(".result-*")] == []


# --- F10: owner answer pending; remove this test alone to drop the launch guard ----------------------

def test_f10_launch_refuses_a_lower_id_job_when_a_launched_job_holds_the_repository(jobs, store, clock):
    clock.now = datetime(2026, 10, 25, 1, 30, tzinfo=timezone(timedelta(hours=3)))
    first = jobs.new(handoff_text((REPO,)), "x")
    store.goal_path(first).write_text("goal", encoding="utf-8")
    jobs.launch(first)
    clock.now = datetime(2026, 10, 25, 1, 10, tzinfo=timezone(timedelta(hours=2)))
    second = jobs.new(handoff_text((REPO,)), "y")
    assert second < first
    store.goal_path(second).write_text("goal", encoding="utf-8")
    with pytest.raises(ResourceHeld) as caught:
        jobs.launch(second)
    assert caught.value.holder == first
