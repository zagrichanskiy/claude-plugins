"""``cure-job stats``: per repository and tier, the job count and the medians over current and kept ledgers.

Output: one header line, then one line per (repo, tier), whitespace-separated columns
``repo tier jobs input output cache_creation cache_read turns lines``; a column without a value prints ``-``.
Token columns are the orchestrator and subagent tokens of a job added.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from cure_job.cli import Cli
from tests.fakes import FakeClaude, FakeClock

KEYS = ("input", "output", "cache_creation", "cache_read")


def record(job, repo="video-core", tier="Light", tokens=(1, 1, 1, 1), turns=1, lines=1):
    orchestrator = dict(zip(KEYS, tokens)) if tokens is not None else dict.fromkeys(KEYS)
    return {"job": job, "date": "2026-10-14", "repo": repo, "slug": "x", "tier": tier, "outcome": "done",
            "est_lines": None, "lines": {f"/work/{repo}": lines}, "turns": turns,
            "orchestrator_tokens": orchestrator, "subagent_tokens": dict.fromkeys(KEYS)}


def write_ledger(path, *records):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in records), encoding="utf-8")


def current(root, *records):
    write_ledger(root / "jobs" / records[0]["job"] / "ledger.jsonl", *records)


def kept(root, *records):
    write_ledger(root / "ledgers" / f"{records[0]['job']}.jsonl", *records)


@pytest.fixture
def stats(root):
    def run(*argv):
        lines = []
        cli = Cli(root=root, config_path=root / "config.json", claude=FakeClaude(),
                  clock=FakeClock(datetime(2026, 10, 14, tzinfo=timezone.utc)), out=lines.append)
        assert cli.run(["stats", *argv]) == 0
        rows = [line.split() for line in lines]
        return {tuple(row[:2]): row[2:] for row in rows[1:]}
    return run


def test_medians_per_repo_and_tier_over_several_ledgers(root, stats):
    for job, n in (("a", 1), ("b", 3), ("c", 20)):
        current(root, record(job, tokens=(n, n * 10, n * 100, n * 1000), turns=n * 2, lines=n * 5))
    current(root, record("d", tier="Heavy", tokens=(7, 8, 9, 10), turns=11, lines=12))
    current(root, record("e", repo="other", tokens=(4, 4, 4, 4), turns=4, lines=4))
    table = stats()
    assert table[("video-core", "Light")] == ["3", "3", "30", "300", "3000", "6", "15"]
    assert table[("video-core", "Heavy")] == ["1", "7", "8", "9", "10", "11", "12"]
    assert table[("other", "Light")] == ["1", "4", "4", "4", "4", "4", "4"]


def test_null_values_are_left_out_of_a_median_and_an_all_null_column_prints_a_dash(root, stats):
    current(root, record("a", tokens=(2, 5, None, None), turns=None, lines=None))
    current(root, record("b", tokens=(4, None, None, None), turns=8, lines=None))
    current(root, record("c", tokens=(None, 9, None, None), turns=None, lines=None))
    assert stats()[("video-core", "Light")] == ["3", "3", "7", "-", "-", "8", "-"]


def test_a_kept_ledger_of_a_pruned_job_is_counted_with_the_current_jobs(root, stats):
    current(root, record("a", tokens=(1, 1, 1, 1)))
    kept(root, record("b", tokens=(5, 5, 5, 5)))
    kept(root, record("c", tokens=(9, 9, 9, 9)))
    assert stats()[("video-core", "Light")][:2] == ["3", "5"]


def test_repo_narrows_the_output_to_one_repository(root, stats):
    current(root, record("a"))
    kept(root, record("b", repo="other"))
    assert list(stats("--repo", "other")) == [("other", "Light")]
    assert list(stats("--repo", "video-core")) == [("video-core", "Light")]


def test_a_job_with_several_records_is_counted_once_by_its_last(root, stats):
    current(root, record("a", turns=1), record("a", turns=9))
    row = stats()[("video-core", "Light")]
    assert (row[0], row[5]) == ("1", "9")


def test_a_job_with_a_kept_and_a_current_ledger_is_counted_once_by_the_current(root, stats):
    kept(root, record("a", turns=2))
    current(root, record("a", turns=6))
    row = stats()[("video-core", "Light")]
    assert (row[0], row[5]) == ("1", "6")


def test_tokens_add_orchestrator_and_subagent_and_lines_add_repositories(root, stats):
    row = record("a", tokens=(1, 2, None, None), lines=3)
    row["subagent_tokens"] = {"input": 10, "output": None, "cache_creation": 5, "cache_read": None}
    row["lines"]["/work/other"] = 4
    current(root, row)
    assert stats()[("video-core", "Light")] == ["1", "11", "2", "5", "-", "1", "7"]


def test_a_truncated_last_line_is_skipped_and_the_other_records_are_counted(root, stats):
    current(root, record("a"))
    path = root / "jobs" / "b" / "ledger.jsonl"
    write_ledger(path, record("b"))
    with path.open("a", encoding="utf-8") as handle:
        handle.write('{"job": "b", "tu')
    assert stats()[("video-core", "Light")][0] == "2"
