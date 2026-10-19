"""Issue 35: ordering stacked jobs with ``after:`` in the handoff.

Each test names the "Done when" item of the issue it pins."""
from __future__ import annotations

import json
import os
import re
import shutil
from datetime import timedelta

import pytest

from tests.builders import NOW, handoff_text
from tests.test_approve import DONE_RESULT, NEEDS_INPUT_RESULT, _needs_input_job, goal_file, rows
from tests.test_cli import Harness

FAILED_RESULT = "---\nstatus: failed\n---\n"
UNPROVEN_RESULT = "---\nstatus: done\nunproven:\n  - 1\n---\n"
X, Y = "/work/x", "/work/y"
UNRESOLVED = "unresolved"


@pytest.fixture
def h(root):
    return Harness(root)


def result_file(h, job_id):
    return h.root / "jobs" / job_id / "result.md"


def next_actions(h):
    h.lines.clear()
    assert h.run("next", "--json") == 0
    return {row["id"]: row for row in json.loads(h.lines[0])}


def failed_predecessor(h, tmp_path):
    pred = h.new(tmp_path, repos=(X,))
    h.approve(pred)
    assert h.run("launch", pred) == 0
    result_file(h, pred).write_text(FAILED_RESULT, encoding="utf-8")
    return pred


def corrupt(h, job_id):
    (h.root / "jobs" / job_id / "dispatch.jsonl").write_text("garbage\n", encoding="utf-8")


def remove_dir(h, job_id):
    shutil.rmtree(h.root / "jobs" / job_id)


# --- Done when 1 ---------------------------------------------------------------------------------------

@pytest.mark.parametrize("after", ["261013-1800-video-core-nothing", "../etc", "not-an-id"])
def test_done_when_1_new_with_an_unknown_or_malformed_after_exits_one(h, tmp_path, capsys, after):
    source = tmp_path / "handoff.md"
    source.write_text(handoff_text(after=after), encoding="utf-8")
    assert h.run("new", "--slug", "x", str(source)) == 1
    captured = capsys.readouterr()
    assert captured.err.startswith("error: ")
    assert "Traceback" not in captured.err
    assert not (h.root / "jobs").exists() or not list((h.root / "jobs").iterdir())


def test_done_when_1_new_with_an_existing_after_succeeds_and_lists_it(h, tmp_path):
    pred = h.new(tmp_path, repos=(X,))
    succ = h.new(tmp_path, repos=(Y,), after=pred)
    row = rows(h)[succ]
    assert (row["after"], row["after-state"]) == (pred, "queued")


# --- Done when 2 ---------------------------------------------------------------------------------------

def test_done_when_2_successor_is_held_with_empty_blocked_by_until_the_predecessor_is_done(h, tmp_path):
    pred = h.new(tmp_path, repos=(X,))
    h.approve(pred)
    succ = h.new(tmp_path, repos=(Y,), after=pred)
    h.approve(succ)
    row = rows(h)[succ]
    assert (row["state"], row["blocked-by"], row["after"], row["after-state"]) == ("held", [], pred, "approved")
    assert h.run("launch", pred) == 0
    assert rows(h)[succ]["after-state"] == "running"
    assert rows(h)[succ]["state"] == "held"
    result_file(h, pred).write_text(DONE_RESULT, encoding="utf-8")
    row = rows(h)[succ]
    assert (row["state"], row["blocked-by"], row["after-state"]) == ("approved", [], "done")


def test_done_when_2_a_needs_input_predecessor_keeps_the_successor_held(h, tmp_path):
    pred, _ = _needs_input_job(h, tmp_path)
    succ = h.new(tmp_path, repos=(Y,), after=pred)
    h.approve(succ)
    row = rows(h)[succ]
    assert (row["state"], row["blocked-by"], row["after-state"]) == ("held", [], "needs-input")


def test_done_when_2_a_done_predecessor_with_an_unproven_item_keeps_the_successor_held(h, tmp_path):
    pred = h.new(tmp_path, repos=(X,))
    h.approve(pred)
    assert h.run("launch", pred) == 0
    result_file(h, pred).write_text(UNPROVEN_RESULT, encoding="utf-8")
    succ = h.new(tmp_path, repos=(Y,), after=pred)
    h.approve(succ)
    row = rows(h)[succ]
    assert (row["state"], row["after-state"]) == ("held", "needs-input")


def test_done_when_2_plain_list_prints_the_predecessor_and_its_state(h, tmp_path):
    pred = h.new(tmp_path, repos=(X,))
    succ = h.new(tmp_path, repos=(Y,), after=pred)
    h.lines.clear()
    assert h.run("list") == 0
    assert h.lines[1].endswith(f"held  after={pred}:queued")


# --- Done when 3 ---------------------------------------------------------------------------------------

def test_done_when_3_launch_of_an_after_held_job_exits_one_naming_the_predecessor_and_its_state(h, tmp_path, capsys):
    pred, _ = _needs_input_job(h, tmp_path)
    succ = h.new(tmp_path, repos=(Y,), after=pred)
    h.approve(succ)
    capsys.readouterr()
    assert h.run("launch", succ) == 1
    err = capsys.readouterr().err
    assert err.strip() == f"error: after {pred} is needs-input"
    assert "Traceback" not in err
    assert not any(event["event"] == "launched" for event in _events(h, succ))


def _events(h, job_id):
    path = h.root / "jobs" / job_id / "dispatch.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


# --- Done when 4 ---------------------------------------------------------------------------------------

def test_done_when_4_a_failed_predecessor_gives_after_state_failed(h, tmp_path):
    pred = failed_predecessor(h, tmp_path)
    succ = h.new(tmp_path, repos=(Y,), after=pred)
    row = rows(h)[succ]
    assert (row["state"], row["after-state"]) == ("held", "failed")


def test_done_when_4_an_invalid_predecessor_gives_after_state_invalid(h, tmp_path):
    pred = h.new(tmp_path, repos=(X,))
    succ = h.new(tmp_path, repos=(Y,), after=pred)
    corrupt(h, pred)
    row = rows(h)[succ]
    assert (row["state"], row["after"], row["after-state"]) == ("held", pred, "invalid")


def test_done_when_4_a_removed_predecessor_gives_after_state_missing(h, tmp_path):
    pred = h.new(tmp_path, repos=(X,))
    succ = h.new(tmp_path, repos=(Y,), after=pred)
    remove_dir(h, pred)
    row = rows(h)[succ]
    assert (row["state"], row["after"], row["after-state"]) == ("held", pred, "missing")


# --- Done when 5 ---------------------------------------------------------------------------------------

def _expire(h, job_id):
    stamp = (NOW - timedelta(days=60)).timestamp()
    os.utime(h.root / "jobs" / job_id / "dispatch.jsonl", (stamp, stamp))


def test_done_when_5_prune_keeps_an_expired_predecessor_of_an_open_job_and_prunes_an_unreferenced_one(h, tmp_path):
    pred = h.new(tmp_path, repos=(X,))
    succ = h.new(tmp_path, repos=(Y,), after=pred)
    loose = h.new(tmp_path, repos=("/work/z",))
    for job_id in (pred, loose):
        h.run("close", job_id)
        _expire(h, job_id)
    h.lines.clear()
    assert h.run("prune") == 0
    assert h.lines == [loose]
    assert (h.root / "jobs" / pred).is_dir()
    assert rows(h)[succ]["after-state"] == "abandoned"


def test_done_when_5_prune_removes_the_predecessor_once_the_successor_has_ended(h, tmp_path):
    pred = h.new(tmp_path, repos=(X,))
    succ = h.new(tmp_path, repos=(Y,), after=pred)
    for job_id in (pred, succ):
        h.run("close", job_id)
        _expire(h, job_id)
    h.lines.clear()
    assert h.run("prune") == 0
    assert sorted(h.lines) == sorted([pred, succ])


# --- Done when 7 ---------------------------------------------------------------------------------------

def test_done_when_7_an_after_held_successor_holds_nothing_and_a_later_job_on_its_repository_is_approved(h, tmp_path):
    pred, _ = _needs_input_job(h, tmp_path)
    succ = h.new(tmp_path, repos=(Y,), after=pred)
    h.approve(succ)
    assert (rows(h)[succ]["state"], rows(h)[succ]["blocked-by"]) == ("held", [])
    later = h.new(tmp_path, repos=(Y,))
    h.approve(later)
    listed = rows(h)
    assert (listed[later]["state"], listed[later]["blocked-by"]) == ("approved", [])
    assert listed[succ]["state"] == "held" and listed[succ]["blocked-by"] == [later]


# --- Done when 8 and 10 --------------------------------------------------------------------------------

def walk(listed, job_id, repo):
    """The walk of ``skills/goal/job.md``, "Base per repository": the job whose branch is the base, or UNRESOLVED."""
    row = listed[job_id]
    while row["after"] is not None:
        if row["after-state"] in ("missing", "invalid"):
            return UNRESOLVED
        row = listed[row["after"]]
        if repo in row["resources"]:
            return row["id"]
    return None


def branch_of(h, job_id):
    return re.search(r"^branch: (.+)$", goal_file(h, job_id).read_text(encoding="utf-8"), re.M).group(1)


def stack(h, tmp_path):
    """P1 on A and B, P2 on A after P1, P3 on A after P2, S on B after P3."""
    a, b = "/work/a", "/work/b"
    p1 = h.new(tmp_path, slug="p1", repos=(a, b))
    p2 = h.new(tmp_path, slug="p2", repos=(a,), after=p1)
    p3 = h.new(tmp_path, slug="p3", repos=(a,), after=p2)
    s = h.new(tmp_path, slug="s", repos=(b,), after=p3)
    for job_id in (p1, p2, p3, s):
        goal_file(h, job_id).write_text(f"branch: feature/{job_id}\n", encoding="utf-8")
    return p1, p2, p3, s


def test_done_when_8_the_walk_from_s_reaches_p1_for_repository_b_and_p3_for_repository_a(h, tmp_path):
    p1, p2, p3, s = stack(h, tmp_path)
    listed = rows(h)
    assert [listed[j]["after"] for j in (p1, p2, p3, s)] == [None, p1, p2, p3]
    assert walk(listed, s, "/work/b") == p1
    assert branch_of(h, walk(listed, s, "/work/b")) == f"feature/{p1}"
    assert walk(listed, s, "/work/a") == p3
    assert branch_of(h, walk(listed, s, "/work/a")) == f"feature/{p3}"


def test_done_when_8_the_walk_ends_with_no_base_when_no_job_on_the_chain_changes_the_repository(h, tmp_path):
    _, _, _, s = stack(h, tmp_path)
    assert walk(rows(h), s, "/work/other") is None


def test_done_when_10_the_walk_stops_unresolved_at_a_row_with_after_state_missing(h, tmp_path):
    p1, p2, _, s = stack(h, tmp_path)
    remove_dir(h, p1)
    listed = rows(h)
    assert listed[p2]["after-state"] == "missing"
    assert walk(listed, s, "/work/b") == UNRESOLVED
    assert walk(listed, s, "/work/a") == listed[s]["after"]


def test_done_when_10_the_walk_stops_unresolved_at_a_row_with_after_state_invalid(h, tmp_path):
    p1, _, _, s = stack(h, tmp_path)
    corrupt(h, p1)
    listed = rows(h)
    assert listed[p1]["state"] == "invalid"
    assert walk(listed, s, "/work/b") == UNRESOLVED


# --- Done when 11 --------------------------------------------------------------------------------------

def _closing(h, tmp_path, make_gone):
    pred = h.new(tmp_path, repos=(X,))
    h.approve(pred)
    succ = h.new(tmp_path, repos=(Y,), after=pred)
    h.approve(succ)
    make_gone(pred)
    return pred, succ


def _fail(h):
    def apply(pred):
        assert h.run("launch", pred) == 0
        result_file(h, pred).write_text(FAILED_RESULT, encoding="utf-8")
    return apply


@pytest.mark.parametrize("state, make_gone", [
    ("failed", lambda h: _fail(h)),
    ("abandoned", lambda h: (lambda pred: h.run("close", pred))),
    ("missing", lambda h: (lambda pred: remove_dir(h, pred))),
])
def test_done_when_11_next_closes_an_approved_successor_whose_predecessor_is_gone_and_does_not_launch_it(
        h, tmp_path, state, make_gone):
    pred, succ = _closing(h, tmp_path, make_gone(h))
    row = next_actions(h)[succ]
    assert row["state"] == "held"
    assert row["actions"] == ["close-successor"]
    assert row["args"] == {"close-successor": {"after": pred, "after-state": state}}


def test_done_when_11_next_gives_no_action_for_the_successor_of_an_invalid_predecessor(h, tmp_path):
    pred, succ = _closing(h, tmp_path, lambda pred: corrupt(h, pred))
    found = next_actions(h)
    assert succ not in found
    assert found[pred]["actions"] == ["repair"]
