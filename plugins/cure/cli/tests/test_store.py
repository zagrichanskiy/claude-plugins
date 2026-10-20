"""``JobStore`` on a temporary root: id reservation, loading, events, archive and removal."""
from __future__ import annotations

import os
from datetime import timezone

import pytest

from cure_job.errors import HandoffError, StoreError, UnknownJob
from cure_job.events import Claim, Closed, Launched
from cure_job.job_id import MAX_SUFFIX, with_suffix
from cure_job.result import ResultStatus
from cure_job.store import JobStore
from tests.builders import NOW, handoff_text

BASE = "261013-1742-video-core-x"


@pytest.fixture
def store(tmp_path):
    return JobStore(tmp_path / "state")


def render(job_id):
    return handoff_text()


def test_constructor_does_no_io(tmp_path):
    JobStore(tmp_path / "absent")
    assert not (tmp_path / "absent").exists()


def test_job_dir_is_under_jobs(store):
    assert store.job_dir(BASE).parts[-2:] == ("jobs", BASE)
    assert store.goal_path(BASE) == store.job_dir(BASE) / "goal.md"


@pytest.mark.parametrize("bad", ["../escape", "", "Not-An-Id", "261013-1742-x/../y"])
def test_job_dir_rejects_invalid_ids(store, bad):
    with pytest.raises(ValueError):
        store.job_dir(bad)


def test_create_writes_rendered_handoff_and_returns_the_id(store):
    created = store.create(BASE, lambda job_id: f"id={job_id}\n")
    assert created == BASE
    assert (store.job_dir(BASE) / "handoff.md").read_text(encoding="utf-8") == f"id={BASE}\n"


def test_create_makes_jobs_directory_with_parents(store):
    store.create(BASE, render)
    assert (store.job_dir(BASE) / "handoff.md").is_file()


def test_create_on_collision_uses_the_next_suffix(store):
    first = store.create(BASE, render)
    second = store.create(BASE, render)
    third = store.create(BASE, render)
    assert (first, second, third) == (BASE, BASE + "-2", BASE + "-3")


def test_create_renders_with_the_final_id(store):
    store.create(BASE, render)
    seen = []
    store.create(BASE, lambda job_id: seen.append(job_id) or handoff_text())
    assert seen == [BASE + "-2"]


def test_create_raises_store_error_when_every_suffix_is_taken(store):
    store.create(BASE, render)
    for n in range(2, MAX_SUFFIX + 1):
        store.job_dir(with_suffix(BASE, n)).mkdir(parents=True)
    with pytest.raises(StoreError):
        store.create(BASE, render)


def test_create_leaves_no_temporary_directory_behind(store):
    store.create(BASE, render)
    assert [p.name for p in (store.job_dir(BASE).parent).iterdir()] == [BASE]


def test_create_cleans_up_when_render_fails(store):
    def boom(job_id):
        raise RuntimeError("render failed")
    with pytest.raises(RuntimeError):
        store.create(BASE, boom)
    jobs = store.job_dir(BASE).parent
    assert list(jobs.iterdir()) == []


def test_create_never_exposes_a_job_directory_without_handoff(store):
    seen = []

    def render_and_look(job_id):
        seen.append(store.load_all())
        return handoff_text()

    store.create(BASE, render_and_look)
    assert seen == [[]]


def test_load_returns_the_record(store):
    store.create(BASE, render)
    record = store.load(BASE)
    assert record.id == BASE
    assert record.dir == store.job_dir(BASE)
    assert record.handoff.repos == ("/work/video-core",)
    assert not record.has_goal
    assert record.events == ()
    assert record.result is None
    assert record.result_mtime is None
    assert record.events_mtime is None
    assert record.run == 0 and record.session is None and record.closed is None


def test_load_unknown_job_raises_unknown_job(store):
    with pytest.raises(UnknownJob):
        store.load(BASE)


def test_load_sees_goal_and_result_and_mtimes(store):
    store.create(BASE, render)
    directory = store.job_dir(BASE)
    (directory / "goal.md").write_text("goal", encoding="utf-8")
    (directory / "result.md").write_text("---\nstatus: failed\n---\n", encoding="utf-8")
    os.utime(directory / "result.md", (1_700_000_000, 1_700_000_000))
    record = store.load(BASE)
    assert record.has_goal
    assert record.result.status is ResultStatus.FAILED
    assert record.result_mtime.tzinfo is not None
    assert record.result_mtime.astimezone(timezone.utc).timestamp() == 1_700_000_000


def test_load_malformed_result_does_not_raise(store):
    store.create(BASE, render)
    (store.job_dir(BASE) / "result.md").write_text("garbage", encoding="utf-8")
    assert store.load(BASE).result.problem


def test_load_invalid_handoff_names_the_path(store):
    directory = store.job_dir(BASE)
    directory.mkdir(parents=True)
    (directory / "handoff.md").write_text("no frontmatter", encoding="utf-8")
    with pytest.raises(HandoffError, match="handoff.md"):
        store.load(BASE)


def test_append_event_writes_one_line_per_event_in_order(store):
    store.create(BASE, render)
    store.append_event(BASE, Launched(1, BASE, NOW))
    store.append_event(BASE, Claim("device:bench"))
    store.append_event(BASE, Closed("done with it"))
    lines = (store.job_dir(BASE) / "dispatch.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3
    record = store.load(BASE)
    assert record.events == (Launched(1, BASE, NOW), Claim("device:bench"), Closed("done with it"))
    assert record.run == 1 and record.session == BASE
    assert record.closed == Closed("done with it")
    assert record.events_mtime is not None
    assert "device:bench" in record.resources


def test_record_run_counts_launches_and_session_is_the_latest(store):
    store.create(BASE, render)
    store.append_event(BASE, Launched(1, BASE, NOW))
    store.append_event(BASE, Launched(2, BASE + "-r2", NOW))
    record = store.load(BASE)
    assert (record.run, record.session) == (2, BASE + "-r2")


def test_record_closed_is_the_first_closed_event(store):
    store.create(BASE, render)
    store.append_event(BASE, Closed("first"))
    store.append_event(BASE, Closed("second"))
    assert store.load(BASE).closed == Closed("first")


def test_load_skips_blank_lines_and_unknown_events(store):
    store.create(BASE, render)
    (store.job_dir(BASE) / "dispatch.jsonl").write_text(
        '\n{"event":"paused"}\n{"event":"closed","reason":"r"}\n\n', encoding="utf-8")
    assert store.load(BASE).events == (Closed("r"),)


def test_load_malformed_event_line_names_path_and_line(store):
    store.create(BASE, render)
    (store.job_dir(BASE) / "dispatch.jsonl").write_text('{"event":"closed","reason":"r"}\nnot json\n',
                                                        encoding="utf-8")
    with pytest.raises(StoreError, match=r"dispatch\.jsonl:2"):
        store.load(BASE)


def test_events_round_trip_non_ascii_text_as_utf8(store):
    store.create(BASE, render)
    store.append_event(BASE, Closed("zakrito — доведено"))
    assert store.load(BASE).closed.reason.endswith("доведено")


def test_archive_result_renames_to_the_run_number(store):
    store.create(BASE, render)
    directory = store.job_dir(BASE)
    (directory / "result.md").write_text("old", encoding="utf-8")
    assert store.archive_result(BASE, 1) is True
    assert not (directory / "result.md").exists()
    assert (directory / "result-1.md").read_text(encoding="utf-8") == "old"


def test_archive_result_without_a_result_returns_false(store):
    store.create(BASE, render)
    assert store.archive_result(BASE, 1) is False


def test_restore_result_is_the_inverse_rename(store):
    store.create(BASE, render)
    directory = store.job_dir(BASE)
    (directory / "result.md").write_text("old", encoding="utf-8")
    store.archive_result(BASE, 2)
    store.restore_result(BASE, 2)
    assert (directory / "result.md").read_text(encoding="utf-8") == "old"
    assert not (directory / "result-2.md").exists()


def test_remove_deletes_the_whole_tree(store):
    store.create(BASE, render)
    (store.job_dir(BASE) / "result-1.md").write_text("x", encoding="utf-8")
    store.remove(BASE)
    assert not store.job_dir(BASE).exists()


def test_load_all_is_empty_when_jobs_directory_is_absent(store):
    assert store.load_all() == []


def test_load_all_is_ascending_and_skips_foreign_entries(store):
    later = "261014-0900-video-core-y"
    store.create(later, render)
    store.create(BASE, render)
    jobs = store.job_dir(BASE).parent
    (jobs / "stray-file.txt").write_text("x", encoding="utf-8")
    (jobs / "Not-An-Id").mkdir()
    (jobs / "261013-1800-empty-dir").mkdir()
    (jobs / ".new-leftover").mkdir()
    assert [record.id for record in store.load_all()] == [BASE, later]


def test_unreadable_state_root_is_a_store_error(tmp_path):
    blocker = tmp_path / "file"
    blocker.write_text("x", encoding="utf-8")
    with pytest.raises(StoreError):
        JobStore(blocker / "state").create(BASE, render)


def test_read_goal_returns_the_goal_text(store):
    job_id = store.create(BASE, render)
    store.goal_path(job_id).write_text("the goal", encoding="utf-8")
    assert store.read_goal(job_id) == "the goal"


def test_read_goal_without_a_goal_file_raises_unknown_job(store):
    job_id = store.create(BASE, render)
    with pytest.raises(UnknownJob):
        store.read_goal(job_id)
