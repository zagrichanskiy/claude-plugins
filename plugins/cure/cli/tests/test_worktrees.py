"""Issue 119: every job runs in its own git worktree under ``worktree.root``."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from cure_job.claude import SessionStatus
from cure_job.config import DEFAULTS
from tests.test_approve import DONE_RESULT, NEEDS_INPUT_RESULT, rows
from tests.test_cli import Harness
from tests.test_config import configure


def git(cwd: Path, *args: str) -> str:
    done = subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
                          cwd=cwd, check=True, capture_output=True, text=True)
    return done.stdout.strip()


def make_repo(parent: Path, name: str) -> Path:
    repo = parent / name
    repo.mkdir(parents=True)
    git(repo, "init", "-q", "-b", "main")
    git(repo, "commit", "-q", "--allow-empty", "-m", "base")
    return repo


@pytest.fixture(autouse=True)
def fake_git():
    """These tests run real git."""


@pytest.fixture
def h(root):
    return Harness(root)


@pytest.fixture
def worktrees(h, tmp_path) -> Path:
    path = tmp_path / "worktrees"
    configure(h, {"worktree": {"root": str(path)}})
    return path


@pytest.fixture
def repo(tmp_path) -> Path:
    return make_repo(tmp_path / "src", "video-core")


def launch(h, tmp_path, repos, **fields) -> str:
    job_id = h.new(tmp_path, repos=tuple(str(r) for r in repos), **fields)
    h.approve(job_id)
    assert h.run("launch", job_id) == 0
    return job_id


def session_cwd(h) -> Path:
    return Path(h.claude.started[-1][1])


def test_worktree_root_defaults_to_the_yocto_worktrees_directory(h):
    assert DEFAULTS["worktree.root"] == "~/work/yocto/worktrees"
    assert h.run("config", "get", "worktree.root") == 0
    assert h.lines == ['"~/work/yocto/worktrees"']


def test_the_default_root_expands_the_home_directory(h, tmp_path, repo):
    job_id = launch(h, tmp_path, [repo], branch="feat")
    assert session_cwd(h) == tmp_path / "home" / "work" / "yocto" / "worktrees" / "video-core" / job_id


def test_launch_runs_the_session_in_a_worktree_detached_at_the_repository_head(h, tmp_path, repo, worktrees):
    job_id = launch(h, tmp_path, [repo], branch="feat-a")
    cwd = session_cwd(h)
    assert cwd == worktrees / "video-core" / job_id
    assert git(cwd, "rev-parse", "--abbrev-ref", "HEAD") == "HEAD"
    assert git(cwd, "rev-parse", "HEAD") == git(repo, "rev-parse", "HEAD")
    assert git(repo, "rev-parse", "--abbrev-ref", "HEAD") == "main"


def test_the_worktree_is_named_after_the_toplevel_and_the_session_starts_in_the_subdirectory(h, tmp_path, repo, worktrees):
    (repo / "sub").mkdir()
    (repo / "sub" / "f").write_text("x", encoding="utf-8")
    git(repo, "add", "sub")
    git(repo, "commit", "-q", "-m", "sub")
    job_id = launch(h, tmp_path, [repo / "sub"], branch="feat-a")
    assert session_cwd(h) == worktrees / "video-core" / job_id / "sub"
    assert session_cwd(h).is_dir()


@pytest.mark.parametrize("value", ["relative/worktrees", 5])
def test_a_worktree_root_that_is_not_an_absolute_path_is_a_config_problem(h, value, capsys):
    configure(h, {"worktree": {"root": value}})
    assert h.run("config", "check") == 1
    assert "worktree.root: expected an absolute path" in capsys.readouterr().err


def test_a_relaunch_whose_worktree_add_fails_records_no_run_and_archives_no_result(h, tmp_path, repo, worktrees):
    job_id = launch(h, tmp_path, [repo])
    path = session_cwd(h)
    git(repo, "worktree", "remove", str(path))
    path.write_text("in the way", encoding="utf-8")
    job_dir = h.root / "jobs" / job_id
    (job_dir / "result.md").write_text(NEEDS_INPUT_RESULT, encoding="utf-8")
    del h.claude.statuses[job_id]
    assert h.run("launch", job_id) == 1
    assert h.cli.jobs.store.load(job_id).run == 1
    assert (job_dir / "result.md").is_file() and not (job_dir / "result-1.md").exists()


def test_two_repositories_with_one_basename_are_refused(h, tmp_path, worktrees, capsys):
    first, second = make_repo(tmp_path / "a", "video-core"), make_repo(tmp_path / "b", "video-core")
    job_id = h.new(tmp_path, repos=(str(first), str(second)))
    h.approve(job_id)
    assert h.run("launch", job_id) == 1
    assert "has the worktree" in capsys.readouterr().err


def test_prune_uses_the_worktree_root_recorded_at_the_first_launch(h, tmp_path, repo, worktrees):
    job_id, path = finished(h, tmp_path, repo)
    configure(h, {"worktree": {"root": str(tmp_path / "moved")}})
    assert h.run("prune") == 0
    assert not path.exists()


def test_launch_creates_one_worktree_per_repository_and_starts_in_the_first(h, tmp_path, repo, worktrees):
    other = make_repo(tmp_path / "src", "meta-layer")
    job_id = launch(h, tmp_path, [other, repo], branch="feat-a")
    assert session_cwd(h) == worktrees / "meta-layer" / job_id
    assert (worktrees / "video-core" / job_id).is_dir()


def test_two_jobs_on_one_repository_both_launch_in_their_own_worktrees(h, tmp_path, repo, worktrees):
    first = launch(h, tmp_path, [repo], branch="feat-a", slug="a")
    first_cwd = session_cwd(h)
    second = launch(h, tmp_path, [repo], branch="feat-b", slug="b")
    assert first_cwd == worktrees / "video-core" / first
    assert session_cwd(h) == worktrees / "video-core" / second
    assert (worktrees / "video-core" / first).is_dir()


def test_a_job_claims_no_repository(h, tmp_path, repo, worktrees):
    job_id = launch(h, tmp_path, [repo], branch="feat-a")
    assert rows(h)[job_id]["resources"] == []


def test_a_launched_job_still_claims_the_bench_as_a_short_hold(h, tmp_path, repo, worktrees):
    job_id = launch(h, tmp_path, [repo], device="bench", branch="feat-a")
    assert h.run("claim", job_id, "device:bench") == 0
    assert rows(h)[job_id]["resources"] == ["device:bench"]


def test_a_relaunch_reuses_the_worktree_under_the_root_recorded_at_the_first_launch(h, tmp_path, repo, worktrees):
    job_id = launch(h, tmp_path, [repo], branch="feat-a")
    path = session_cwd(h)
    (path / "wip.txt").write_text("keep", encoding="utf-8")
    (h.root / "jobs" / job_id / "result.md").write_text(NEEDS_INPUT_RESULT, encoding="utf-8")
    del h.claude.statuses[job_id]
    configure(h, {"worktree": {"root": str(tmp_path / "moved")}})
    assert h.run("launch", job_id) == 0
    assert session_cwd(h) == path
    assert (path / "wip.txt").read_text(encoding="utf-8") == "keep"
    assert len(git(repo, "worktree", "list").splitlines()) == 2


def test_a_resume_runs_in_the_existing_worktree(h, tmp_path, repo, worktrees):
    job_id = launch(h, tmp_path, [repo], branch="feat-a")
    (h.root / "jobs" / job_id / "result.md").write_text(NEEDS_INPUT_RESULT, encoding="utf-8")
    h.claude.statuses[job_id] = SessionStatus.IDLE
    assert h.run("resume", job_id) == 0
    assert Path(h.claude.resumed[-1][2]) == worktrees / "video-core" / job_id
    assert len(git(repo, "worktree", "list").splitlines()) == 2


def test_an_after_job_starts_its_worktree_from_the_predecessor_branch(h, tmp_path, repo, worktrees):
    pred = launch(h, tmp_path, [repo], branch="feat-a", slug="a")
    git(session_cwd(h), "switch", "-q", "-c", "feat-a")
    git(session_cwd(h), "commit", "-q", "--allow-empty", "-m", "pred work")
    (h.root / "jobs" / pred / "result.md").write_text(DONE_RESULT, encoding="utf-8")
    succ = launch(h, tmp_path, [repo], branch="feat-b", slug="b", after=pred)
    cwd = session_cwd(h)
    assert cwd == worktrees / "video-core" / succ
    assert git(cwd, "rev-parse", "HEAD") == git(repo, "rev-parse", "feat-a")
    assert git(cwd, "rev-parse", "HEAD") != git(repo, "rev-parse", "main")


def test_an_after_job_without_a_predecessor_branch_starts_from_the_predecessor_worktree_head(h, tmp_path, repo, worktrees):
    pred = launch(h, tmp_path, [repo], slug="a")
    git(session_cwd(h), "commit", "-q", "--allow-empty", "-m", "pred work")
    head = git(session_cwd(h), "rev-parse", "HEAD")
    (h.root / "jobs" / pred / "result.md").write_text(DONE_RESULT, encoding="utf-8")
    launch(h, tmp_path, [repo], slug="b", after=pred)
    assert git(session_cwd(h), "rev-parse", "HEAD") == head != git(repo, "rev-parse", "main")


def finished(h, tmp_path, repo, slug="x", branch="feat-a") -> tuple[str, Path]:
    job_id = launch(h, tmp_path, [repo], slug=slug, branch=branch)
    path = session_cwd(h)
    git(path, "switch", "-q", "-c", branch)
    assert h.run("finish", job_id, "--status", "done") == 0
    assert h.run("reported", job_id) == 0
    assert h.run("remove-sessions", job_id) == 0
    return job_id, path


def test_finish_keeps_the_worktree(h, tmp_path, repo, worktrees):
    assert finished(h, tmp_path, repo)[1].is_dir()


def test_prune_removes_the_worktree_of_a_pruned_job_and_keeps_its_branch(h, tmp_path, repo, worktrees):
    job_id, path = finished(h, tmp_path, repo)
    h.lines.clear()
    assert h.run("prune") == 0
    assert h.lines == [job_id]
    assert not path.exists()
    assert str(path) not in git(repo, "worktree", "list", "--porcelain")
    assert git(repo, "rev-parse", "--verify", "feat-a")


def test_prune_keeps_the_worktree_of_a_job_it_does_not_prune(h, tmp_path, repo, worktrees):
    launch(h, tmp_path, [repo], branch="feat-a")
    path = session_cwd(h)
    assert h.run("prune") == 0
    assert path.is_dir()


def test_a_worktree_that_git_refuses_to_remove_keeps_its_job_and_others_are_pruned(h, tmp_path, repo, worktrees, capsys):
    (repo / "tracked").write_text("a", encoding="utf-8")
    git(repo, "add", "tracked")
    git(repo, "commit", "-q", "-m", "tracked")
    blocked, blocked_path = finished(h, tmp_path, repo, slug="a", branch="feat-a")
    pruned, pruned_path = finished(h, tmp_path, repo, slug="b", branch="feat-b")
    (blocked_path / "tracked").write_text("edited", encoding="utf-8")
    h.lines.clear()
    assert h.run("prune") == 1
    assert h.lines == [pruned]
    assert f"job {blocked}: " in capsys.readouterr().err
    assert blocked_path.is_dir() and (h.root / "jobs" / blocked).is_dir() and not pruned_path.exists()
