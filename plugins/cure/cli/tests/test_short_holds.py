"""Issue 32: ``release``, run-scoped short-hold claims, the ``claim`` precondition and ``claim --wait``."""
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


# --- Done when 2: a claim lives for its run -----------------------------------------------------------------

def test_done_2_run_one_claim_is_absent_from_resources_after_finish(h, pair):
    first, _ = pair
    h.jobs.claim(first, [BENCH])
    assert BENCH in h.resources(first)
    h.jobs.finish(first, NEEDS_INPUT)
    assert BENCH not in h.resources(first)
    assert REPO_A in h.resources(first)


def test_done_2_run_one_claim_is_absent_from_resources_after_run_two_starts(h, pair):
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


# --- Done when 3: release ----------------------------------------------------------------------------------

def test_done_3_release_of_a_repo_exits_one(h, pair, capsys):
    first, _ = pair
    assert h.run("release", first, REPO_A) == 1
    assert "held until the job ends" in capsys.readouterr().err
    assert REPO_A in h.resources(first)


def test_done_3_second_release_of_a_device_exits_zero(h, pair):
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


# --- Done when 4: device: bench no longer blocks at launch -----------------------------------------------------

def test_done_4_device_bench_no_longer_blocks_a_second_job_at_launch(h, tmp_path):
    first = h.launched(tmp_path, REPO_A, device="bench")
    second = h.launched(tmp_path, REPO_B, device="bench")
    h.run("list", "--json")
    assert BENCH not in h.resources(first)
    assert BENCH not in h.resources(second)
    assert h.claude.statuses.keys() == {first, second}


# --- Done when 5: a legacy claim without run -------------------------------------------------------------

def test_done_5_legacy_claim_without_run_counts_across_runs_and_after_the_result(h, pair):
    first, _ = pair
    h.jobs.store.append_event(first, Claim(BENCH))
    assert BENCH in h.resources(first)
    h.relaunch_after_needs_input(first)
    assert BENCH in h.resources(first)
    h.jobs.finish(first, NEEDS_INPUT)
    assert BENCH in h.resources(first)


def test_done_5_legacy_claim_holds_the_bench_against_another_job(h, pair):
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


# --- Done when 6: no session list, no sleep under the lock ----------------------------------------------------

def test_done_6_claim_wait_reads_no_session_list(h, pair):
    first, second = pair
    h.jobs.claim(first, [BENCH])
    h.claude.fail_sessions = ClaudeError("claude agents is slow")
    h.claude.sessions_calls = 0
    h.time.on_sleep = lambda count: h.jobs.release(first, BENCH)
    assert h.run("claim", second, BENCH, "--wait", "30") == 0
    assert h.claude.sessions_calls == 0


def test_done_6_a_claim_holder_that_is_lost_still_holds_without_a_session_list(h, pair):
    first, second = pair
    h.jobs.claim(first, [BENCH])
    h.claude.fail_sessions = ClaudeError("claude agents is down")
    with pytest.raises(ResourceHeld):
        h.jobs.claim(second, [BENCH])


def test_done_6_no_sleep_runs_while_the_lock_is_held(h, pair):
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
