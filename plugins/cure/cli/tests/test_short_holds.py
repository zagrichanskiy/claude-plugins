"""Issues 32 and 43: ``release``, run-scoped short-hold claims, the ``claim`` precondition, ``claim --wait`` and the claim lock."""
from __future__ import annotations

import fcntl
import os
from datetime import timedelta

import pytest

from cure_job import resource
from cure_job.cli import Cli
from cure_job.errors import ClaudeError, JobStateError, ResourceHeld
from cure_job.events import Claim, Release, decode, encode
from cure_job.result import Report, ResultStatus
from tests.builders import NOW, handoff_text
from tests.fakes import FakeClaude, FakeClock

BENCH = resource.DEVICE_BENCH
REPO_A = "/work/a"
REPO_B = "/work/b"
NEEDS_INPUT = Report(ResultStatus.NEEDS_INPUT, questions=("which board?",))


class FakeTime:
    """A monotonic clock whose ``sleep`` advances it and runs an optional hook, with no real waiting."""

    def __init__(self):
        self.now = 0.0
        self.sleeps: list[float] = []
        self.on_sleep = None

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds
        if self.on_sleep is not None:
            self.on_sleep(len(self.sleeps))


class Harness:
    def __init__(self, root):
        self.root = root
        self.claude = FakeClaude()
        self.clock = FakeClock(NOW)
        self.time = FakeTime()
        self.lines: list[str] = []
        self.cli = Cli(root=root, claude=self.claude, clock=self.clock, out=self.lines.append,
                       sleep=self.time.sleep, monotonic=self.time.monotonic)
        self.jobs = self.cli.jobs

    def run(self, *argv) -> int:
        self.lines.clear()
        return self.cli.run(list(argv))

    def launched(self, tmp_path, repo, device="none") -> str:
        self.clock.advance(timedelta(minutes=1))
        source = tmp_path / "handoff.md"
        source.write_text(handoff_text((repo,), device), encoding="utf-8")
        assert self.run("new", "--slug", "x", str(source)) == 0
        job_id = self.lines[0]
        self.jobs.store.goal_path(job_id).write_text("goal", encoding="utf-8")
        assert self.run("launch", job_id) == 0
        return job_id

    def resources(self, job_id) -> frozenset[str]:
        return self.jobs.store.load(job_id).resources

    def relaunch_after_needs_input(self, job_id) -> None:
        self.jobs.finish(job_id, NEEDS_INPUT)
        del self.claude.statuses[job_id]
        self.jobs.launch(job_id)


@pytest.fixture
def h(root):
    return Harness(root)


@pytest.fixture
def pair(h, tmp_path):
    return h.launched(tmp_path, REPO_A), h.launched(tmp_path, REPO_B)


# --- Done when 1: a second bench claim is refused, then waits for the release --------------------------------

def test_done_1_second_launched_job_bench_claim_exits_one_naming_the_holder(h, pair, capsys):
    first, second = pair
    assert h.run("claim", first, BENCH) == 0
    assert h.run("claim", second, BENCH) == 1
    assert f"{BENCH} is held by {first}" in capsys.readouterr().err
    assert BENCH not in h.resources(second)


def test_done_1_claim_wait_succeeds_after_the_holder_releases(h, pair):
    first, second = pair
    assert h.run("claim", first, BENCH) == 0
    h.time.on_sleep = lambda count: h.run("release", first, BENCH)
    assert h.run("claim", second, BENCH, "--wait", "60") == 0
    assert h.time.sleeps == [10.0]
    assert BENCH in h.resources(second)
    assert BENCH not in h.resources(first)


def test_claim_wait_timeout_exits_one_naming_the_holder_after_polling_until_the_deadline(h, pair, capsys):
    first, second = pair
    assert h.run("claim", first, BENCH) == 0
    assert h.run("claim", second, BENCH, "--wait", "25") == 1
    assert f"{BENCH} is held by {first}" in capsys.readouterr().err
    assert h.time.sleeps == [10.0, 10.0, 5.0]


def test_claim_wait_timeout_raises_resource_held_from_the_provider(h, pair):
    first, second = pair
    h.jobs.claim(first, [BENCH])
    with pytest.raises(ResourceHeld) as caught:
        h.jobs.claim(second, [BENCH], 12)
    assert (caught.value.resource, caught.value.holder) == (BENCH, first)
    assert h.time.sleeps == [10.0, 2.0]


def test_claim_without_wait_does_not_sleep(h, pair):
    first, second = pair
    h.jobs.claim(first, [BENCH])
    with pytest.raises(ResourceHeld):
        h.jobs.claim(second, [BENCH])
    assert h.time.sleeps == []


@pytest.mark.parametrize("seconds", ["541", "-1", "soon"])
def test_claim_wait_outside_zero_to_540_is_a_usage_error(h, pair, seconds, capsys):
    with pytest.raises(SystemExit) as caught:
        h.run("claim", pair[0], BENCH, "--wait", seconds)
    assert caught.value.code == 2


def test_claim_of_several_resources_writes_none_when_one_is_held(h, pair):
    first, second = pair
    h.jobs.claim(first, [BENCH])
    with pytest.raises(ResourceHeld):
        h.jobs.claim(second, ["/work/free", BENCH])
    assert h.resources(second) == frozenset({REPO_B})


def test_claim_of_several_free_resources_takes_all(h, pair):
    first, _ = pair
    h.jobs.claim(first, [BENCH, "/work/free"])
    assert h.resources(first) == frozenset({REPO_A, BENCH, "/work/free"})


# --- Done when 2: device: bench no longer blocks at launch -----------------------------------------------------

def test_done_2_device_bench_no_longer_blocks_a_second_job_at_launch(h, tmp_path):
    first = h.launched(tmp_path, REPO_A, device="bench")
    second = h.launched(tmp_path, REPO_B, device="bench")
    h.run("list", "--json")
    assert BENCH not in h.resources(first)
    assert BENCH not in h.resources(second)
    assert h.claude.statuses.keys() == {first, second}


# --- Done when 3: no session list, no sleep under the lock ----------------------------------------------------

def test_done_3_claim_wait_reads_no_session_list(h, pair):
    first, second = pair
    h.jobs.claim(first, [BENCH])
    h.claude.fail_sessions = ClaudeError("claude agents is slow")
    h.claude.sessions_calls = 0
    h.time.on_sleep = lambda count: h.jobs.release(first, BENCH)
    assert h.run("claim", second, BENCH, "--wait", "30") == 0
    assert h.claude.sessions_calls == 0


def test_done_3_a_claim_holder_that_is_lost_still_holds_without_a_session_list(h, pair):
    first, second = pair
    h.jobs.claim(first, [BENCH])
    h.claude.fail_sessions = ClaudeError("claude agents is down")
    with pytest.raises(ResourceHeld):
        h.jobs.claim(second, [BENCH])


def test_done_3_no_sleep_runs_while_the_lock_is_held(h, pair):
    first, second = pair
    h.jobs.claim(first, [BENCH])
    outcomes: list[str] = []

    def probe(count):
        descriptor = os.open(h.root / "jobs", os.O_RDONLY | os.O_DIRECTORY)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            outcomes.append("free")
        except BlockingIOError:
            outcomes.append("locked")
        finally:
            os.close(descriptor)
        if count == 2:
            h.jobs.release(first, BENCH)

    h.time.on_sleep = probe
    assert h.run("claim", second, BENCH, "--wait", "60") == 0
    assert outcomes == ["free", "free"]


def test_store_locked_excludes_another_holder_of_the_jobs_directory_lock(h):
    (h.root / "jobs").mkdir(parents=True)
    descriptor = os.open(h.root / "jobs", os.O_RDONLY | os.O_DIRECTORY)
    try:
        with h.jobs.store.locked():
            with pytest.raises(BlockingIOError):
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        os.close(descriptor)


def test_store_locked_creates_no_lock_file(h):
    with h.jobs.store.locked():
        pass
    assert list((h.root / "jobs").iterdir()) == []


# --- claim precondition -----------------------------------------------------------------------------------

def test_claim_of_an_unlaunched_job_is_refused_and_writes_nothing(h, tmp_path):
    source = tmp_path / "handoff.md"
    source.write_text(handoff_text((REPO_A,)), encoding="utf-8")
    h.run("new", "--slug", "x", str(source))
    job_id = h.lines[0]
    with pytest.raises(JobStateError, match="no launched run"):
        h.jobs.claim(job_id, [BENCH])
    assert h.jobs.store.load(job_id).events == ()


def test_claim_of_a_job_with_a_result_is_refused(h, pair):
    first, _ = pair
    h.jobs.finish(first, NEEDS_INPUT)
    with pytest.raises(JobStateError, match="result"):
        h.jobs.claim(first, [BENCH])


def test_claim_of_a_closed_job_is_refused(h, pair):
    first, _ = pair
    h.jobs.stop(first)
    h.jobs.close(first)
    with pytest.raises(JobStateError, match="abandoned"):
        h.jobs.claim(first, [BENCH])


def test_claim_of_an_unlaunched_job_exits_one_from_the_cli(h, tmp_path, capsys):
    source = tmp_path / "handoff.md"
    source.write_text(handoff_text((REPO_A,)), encoding="utf-8")
    h.run("new", "--slug", "x", str(source))
    assert h.run("claim", h.lines[0], BENCH) == 1
    assert "launched run" in capsys.readouterr().err


def test_claim_of_a_run_whose_result_is_archived_is_refused_and_writes_nothing(h, pair):
    first, _ = pair
    h.jobs.finish(first, NEEDS_INPUT)
    assert h.jobs.store.archive_result(first, 1)
    before = h.jobs.store.load(first).events
    with pytest.raises(JobStateError, match="result"):
        h.jobs.claim(first, [BENCH])
    assert h.jobs.store.load(first).events == before


# --- run-scoped claims: a claim lives for its run -----------------------------------------------------------------

def test_run_scoped_run_one_claim_is_absent_from_resources_after_finish(h, pair):
    first, _ = pair
    h.jobs.claim(first, [BENCH])
    assert BENCH in h.resources(first)
    h.jobs.finish(first, NEEDS_INPUT)
    assert BENCH not in h.resources(first)
    assert REPO_A in h.resources(first)


def test_run_scoped_run_one_claim_is_absent_from_resources_after_run_two_starts(h, pair):
    first, _ = pair
    h.jobs.claim(first, [BENCH])
    h.relaunch_after_needs_input(first)
    assert h.jobs.store.load(first).run == 2
    assert BENCH not in h.resources(first)


def test_a_repo_claim_survives_finish_and_the_next_run(h, pair):
    first, _ = pair
    h.jobs.claim(first, ["/work/extra"])
    h.relaunch_after_needs_input(first)
    assert "/work/extra" in h.resources(first)


def test_a_run_two_claim_counts_in_run_two(h, pair):
    first, _ = pair
    h.jobs.claim(first, [BENCH])
    h.relaunch_after_needs_input(first)
    h.jobs.claim(first, [BENCH])
    assert BENCH in h.resources(first)
    assert h.jobs.store.load(first).events[-1] == Claim(BENCH, 2)


def test_a_finished_run_frees_the_bench_for_another_job(h, pair):
    first, second = pair
    h.jobs.claim(first, [BENCH])
    h.jobs.finish(first, NEEDS_INPUT)
    h.jobs.claim(second, [BENCH])
    assert BENCH in h.resources(second)


# --- release ----------------------------------------------------------------------------------

def test_release_of_a_repo_exits_one(h, pair, capsys):
    first, _ = pair
    assert h.run("release", first, REPO_A) == 1
    assert "held until the job ends" in capsys.readouterr().err
    assert REPO_A in h.resources(first)


def test_second_release_of_a_device_exits_zero(h, pair):
    first, _ = pair
    assert h.run("claim", first, BENCH) == 0
    assert h.run("release", first, BENCH) == 0
    assert h.run("release", first, BENCH) == 0
    assert BENCH not in h.resources(first)


def test_release_of_a_short_hold_never_claimed_exits_zero_and_writes_nothing(h, pair):
    first, _ = pair
    before = h.jobs.store.load(first).events
    assert h.run("release", first, BENCH) == 0
    assert h.jobs.store.load(first).events == before


def test_release_writes_one_release_event_and_the_job_may_claim_again(h, pair):
    first, _ = pair
    h.jobs.claim(first, [BENCH])
    h.jobs.release(first, BENCH)
    assert h.jobs.store.load(first).events[-1] == Release(BENCH)
    h.jobs.claim(first, [BENCH])
    assert BENCH in h.resources(first)


def test_release_of_a_build_directory_is_allowed(h, pair, tmp_path):
    first, _ = pair
    name = resource.build(str(tmp_path))
    h.jobs.claim(first, [name])
    assert h.run("release", first, name) == 0
    assert name not in h.resources(first)


def test_release_of_an_unknown_job_exits_one(h, capsys):
    assert h.run("release", "261013-1800-video-core-nothing", BENCH) == 1
    assert "unknown job" in capsys.readouterr().err


def test_release_frees_the_resource_for_another_job_at_once(h, pair):
    first, second = pair
    h.jobs.claim(first, [BENCH])
    h.jobs.release(first, BENCH)
    h.jobs.claim(second, [BENCH])
    assert BENCH in h.resources(second)


# --- a legacy claim without run -------------------------------------------------------------

def test_legacy_claim_without_run_counts_across_runs_and_after_the_result(h, pair):
    first, _ = pair
    h.jobs.store.append_event(first, Claim(BENCH))
    assert BENCH in h.resources(first)
    h.relaunch_after_needs_input(first)
    assert BENCH in h.resources(first)
    h.jobs.finish(first, NEEDS_INPUT)
    assert BENCH in h.resources(first)


def test_legacy_claim_holds_the_bench_against_another_job(h, pair):
    first, second = pair
    h.jobs.store.append_event(first, Claim(BENCH))
    with pytest.raises(ResourceHeld) as caught:
        h.jobs.claim(second, [BENCH])
    assert caught.value.holder == first


def test_a_release_cancels_a_legacy_claim(h, pair):
    first, _ = pair
    h.jobs.store.append_event(first, Claim(BENCH))
    h.jobs.release(first, BENCH)
    assert BENCH not in h.resources(first)


# --- resource.py ------------------------------------------------------------------------------------------

def test_kind_names_repo_device_and_build():
    assert resource.kind("/work/a") is resource.Kind.REPO
    assert resource.kind(BENCH) is resource.Kind.DEVICE
    assert resource.kind("build:/work/a/build") is resource.Kind.BUILD


def test_only_device_and_build_are_short_holds():
    assert resource.is_short_hold(BENCH)
    assert resource.is_short_hold("build:/work/a/build")
    assert not resource.is_short_hold("/work/a")


def test_build_prefixes_the_resolved_absolute_path(tmp_path):
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real)
    assert resource.build(str(link)) == "build:" + str(real.resolve())


def test_build_refuses_a_relative_path():
    with pytest.raises(ValueError):
        resource.build("relative/build")


def test_parse_accepts_bench_build_and_repo_and_normalises_each(tmp_path):
    assert resource.parse(BENCH) == BENCH
    assert resource.parse(f"build:{tmp_path}/x/../") == "build:" + str(tmp_path.resolve())
    assert resource.parse("/work/extra/../a/") == "/work/a"


def test_parse_refuses_a_relative_build_path():
    with pytest.raises(ValueError):
        resource.parse("build:relative")


# --- events -----------------------------------------------------------------------------------------------

def test_claim_with_a_run_encodes_the_run_and_round_trips():
    event = Claim(BENCH, 2)
    assert encode(event) == '{"event":"claim","resource":"device:bench","run":2}'
    assert decode(encode(event)) == event


def test_claim_without_a_run_encodes_no_run_and_decodes_to_none():
    assert encode(Claim(BENCH)) == '{"event":"claim","resource":"device:bench"}'
    assert decode('{"event":"claim","resource":"device:bench"}') == Claim(BENCH, None)


def test_release_line_shape_and_round_trip():
    assert encode(Release(BENCH)) == '{"event":"release","resource":"device:bench"}'
    assert decode(encode(Release(BENCH))) == Release(BENCH)


@pytest.mark.parametrize("line", ['{"event":"release"}', '{"event":"release","resource":3}',
                                  '{"event":"claim","resource":"/a","run":"1"}'])
def test_decode_rejects_malformed_release_and_claim_run(line):
    with pytest.raises(ValueError):
        decode(line)


# --- an archived result ends the run's short holds before the next Launched is written ------------------------------

def _archive_run_one(h, job_id):
    h.jobs.finish(job_id, NEEDS_INPUT)
    assert h.jobs.store.archive_result(job_id, 1)


def test_archived_result_ends_a_short_hold_and_frees_the_bench_for_another_job(h, pair):
    first, second = pair
    h.jobs.claim(first, [BENCH])
    _archive_run_one(h, first)
    assert BENCH not in h.resources(first)
    assert h.run("claim", second, BENCH) == 0


def test_failed_relaunch_leaves_the_bench_unheld(h, pair):
    first, _ = pair
    h.jobs.claim(first, [BENCH])
    h.jobs.finish(first, NEEDS_INPUT)
    del h.claude.statuses[first]
    h.claude.fail_start = ClaudeError("cannot start")
    with pytest.raises(ClaudeError):
        h.jobs.launch(first)
    assert (h.jobs.store.job_dir(first) / "result.md").is_file()
    assert BENCH not in h.resources(first)


def test_archived_result_keeps_a_repo_claim(h, pair):
    first, _ = pair
    h.jobs.claim(first, ["/work/extra"])
    _archive_run_one(h, first)
    assert "/work/extra" in h.resources(first)


def test_archived_result_keeps_a_legacy_bench_claim(h, pair):
    first, _ = pair
    h.jobs.store.append_event(first, Claim(BENCH))
    _archive_run_one(h, first)
    assert BENCH in h.resources(first)


def test_archived_runs_are_the_positive_integer_result_files_only(h, pair):
    first, _ = pair
    directory = h.jobs.store.job_dir(first)
    for name in ("result-1.md", "result-2.md", "result-0.md", "result-01.md", "result-x.md"):
        (directory / name).write_text("---\nstatus: done\n---\n", encoding="utf-8")
    assert h.jobs.store.load(first).archived_runs == {1, 2}


# --- release on a job that no longer runs -------------------------------------------------------------------------

def _closed_with_bench(h, job_id):
    h.jobs.claim(job_id, [BENCH])
    h.jobs.stop(job_id)
    h.jobs.close(job_id)
    log = h.jobs.store.job_dir(job_id) / "dispatch.jsonl"
    os.utime(log, (1_000_000_000, 1_000_000_000))
    return log


def test_release_on_a_closed_job_exits_zero_and_leaves_the_log_untouched(h, pair):
    first, _ = pair
    log = _closed_with_bench(h, first)
    before = (log.read_bytes(), log.stat().st_mtime_ns)
    assert h.run("release", first, BENCH) == 0
    assert (log.read_bytes(), log.stat().st_mtime_ns) == before


def test_release_of_a_repo_on_a_closed_job_still_exits_one(h, pair):
    first, _ = pair
    _closed_with_bench(h, first)
    assert h.run("release", first, "/work/extra") == 1


def test_release_on_a_done_job_exits_zero_and_writes_nothing(h, pair):
    first, _ = pair
    h.jobs.claim(first, [BENCH])
    h.jobs.finish(first, Report(ResultStatus.DONE))
    log = h.jobs.store.job_dir(first) / "dispatch.jsonl"
    before = log.read_bytes()
    assert h.run("release", first, BENCH) == 0
    assert log.read_bytes() == before


def test_release_on_an_invalid_job_exits_one(h, pair, capsys):
    first, _ = pair
    (h.jobs.store.job_dir(first) / "dispatch.jsonl").write_text("{not json\n", encoding="utf-8")
    assert h.run("release", first, BENCH) == 1
    assert "invalid" in capsys.readouterr().err


# --- Review round 1: R1-2, R1-4, R1-5 -------------------------------------------------------------------

def _jobs_lock_is_held(root) -> bool:
    descriptor = os.open(root / "jobs", os.O_RDONLY | os.O_DIRECTORY)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return True
    finally:
        os.close(descriptor)
    return False


def test_claim_holds_the_store_lock_during_the_snapshot_and_the_append(h, pair, monkeypatch):
    _, second = pair
    store = h.jobs.store
    observed: dict[str, bool] = {}
    snapshot, append_events = store.snapshot, store.append_events

    def probing_snapshot():
        observed["snapshot"] = _jobs_lock_is_held(h.root)
        return snapshot()

    def probing_append(job_id, events):
        observed["append"] = _jobs_lock_is_held(h.root)
        append_events(job_id, events)

    monkeypatch.setattr(store, "snapshot", probing_snapshot)
    monkeypatch.setattr(store, "append_events", probing_append)
    h.jobs.claim(second, [BENCH])
    assert observed == {"snapshot": True, "append": True}


def test_claim_wait_on_a_held_bench_refuses_an_invalid_job_on_the_first_poll(h, pair, tmp_path, capsys):
    first, second = pair
    invalid = h.launched(tmp_path, "/work/c")
    h.jobs.claim(first, [BENCH])
    (h.jobs.store.job_dir(invalid) / "dispatch.jsonl").write_text("{not json\n", encoding="utf-8")
    assert h.run("claim", second, BENCH, "--wait", "540") == 1
    err = capsys.readouterr().err
    assert f"claim refused: job {invalid} is invalid" in err
    assert "is held by" not in err
    assert h.time.sleeps == []
    assert BENCH not in h.resources(second)


def test_claim_of_several_resources_is_one_write(h, pair, monkeypatch):
    _, second = pair
    writes: list[bytes] = []
    real_write = os.write

    def counting_write(descriptor, data):
        writes.append(bytes(data))
        return real_write(descriptor, data)

    monkeypatch.setattr(os, "write", counting_write)
    h.jobs.claim(second, [BENCH, "device:other"])
    assert len(writes) == 1
    claims = [decode(line) for line in writes[0].decode().splitlines()]
    assert [c.resource for c in claims] == [BENCH, "device:other"]
    assert h.resources(second) >= {BENCH, "device:other"}


def test_claim_of_several_resources_records_none_when_the_write_fails(h, pair, monkeypatch):
    _, second = pair
    before = h.resources(second)

    def failing_write(descriptor, data):
        raise OSError("disk full")

    monkeypatch.setattr(os, "write", failing_write)
    with pytest.raises(Exception):
        h.jobs.claim(second, [BENCH, "device:other"])
    monkeypatch.undo()
    assert h.resources(second) == before


def test_append_events_with_no_events_writes_nothing_and_creates_no_file(h, tmp_path):
    store = h.jobs.store
    source = tmp_path / "handoff.md"
    source.write_text(handoff_text((REPO_A,), "none"), encoding="utf-8")
    assert h.run("new", "--slug", "x", str(source)) == 0
    job_id = h.lines[0]
    log = store.job_dir(job_id) / "dispatch.jsonl"
    log.unlink(missing_ok=True)
    store.append_events(job_id, [])
    assert not log.exists()
