"""Issue 33: the ``build:<dir>`` resource, the all-or-none claim and the hold-and-wait refusal."""
from __future__ import annotations

import pytest

from cure_job import resource
from cure_job.events import Claim
from tests.test_short_holds import BENCH, REPO_A, REPO_B, Harness


@pytest.fixture
def h(root):
    return Harness(root)


@pytest.fixture
def pair(h, tmp_path):
    return h.launched(tmp_path, REPO_A), h.launched(tmp_path, REPO_B)


def claims(h, job_id):
    return [event for event in h.jobs.store.load(job_id).events if isinstance(event, Claim)]


def test_build_claim_through_a_symlink_stores_the_realpath(h, pair, tmp_path):
    first, _ = pair
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real)
    assert h.run("claim", first, f"build:{link}") == 0
    assert h.resources(first) >= {f"build:{real.resolve()}"}
    assert f"build:{link}" not in h.resources(first)


def test_build_claim_with_dot_dot_stores_the_realpath(h, pair, tmp_path):
    first, _ = pair
    (tmp_path / "b").mkdir()
    assert h.run("claim", first, f"build:{tmp_path}/b/../b") == 0
    assert f"build:{tmp_path.resolve()}/b" in h.resources(first)


def test_two_spellings_of_one_build_directory_conflict(h, pair, tmp_path, capsys):
    first, second = pair
    real = tmp_path / "real"
    real.mkdir()
    link = tmp_path / "link"
    link.symlink_to(real)
    assert h.run("claim", first, f"build:{real}") == 0
    assert h.run("claim", second, f"build:{link}") == 1
    assert "is held by" in capsys.readouterr().err


def test_relative_build_path_is_a_usage_error(h, pair, capsys):
    first, _ = pair
    with pytest.raises(SystemExit) as caught:
        h.cli.run(["claim", first, "build:relative/dir"])
    assert caught.value.code == 2
    assert "is not an absolute path" in capsys.readouterr().err


def test_claim_of_several_resources_with_one_held_writes_no_event(h, pair, capsys):
    first, second = pair
    assert h.run("claim", first, BENCH) == 0
    before = h.jobs.store.load(second).events
    assert h.run("claim", second, "build:/w", BENCH) == 1
    assert f"{BENCH} is held by {first}" in capsys.readouterr().err
    assert h.jobs.store.load(second).events == before
    assert "build:/w" not in h.resources(second)


def test_claim_of_several_free_resources_appends_one_event_each(h, pair):
    first, _ = pair
    before = len(claims(h, first))
    assert h.run("claim", first, "build:/w", BENCH) == 0
    appended = claims(h, first)[before:]
    assert [event.resource for event in appended] == ["build:/w", BENCH]


def test_claim_naming_one_resource_twice_appends_one_event_for_it(h, pair):
    first, _ = pair
    before = len(claims(h, first))
    assert h.run("claim", first, "build:/w", "build:/w", BENCH) == 0
    appended = claims(h, first)[before:]
    assert [event.resource for event in appended] == ["build:/w", BENCH]


def test_wait_claim_of_a_build_is_refused_while_the_run_holds_the_bench(h, pair, capsys):
    first, _ = pair
    assert h.run("claim", first, BENCH) == 0
    assert h.run("claim", "--wait", "5", first, "build:/w") == 1
    assert f"release {BENCH} first" in capsys.readouterr().err
    assert "build:/w" not in h.resources(first)


def test_claim_of_an_unheld_repository_is_refused_while_the_run_holds_the_bench(h, pair, capsys):
    first, _ = pair
    assert h.run("claim", first, BENCH) == 0
    assert h.run("claim", first, REPO_B) == 1
    assert f"release {BENCH} first" in capsys.readouterr().err


def test_reclaiming_a_held_resource_is_accepted_while_the_run_holds_the_bench(h, pair):
    first, _ = pair
    assert h.run("claim", first, BENCH) == 0
    assert h.run("claim", first, BENCH, REPO_A) == 0


def test_claim_is_accepted_again_after_the_short_hold_is_released(h, pair):
    first, _ = pair
    assert h.run("claim", first, BENCH) == 0
    assert h.run("release", first, BENCH) == 0
    assert h.run("claim", first, "build:/w") == 0


def test_wait_claim_of_a_repository_exits_one_when_the_run_holds_nothing_short(h, pair, capsys):
    first, _ = pair
    assert h.run("claim", "--wait", "5", first, REPO_B) == 1
    assert "claim --wait accepts only device: and build:" in capsys.readouterr().err
    assert h.time.sleeps == []


def test_wait_claim_mixing_a_repository_and_the_bench_writes_nothing(h, pair):
    first, _ = pair
    assert h.run("claim", "--wait", "5", first, BENCH, REPO_A) == 1
    assert BENCH not in h.resources(first)


def test_build_name_parses_to_the_resolved_path(tmp_path):
    assert resource.parse(f"build:{tmp_path}/x/..") == f"build:{tmp_path.resolve()}"
