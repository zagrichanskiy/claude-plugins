"""Issue 126: ids no longer sort by creation time, so the views, the lock and ``list`` order by ``created``."""
from __future__ import annotations

import dataclasses
import json
from datetime import timedelta

from cure_job.events import Claim
from cure_job.state import derive, holders, lock_rank
from tests.builders import NOW, handoff_text, make_record
from tests.test_approve import DONE_RESULT
from tests.test_cli import Harness
from tests.test_state import launched

OLD = "abc-7-video-core-old"
NEW = "261013-1000-video-core-new"


def created(record, minutes: int):
    return dataclasses.replace(record, handoff=dataclasses.replace(record.handoff,
                                                                   created=NOW + timedelta(minutes=minutes)))


def test_views_order_by_creation_time_then_id():
    tie = "261013-0900-video-core-tie"
    records = [created(make_record(NEW), 2), created(make_record(tie), 1), created(make_record(OLD), 1)]
    assert [view.record.id for view in derive(records, {}, NOW, frozenset())] == [tie, OLD, NEW]


def test_lock_order_is_launched_first_then_creation_time():
    old = created(make_record(OLD, events=(launched(OLD), Claim("r"))), 1)
    new = created(make_record(NEW, events=(launched(NEW), Claim("r"))), 2)
    assert holders([new, old]) == {"r": OLD}
    queued = created(make_record("261013-0800-video-core-q"), 0)
    assert sorted([queued, new, old], key=lock_rank) == [old, new, queued]


def test_list_orders_jobs_by_creation_time_and_new_uses_the_handoff_ticket(root, tmp_path):
    h = Harness(root)
    source = tmp_path / "handoff.md"
    source.write_text(handoff_text().replace("device: none", "device: none\nticket: ABC-7"), encoding="utf-8")
    assert h.run("new", "--slug", "old", str(source)) == 0
    first = h.lines[0]
    assert first == "abc-7-video-core-old"
    h.clock.advance(timedelta(minutes=1))
    second = h.new(tmp_path, slug="new")
    assert second < first
    h.lines.clear()
    assert h.run("list", "--json") == 0
    assert [row["id"] for row in json.loads(h.lines[0])] == [first, second]


def test_next_orders_an_invalid_job_with_a_launched_one(root, tmp_path):
    h = Harness(root)
    launched_id = h.new(tmp_path, slug="a")
    h.approve(launched_id)
    assert h.run("launch", launched_id) == 0
    # A result gives the launched job an action, so next lists it.
    (root / "jobs" / launched_id / "result.md").write_text(DONE_RESULT, encoding="utf-8")
    invalid_id = h.new(tmp_path, slug="b")
    (root / "jobs" / invalid_id / "dispatch.jsonl").write_text("garbage\n", encoding="utf-8")
    h.lines.clear()
    assert h.run("next", "--json") == 0
    ids = [row["id"] for row in json.loads(h.lines[0])]
    # The invalid job's creation time does not read, so it ranks first among the launched jobs.
    assert ids.index(invalid_id) < ids.index(launched_id)
