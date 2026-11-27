"""The job ledger: the transcript reader, the job record, and the ledger of ``finish`` and ``prune``."""
from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest

from cure_job import ledger, worktree
from cure_job.ledger import Usage
from cure_job.providers.jobs import JobsProvider
from cure_job.result import Report, ResultStatus
from cure_job.store import JobStore
from tests.builders import handoff_text
from tests.fakes import FakeClaude, FakeClock
from tests.test_finish import LOCAL
from tests.test_worktrees import git, make_repo

KEYS = ("input", "output", "cache_creation", "cache_read")


@pytest.fixture(autouse=True)
def fake_git():
    """These tests run real git."""


def line(msg_id, input=0, output=0, creation=0, read=0, kind="assistant", **extra):
    usage = {"input_tokens": input, "output_tokens": output, "cache_creation_input_tokens": creation,
             "cache_read_input_tokens": read, **extra}
    return json.dumps({"type": kind, "message": {"id": msg_id, "usage": usage}})


def write(path: Path, *lines: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# --- reader ------------------------------------------------------------------------------------------

def test_reader_sums_each_token_type_separately_and_counts_turns(tmp_path):
    path = write(tmp_path / "s.jsonl", line("a", 1, 10, 100, 1000), line("b", 2, 20, 200, 2000),
                 line("u", 99, 99, 99, 99, kind="user"))
    assert ledger.read_usage([path]) == Usage(3, 30, 300, 3000, 2)


def test_reader_counts_a_streamed_message_once_with_its_last_usage(tmp_path):
    path = write(tmp_path / "s.jsonl", line("a", 1, 5, 100, 1000), line("a", 1, 40, 100, 1000), line("b", 2, 7))
    assert ledger.read_usage([path]) == Usage(3, 47, 100, 1000, 2)


def test_reader_gives_none_for_a_type_no_line_carries_and_never_zero(tmp_path):
    path = write(tmp_path / "s.jsonl", json.dumps({"type": "assistant", "message": {"id": "a",
                 "usage": {"input_tokens": 4, "output_tokens": 0}}}))
    assert ledger.read_usage([path]) == Usage(4, 0, None, None, 1)


def test_reader_gives_none_everywhere_without_a_transcript(tmp_path):
    assert ledger.read_usage([]) == Usage(None, None, None, None, None)
    assert ledger.read_usage([tmp_path / "missing.jsonl"]) == Usage(None, None, None, None, None)


def test_reader_skips_a_sidechain_line(tmp_path):
    side = json.dumps({"type": "assistant", "isSidechain": True, "message": {"id": "s", "usage": {"input_tokens": 9}}})
    assert ledger.read_usage([write(tmp_path / "s.jsonl", side, line("a", 1))]) == Usage(1, 0, 0, 0, 1)


def test_reader_skips_a_line_that_is_not_json(tmp_path):
    path = write(tmp_path / "s.jsonl", "{broken", line("a", 1, 2, 3, 4))
    assert ledger.read_usage([path]) == Usage(1, 2, 3, 4, 1)


def test_locate_finds_the_main_transcript_in_any_project_directory_and_its_subagents(tmp_path):
    main = write(tmp_path / "-work-repo" / "uuid-1.jsonl", line("a", 1))
    subs = [write(tmp_path / "-work-repo" / "uuid-1" / "subagents" / f"agent-{n}.jsonl", line(f"s{n}", 1))
            for n in (1, 2)]
    write(tmp_path / "-work-repo" / "uuid-2.jsonl", line("z", 1))
    found, found_subs = ledger.locate(tmp_path, "uuid-1")
    assert found == main and sorted(found_subs) == subs
    assert ledger.locate(tmp_path, "uuid-9") == (None, ())


# --- record ------------------------------------------------------------------------------------------

def test_record_keeps_orchestrator_and_subagent_tokens_apart_and_has_no_rounds():
    record = ledger.job_record(job_id="261001-0900-video-core-x", date="2026-10-14", repo="video-core", slug="x",
                               tier="Light", outcome="done", est_lines=400, lines={"/work/video-core": 42},
                               orchestrator=Usage(1, 2, 3, 4, 5), subagents=Usage(10, 20, None, 40, 6))
    assert record["job"] == "261001-0900-video-core-x" and record["turns"] == 5
    assert record["orchestrator_tokens"] == dict(zip(KEYS, (1, 2, 3, 4)))
    assert record["subagent_tokens"] == dict(zip(KEYS, (10, 20, None, 40)))
    assert record["lines"] == {"/work/video-core": 42} and "rounds" not in record
    assert {"date", "repo", "slug", "tier", "outcome", "est_lines"} <= record.keys()


def test_append_adds_a_line_and_never_truncates(tmp_path):
    path = tmp_path / "ledger.jsonl"
    ledger.append(path, {"n": 1})
    ledger.append(path, {"n": 2})
    assert [json.loads(text) for text in path.read_text(encoding="utf-8").splitlines()] == [{"n": 1}, {"n": 2}]


@pytest.mark.parametrize("text, expected", [("- Estimate: ~400 changed lines\n", 400), ("- Scope only\n", None)])
def test_est_lines_reads_the_settled_estimate_line(text, expected):
    assert ledger.est_lines("## Settled\n\n" + text) == expected


def test_changed_lines_sums_insertions_and_deletions_against_the_base(tmp_path):
    repo = make_repo(tmp_path, "r")
    (repo / "a.txt").write_text("1\n2\n3\n", encoding="utf-8")
    git(repo, "add", "."); git(repo, "commit", "-qm", "a")
    base = git(repo, "rev-parse", "HEAD")
    (repo / "a.txt").write_text("1\nX\n3\n4\n", encoding="utf-8")
    git(repo, "commit", "-qam", "b")
    assert worktree.Git().changed_lines(repo, base) == 3


# --- finish and prune --------------------------------------------------------------------------------

@pytest.fixture
def world(tmp_path):
    store, claude, clock = JobStore(tmp_path / "state"), FakeClaude(), FakeClock(LOCAL)
    projects = tmp_path / "projects"
    jobs = JobsProvider(store, claude, clock, projects_root=projects)
    repo = str(make_repo(tmp_path / "src", "video-core"))
    return jobs, store, clock, projects, repo


def launched(world, estimate=True):
    jobs, store, clock, projects, repo = world
    clock.advance(timedelta(minutes=1))
    text = handoff_text((repo,)) + ("## Settled\n\n- Estimate: ~400 changed lines\n" if estimate else "")
    job_id = jobs.new(text, "x")
    store.goal_path(job_id).write_text("## Rules\n\n- Tier: Light\n", encoding="utf-8")
    jobs.approve(job_id)
    jobs.launch(job_id)
    return job_id


def records(store, job_id):
    text = store.job_dir(job_id).joinpath("ledger.jsonl").read_text(encoding="utf-8")
    return [json.loads(row) for row in text.splitlines()]


def test_finish_appends_one_job_record_with_tokens_lines_tier_and_estimate(world):
    jobs, store, clock, projects, repo = world
    job_id = launched(world)
    uuid = jobs.claude.sessions()[store.load(job_id).session].uuid
    write(projects / "-any" / f"{uuid}.jsonl", line("a", 1, 2, 3, 4), line("b", 1, 2, 3, 4))
    write(projects / "-any" / uuid / "subagents" / "agent-1.jsonl", line("s", 5, 6, 7, 8))
    worktree = Path(store.load(job_id).worktree_root) / "video-core" / job_id
    (worktree / "f.txt").write_text("a\nb\n", encoding="utf-8")
    git(worktree, "add", "."); git(worktree, "commit", "-qm", "work")
    jobs.finish(job_id, Report(ResultStatus.DONE))
    [record] = records(store, job_id)
    assert record["job"] == job_id and record["repo"] == "video-core" and record["slug"] == "x"
    assert (record["tier"], record["outcome"], record["est_lines"]) == ("Light", "done", 400)
    assert record["date"].startswith("2026-10-14") and record["lines"] == {repo: 2} and record["turns"] == 2
    assert record["orchestrator_tokens"] == dict(zip(KEYS, (2, 4, 6, 8)))
    assert record["subagent_tokens"] == dict(zip(KEYS, (5, 6, 7, 8)))
    assert "rounds" not in record


def test_finish_records_the_slug_of_a_ticket_job_id(world):
    jobs, store, clock, projects, repo = world
    job_id = jobs.new(handoff_text((repo,)).replace("device: none", "device: none\nticket: ABC-1"), "fix-it")
    assert job_id == "abc-1-video-core-fix-it"
    store.goal_path(job_id).write_text("## Rules\n\n- Tier: Light\n", encoding="utf-8")
    jobs.approve(job_id)
    jobs.launch(job_id)
    jobs.finish(job_id, Report(ResultStatus.DONE))
    assert records(store, job_id)[0]["slug"] == "fix-it"


def test_finish_records_the_slug_of_a_job_id_whose_repository_was_cut(world, tmp_path):
    jobs, store, *_ = world
    repo = str(make_repo(tmp_path / "src", "video-core-firmware-images-and-more"))
    text = handoff_text((repo,)).replace("device: none", "device: none\nticket: ABC-1")
    job_id = jobs.new(text, "report-pass-from-signal-and-more")
    assert job_id == "abc-1-video-core-firmware-images-report-pass-from-signal-an"
    store.goal_path(job_id).write_text("## Rules\n\n- Tier: Light\n", encoding="utf-8")
    jobs.approve(job_id)
    jobs.launch(job_id)
    jobs.finish(job_id, Report(ResultStatus.DONE))
    assert records(store, job_id)[0]["slug"] == "report-pass-from-signal-an"


def test_finish_without_transcript_or_estimate_records_null_never_zero(world):
    jobs, store, *_ = world
    job_id = launched(world, estimate=False)
    jobs.finish(job_id, Report(ResultStatus.FAILED))
    [record] = records(store, job_id)
    assert record["est_lines"] is None and record["turns"] is None and record["outcome"] == "failed"
    assert record["orchestrator_tokens"] == dict.fromkeys(KEYS)
    assert record["subagent_tokens"] == dict.fromkeys(KEYS)


def test_a_refused_second_finish_leaves_the_first_record_in_place(world):
    jobs, store, *_ = world
    job_id = launched(world)
    jobs.finish(job_id, Report(ResultStatus.DONE))
    with pytest.raises(Exception):
        jobs.finish(job_id, Report(ResultStatus.DONE))
    assert len(records(store, job_id)) == 1


def test_prune_keeps_the_ledger_of_a_removed_job_outside_its_directory(world):
    jobs, store, *_ = world
    job_id = launched(world, estimate=False)
    jobs.finish(job_id, Report(ResultStatus.DONE))
    before = store.job_dir(job_id).joinpath("ledger.jsonl").read_text(encoding="utf-8")
    jobs.mark_reported(job_id)
    jobs.remove_sessions(job_id)
    assert jobs.prune() == [job_id]
    kept = store.root / "ledgers" / f"{job_id}.jsonl"
    assert not store.job_dir(job_id).exists() and store.kept_ledger_path(job_id) == kept
    assert kept.read_text(encoding="utf-8") == before


def test_prune_appends_to_a_kept_ledger_it_finds_and_never_truncates(world):
    jobs, store, *_ = world
    job_id = launched(world, estimate=False)
    jobs.finish(job_id, Report(ResultStatus.DONE))
    kept = store.kept_ledger_path(job_id)
    kept.parent.mkdir(parents=True)
    kept.write_text('{"earlier": true}\n', encoding="utf-8")
    jobs.mark_reported(job_id)
    jobs.remove_sessions(job_id)
    jobs.prune()
    rows = kept.read_text(encoding="utf-8").splitlines()
    assert json.loads(rows[0]) == {"earlier": True} and len(rows) == 2


def commit_file(repo, name, text):
    (Path(repo) / name).write_text(text, encoding="utf-8")
    git(Path(repo), "add", "."); git(Path(repo), "commit", "-qm", name)


def test_lines_count_from_the_recorded_start_commit_when_the_source_head_differs(world):
    jobs, store, clock, projects, repo = world
    git(Path(repo), "switch", "-qc", "predecessor")
    commit_file(repo, "p.txt", "1\n2\n3\n4\n5\n")
    job_id = launched(world)
    git(Path(repo), "switch", "-q", "main")
    commit_file(Path(store.load(job_id).worktree_root) / "video-core" / job_id, "f.txt", "a\nb\n")
    jobs.finish(job_id, Report(ResultStatus.DONE))
    assert records(store, job_id)[0]["lines"] == {repo: 2}


def test_lines_are_keyed_by_the_handoff_repository_path(world):
    jobs, store, clock, projects, repo = world
    (Path(repo) / "sub").mkdir()
    commit_file(repo, "sub/s.txt", "1\n")
    job_id = launched((jobs, store, clock, projects, str(Path(repo) / "sub")))
    jobs.finish(job_id, Report(ResultStatus.DONE))
    assert records(store, job_id)[0]["lines"] == {str(Path(repo) / "sub"): 0}


def test_a_prune_retry_does_not_append_a_ledger_the_kept_file_already_ends_with(world):
    jobs, store, *_ = world
    job_id = launched(world, estimate=False)
    jobs.finish(job_id, Report(ResultStatus.DONE))
    kept = store.kept_ledger_path(job_id)
    kept.parent.mkdir(parents=True)
    before = '{"earlier": true}\n' + store.ledger_path(job_id).read_text(encoding="utf-8")
    kept.write_text(before, encoding="utf-8")
    jobs.mark_reported(job_id)
    jobs.remove_sessions(job_id)
    assert jobs.prune() == [job_id]
    assert kept.read_text(encoding="utf-8") == before


def test_a_repository_without_a_recorded_start_commit_has_null_lines(world):
    jobs, store, *_, repo = world
    job_id = launched(world)
    events = store.job_dir(job_id) / "dispatch.jsonl"
    rows = events.read_text(encoding="utf-8").splitlines(keepends=True)
    events.write_text("".join(row for row in rows if "checkout-started" not in row), encoding="utf-8")
    jobs.finish(job_id, Report(ResultStatus.DONE))
    assert records(store, job_id)[0]["lines"] == {repo: None}


def test_a_job_with_two_checkout_starts_for_one_repository_counts_lines_from_the_last(world):
    jobs, store, *_, repo = world
    job_id = launched(world)
    tree = Path(store.load(job_id).worktree_root) / "video-core" / job_id
    commit_file(tree, "earlier.txt", "1\n2\n3\n4\n5\n")
    row = json.dumps({"event": "checkout-started", "repo": repo, "commit": git(tree, "rev-parse", "HEAD")})
    with (store.job_dir(job_id) / "dispatch.jsonl").open("a", encoding="utf-8") as events:
        events.write(row + "\n")
    commit_file(tree, "f.txt", "a\nb\n")
    jobs.finish(job_id, Report(ResultStatus.DONE))
    assert records(store, job_id)[0]["lines"] == {repo: 2}


def test_each_finish_records_the_totals_so_far_so_the_last_record_covers_every_run(world):
    jobs, store, clock, projects, repo = world
    job_id = launched(world)
    uuid = jobs.claude.sessions()[store.load(job_id).session].uuid
    transcript = write(projects / "-any" / f"{uuid}.jsonl", line("a", 1, 2, 3, 4))
    jobs.finish(job_id, Report(ResultStatus.NEEDS_INPUT, questions=("q",)))
    jobs.resume(job_id)
    write(transcript, line("a", 1, 2, 3, 4), line("b", 1, 2, 3, 4))
    jobs.finish(job_id, Report(ResultStatus.DONE))
    first, second = records(store, job_id)
    assert (first["outcome"], first["turns"], second["outcome"], second["turns"]) == ("needs-input", 1, "done", 2)
    assert second["orchestrator_tokens"] == dict(zip(KEYS, (2, 4, 6, 8)))


def test_prune_starts_a_new_line_after_a_kept_ledger_cut_off_mid_line(world):
    jobs, store, *_ = world
    job_id = launched(world, estimate=False)
    jobs.finish(job_id, Report(ResultStatus.DONE))
    kept = store.kept_ledger_path(job_id)
    kept.parent.mkdir(parents=True)
    kept.write_text('{"cut": tru', encoding="utf-8")
    jobs.mark_reported(job_id)
    jobs.remove_sessions(job_id)
    jobs.prune()
    rows = kept.read_text(encoding="utf-8").splitlines()
    assert rows[0] == '{"cut": tru' and json.loads(rows[1])["job"] == job_id
