"""Review round 1 (R1-C1, C3, C4, C5, D2, D3): writer round trip, lock order, invalid jobs, launch edges."""
from __future__ import annotations

import json
import sys
from datetime import timedelta

import pytest

from cure_job.claude import ClaudeCli
from cure_job.cli import Cli
from cure_job.frontmatter import is_writable, parse, render
from cure_job.result import ResultStatus, parse_result
from tests.builders import NOW, handoff_text, set_age
from tests.fakes import FakeClaude, FakeClock

REPO = "/work/video-core"
OTHER = "/work/other"
OLD_ROOT = "/x/plugins/cache/zagrichanskiy/cure/0.18.0"


class Harness:
    def __init__(self, root, claude=None, **kwargs):
        self.root = root
        self.claude = claude or FakeClaude()
        self.clock = FakeClock(NOW)
        self.lines: list[str] = []
        self.cli = Cli(root=root, claude=self.claude, clock=self.clock, out=self.lines.append, **kwargs)

    def run(self, *argv) -> int:
        self.lines.clear()
        return self.cli.run(list(argv))

    def new(self, tmp_path, repo=REPO, slug="x", goal=True, at=None) -> str:
        self.clock.now = at or self.clock.now + timedelta(minutes=1)
        source = tmp_path / "handoff.md"
        source.write_text(handoff_text((repo,)), encoding="utf-8")
        assert self.run("new", "--slug", slug, str(source)) == 0
        job_id = self.lines[0]
        if goal:
            self.goal(job_id).write_text("goal", encoding="utf-8")
        return job_id

    def goal(self, job_id):
        return self.root / "jobs" / job_id / "goal.md"

    def listed(self) -> dict[str, dict]:
        assert self.run("list", "--json") == 0
        return {entry["id"]: entry for entry in json.loads(self.lines[0])}


@pytest.fixture
def h(root):
    return Harness(root)


# --- R1-C3: the writer and the parser agree -------------------------------------------------------------

AWKWARD = ['say "hi"', "it's", "[a, b]", "a, b", "# not a comment", "---", "key: value", "https://example.com/pr/1",
           "/abs/path/to/file.md", "- leading dash", "'quoted'", "x [y]"]


@pytest.mark.parametrize("text", AWKWARD)
def test_render_round_trips_a_scalar_and_a_block_list_item(text):
    assert is_writable(text)
    assert parse(render({"status": "done", "retro": text, "kept": [text, "plain"]})) == {
        "status": "done", "retro": text, "kept": [text, "plain"]}


@pytest.mark.parametrize("text", ["", " padded", "two\nlines", "tail ", "a b"])
def test_is_writable_refuses_empty_padded_and_multiline_text(text):
    assert not is_writable(text)


def test_finish_writes_retro_kept_and_pr_that_parse_back(h, tmp_path):
    job_id = h.new(tmp_path)
    assert h.run("launch", job_id) == 0
    retro = tmp_path / "my retro, v2 [draft].md"
    assert h.run("finish", job_id, "--status", "done", "--retro", str(retro), "--pr", "https://example.com/pr/7#x",
                 "--kept", "/a/one.md", "--kept", "/b/two, three.md") == 0
    entries = parse((h.root / "jobs" / job_id / "result.md").read_text(encoding="utf-8"))
    assert entries["retro"] == str(retro)
    assert entries["pr"] == "https://example.com/pr/7#x"
    assert entries["kept"] == ["/a/one.md", "/b/two, three.md"]
    assert parse_result((h.root / "jobs" / job_id / "result.md").read_text(encoding="utf-8")).status is ResultStatus.DONE


# --- R1-C1: lock order after a backward clock step ------------------------------------------------------

def test_launched_job_with_a_higher_id_holds_the_resource_against_a_lower_unlaunched_one(h, tmp_path):
    high = h.new(tmp_path)
    assert h.run("launch", high) == 0
    low = h.new(tmp_path, at=NOW - timedelta(hours=1))
    assert low < high
    listed = h.listed()
    assert listed[low]["blocked-by"] == [high]
    assert listed[high]["blocked-by"] == []
    h.claude.started.clear()
    assert h.run("launch", low) == 1
    assert h.claude.started == []


# --- R2-C1: a launched job may claim a resource that a lower-id unlaunched job names --------------------

def test_launched_job_may_claim_a_resource_named_by_a_lower_unlaunched_job(h, tmp_path):
    low = h.new(tmp_path, repo=OTHER)
    (h.root / "jobs" / low / "handoff.md").write_text(handoff_text((OTHER,), device="bench"), encoding="utf-8")
    high = h.new(tmp_path)
    assert h.run("launch", high) == 0
    assert h.run("claim", high, "device:bench") == 0
    listed = h.listed()
    assert listed[low]["blocked-by"] == [high]
    assert listed[high]["blocked-by"] == []


# --- R1-D2: one invalid job does not take the others down -----------------------------------------------

def _break(h, job_id, how):
    directory = h.root / "jobs" / job_id
    if how == "handoff":
        (directory / "handoff.md").write_text("not frontmatter\n", encoding="utf-8")
    else:
        (directory / "dispatch.jsonl").write_text("{not json\n", encoding="utf-8")


@pytest.fixture(params=["handoff", "events"])
def broken(request, h, tmp_path):
    first = h.new(tmp_path, repo=OTHER, goal=False)
    bad = h.new(tmp_path, repo=OTHER, goal=False)
    later = h.new(tmp_path, repo=REPO)
    _break(h, bad, request.param)
    return h, first, bad, later


def test_list_shows_the_invalid_job_and_still_lists_the_others(broken):
    h, first, bad, later = broken
    listed = h.listed()
    assert listed[bad]["state"] == "invalid"
    assert listed[first]["state"] == "queued"
    assert listed[later]["state"] == "awaiting-approval"


def test_prune_skips_an_invalid_job(broken):
    h, _, bad, _ = broken
    set_age(h.root / "jobs" / bad, NOW + timedelta(days=100), timedelta(days=60))
    h.clock.advance(timedelta(days=100))
    assert h.run("prune") == 0
    assert (h.root / "jobs" / bad).is_dir()


@pytest.mark.parametrize("which", ["first", "later"])
def test_launch_and_claim_are_refused_while_any_job_is_invalid(broken, which):
    h, first, _, later = broken
    # The invalid job's resources are unknown, so it may hold any resource, whatever its id.
    target = {"first": first, "later": later}[which]
    h.goal(target).write_text("goal", encoding="utf-8")
    assert h.run("launch", target) == 1
    assert h.run("claim", target, "device:bench") == 1
    assert h.claude.started == []


# --- R1-D3: a start that times out may have left a live session ----------------------------------------

def test_launch_that_times_out_leaves_a_launched_job_with_an_event(root, tmp_path, monkeypatch):
    slow = tmp_path / "slow-claude"
    slow.write_text(f"#!{sys.executable}\nimport sys, time\n"
                    "if sys.argv[1] == '--bg':\n    time.sleep(30)\nprint('[]')\n", encoding="utf-8")
    slow.chmod(0o755)
    monkeypatch.setattr(ClaudeCli, "TIMEOUT_SECONDS", 0.5)
    h = Harness(root, claude=ClaudeCli(str(slow)))
    workdir = tmp_path / "work" / "proj"
    workdir.mkdir(parents=True)
    job_id = h.new(tmp_path, repo=str(workdir))
    assert h.run("launch", job_id) == 1
    assert '"launched"' in (root / "jobs" / job_id / "dispatch.jsonl").read_text(encoding="utf-8")
    assert h.listed()[job_id]["state"] == "launched"


# --- R1-C4: a slug may not mimic a session suffix ------------------------------------------------------

def test_new_refuses_a_slug_that_ends_in_a_run_suffix(h, tmp_path):
    source = tmp_path / "handoff.md"
    source.write_text(handoff_text((REPO,)), encoding="utf-8")
    with pytest.raises(SystemExit) as caught:
        h.run("new", "--slug", "fix r2", str(source))
    assert caught.value.code == 2
    assert not (h.root / "jobs").exists() or not list((h.root / "jobs").iterdir())


# --- R1-C5: goal files name the current plugin root ----------------------------------------------------

def plugin_with_rules(path):
    """A plugin root that holds the goal rules file, which ``launch`` requires."""
    (path / "skills" / "goal").mkdir(parents=True)
    (path / "skills" / "goal" / "rules.md").write_text("rules", encoding="utf-8")
    return path


def test_launch_rewrites_a_versioned_cure_job_path_to_the_current_plugin_root(root, tmp_path):
    current = plugin_with_rules(tmp_path / "plugin" / "0.19.0")
    h = Harness(root, plugin_root=current)
    job_id = h.new(tmp_path)
    h.goal(job_id).write_text(f"run {OLD_ROOT}/bin/cure-job finish\nand {OLD_ROOT}/bin/cure-job claim\n",
                              encoding="utf-8")
    assert h.run("launch", job_id) == 0
    assert h.goal(job_id).read_text(encoding="utf-8") == (
        f"run {current}/bin/cure-job finish\nand {current}/bin/cure-job claim\n")


def test_launch_leaves_a_goal_without_a_plugin_path_unchanged(root, tmp_path):
    h = Harness(root, plugin_root=plugin_with_rules(tmp_path / "plugin" / "0.19.0"))
    job_id = h.new(tmp_path)
    text = "do the work\nsee /home/u/other/bin/cure-job-notes\n"
    h.goal(job_id).write_text(text, encoding="utf-8")
    assert h.run("launch", job_id) == 0
    assert h.goal(job_id).read_text(encoding="utf-8") == text
