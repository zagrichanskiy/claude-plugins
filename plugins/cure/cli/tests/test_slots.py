"""Issue 131: a job whose launch checkout is in a ``repo`` workspace runs in a workspace slot.

``repo`` is a fake executable on PATH that records its calls and acts on a real local origin; ``git`` is real.
The slot module assumed here is ``cure_job.slot``:

* ``find_workspace(path) -> Path | None``, the nearest ancestor holding ``.repo``;
* ``create(workspace, slot)``, raising ``SlotError`` when the free space under the slot's parent is below
  ``NEEDED_BYTES``, with the message ``<free> bytes free, <needed> bytes needed``;
* ``prepare(slot)``, which reaches the projects only through ``repo forall -c``.

A slot is held through the claim ``slot:<path>``. A launch with no free slot exits 1 with ``no free slot``.
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
from collections import namedtuple
from pathlib import Path

import pytest

from cure_job import slot
from cure_job.claude import SessionStatus
from cure_job.config import DEFAULTS
from tests.test_approve import DONE_RESULT, NEEDS_INPUT_RESULT, rows
from tests.test_cli import Harness
from tests.test_config import configure
from tests.test_worktrees import git, session_cwd

PROJECT = "sources/repositories/video-core"
FAKE_REPO = f"""#!/bin/sh
echo "$PWD $*" >> "$FAKE_REPO_LOG"
case "$1" in
  init) mkdir -p .repo ;;
  sync) [ -d {PROJECT} ] || {{ mkdir -p sources/repositories; git clone -q "$FAKE_ORIGIN" {PROJECT}; }} ;;
  forall) [ -d {PROJECT} ] && cd {PROJECT} && REPO_PATH={PROJECT} REPO_LREV=$(git rev-parse origin/main) sh -c "$3" ;;
esac
"""


@pytest.fixture(autouse=True)
def fake_git():
    """These tests run real git."""


@pytest.fixture
def h(root):
    return Harness(root)


@pytest.fixture
def origin(tmp_path) -> Path:
    path = tmp_path / "origin.git"
    seed = tmp_path / "seed"
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(path))
    git(tmp_path, "clone", "-q", str(path), str(seed))
    git(seed, "commit", "-q", "--allow-empty", "-m", "base")
    git(seed, "push", "-q", "origin", "main")
    return path


@pytest.fixture
def repo_log(tmp_path, origin, monkeypatch) -> Path:
    tools = tmp_path / "tools"
    tools.mkdir()
    (tools / "repo").write_text(FAKE_REPO, encoding="utf-8")
    (tools / "repo").chmod(stat.S_IRWXU)
    log = tmp_path / "repo.log"
    monkeypatch.setenv("PATH", f"{tools}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_REPO_LOG", str(log))
    monkeypatch.setenv("FAKE_ORIGIN", str(origin))
    return log


def repo_calls(log: Path) -> list[tuple[str, list[str]]]:
    return [(line.split()[0], line.split()[1:]) for line in log.read_text(encoding="utf-8").splitlines()]


def value_of(args: list[str], flag: str) -> str:
    return args[args.index(flag) + 1]


@pytest.fixture
def workspace(tmp_path, origin) -> Path:
    ws = tmp_path / "ws"
    manifests = ws / ".repo" / "manifests"
    manifests.mkdir(parents=True)
    git(manifests, "init", "-q")
    git(manifests, "config", "remote.origin.url", "git@example.com:team/manifests.git")
    git(manifests, "config", "branch.default.merge", "refs/heads/team/main/dev")
    (ws / ".repo" / "manifest.xml").write_text('<manifest><include name="dev.xml" /></manifest>', encoding="utf-8")
    (ws / ".repo" / "local_manifests").mkdir()
    (ws / ".repo" / "local_manifests" / "extra.xml").write_text("<manifest/>", encoding="utf-8")
    for build in ("build", "build2"):
        (ws / build / "conf").mkdir(parents=True)
        (ws / build / "conf" / "bblayers.conf").write_text(f'BBLAYERS = "{ws}/layers/meta {ws}/../keep/meta"\n',
                                                           encoding="utf-8")
        (ws / build / "conf" / "local.conf").write_text('DL_DIR = "/srv/cache/downloads"\n', encoding="utf-8")
    (ws / "scratch" / "conf").mkdir(parents=True)
    (ws / "scratch" / "conf" / "local.conf").write_text("x\n", encoding="utf-8")
    (ws / ".claude").mkdir()
    (ws / "sources").mkdir(exist_ok=True)
    for name in ("CLAUDE.md", "sources/CLAUDE.md", "sources/CLAUDE.local.md"):
        (ws / name).write_text(name, encoding="utf-8")
    (ws / "sources" / "repositories").mkdir()
    git(ws, "clone", "-q", str(origin), str(ws / PROJECT))
    return ws


def clone_in(slot_dir: Path) -> Path:
    return slot_dir / PROJECT


def test_slot_defaults():
    assert DEFAULTS["slots.count"] == 5
    assert DEFAULTS["slots.root"] == "~/work/yocto/slots"


def test_the_workspace_is_the_nearest_ancestor_holding_repo(tmp_path):
    inner = tmp_path / "a" / "b"
    (tmp_path / "a" / ".repo").mkdir(parents=True)
    (inner / ".repo").mkdir(parents=True)
    assert slot.find_workspace(inner / "c" / "d") == inner
    assert slot.find_workspace(tmp_path / "a" / "x") == tmp_path / "a"


def test_a_path_outside_a_repo_workspace_has_no_workspace(tmp_path):
    assert slot.find_workspace(tmp_path) is None


def test_creating_a_slot_inits_with_the_launch_manifest_then_syncs(workspace, repo_log, tmp_path):
    target = tmp_path / "slots" / "1"
    slot.create(workspace, target)
    (init_dir, init), (sync_dir, sync) = repo_calls(repo_log)[:2]
    assert (init_dir, init[0]) == (str(target), "init") and (sync_dir, sync[0]) == (str(target), "sync")
    assert value_of(init, "-u") == "git@example.com:team/manifests.git"
    assert value_of(init, "-m") == "dev.xml"
    assert value_of(init, "-b") == "team/main/dev"
    assert f"--reference={workspace}" in init
    assert "-c" in sync


def test_creating_a_slot_copies_every_build_conf_with_the_root_rewritten(workspace, repo_log, tmp_path):
    target = tmp_path / "slots" / "1"
    slot.create(workspace, target)
    for build in ("build", "build2"):
        layers = (target / build / "conf" / "bblayers.conf").read_text(encoding="utf-8")
        assert layers == f'BBLAYERS = "{target}/layers/meta {target}/../keep/meta"\n'
        assert (target / build / "conf" / "local.conf").read_text(encoding="utf-8") == 'DL_DIR = "/srv/cache/downloads"\n'
    assert not (target / "scratch").exists()


def test_creating_a_slot_links_the_session_files_and_copies_local_manifests(workspace, repo_log, tmp_path):
    target = tmp_path / "slots" / "1"
    slot.create(workspace, target)
    for name in ("CLAUDE.md", ".claude", "sources/CLAUDE.md", "sources/CLAUDE.local.md"):
        assert (target / name).is_symlink() and (target / name).resolve() == (workspace / name).resolve()
    extra = target / ".repo" / "local_manifests" / "extra.xml"
    assert extra.is_file() and not extra.is_symlink()


def test_creating_a_slot_with_too_little_disk_is_refused_naming_free_and_needed_sizes(workspace, repo_log, tmp_path,
                                                                                    monkeypatch):
    usage = namedtuple("usage", "total used free")
    monkeypatch.setattr(shutil, "disk_usage", lambda path: usage(10**12, 10**12 - 1234, 1234))
    with pytest.raises(slot.SlotError, match=f"1234 bytes free, {slot.NEEDED_BYTES} bytes needed"):
        slot.create(workspace, tmp_path / "slots" / "1")
    assert not repo_log.exists() and not (tmp_path / "slots" / "1").exists()


def test_reusing_a_slot_returns_projects_to_the_manifest_revision_deletes_pushed_branches_then_syncs(
        workspace, repo_log, tmp_path):
    target = tmp_path / "slots" / "1"
    slot.create(workspace, target)
    project = clone_in(target)
    git(project, "switch", "-q", "-c", "pushed")
    git(project, "commit", "-q", "--allow-empty", "-m", "work")
    git(project, "push", "-q", "origin", "pushed")
    git(project, "switch", "-q", "-c", "local-only")
    git(project, "commit", "-q", "--allow-empty", "-m", "work")
    repo_log.unlink()
    slot.prepare(target)
    assert git(project, "rev-parse", "HEAD") == git(project, "rev-parse", "origin/main")
    assert git(project, "rev-parse", "--abbrev-ref", "HEAD") == "HEAD"
    branches = git(project, "branch", "--format=%(refname:short)").split()
    assert "pushed" not in branches and "local-only" in branches
    assert repo_calls(repo_log)[-1][1][0] == "sync" and "-c" in repo_calls(repo_log)[-1][1]


# --- the slot as a cure-job resource ---------------------------------------------------------------------

@pytest.fixture
def slots(h, tmp_path, workspace, repo_log) -> Path:
    path = (tmp_path / "slots").resolve()
    configure(h, {"slots": {"root": str(path), "count": 2}})
    return path


def start(h, workspace, slug, **fields) -> str:
    job_id = h.new(workspace.parent, repos=(str(workspace / PROJECT),), slug=slug, **fields)
    h.approve(job_id)
    assert h.run("launch", job_id) == 0
    return job_id


def finish(h, job_id, result=DONE_RESULT):
    (h.root / "jobs" / job_id / "result.md").write_text(result, encoding="utf-8")


def test_two_jobs_in_one_workspace_take_two_slots_and_never_main(h, workspace, slots):
    first = start(h, workspace, "a", branch="feat-a")
    assert session_cwd(h) == slots / "1" / PROJECT
    second = start(h, workspace, "b", branch="feat-b")
    assert session_cwd(h) == slots / "2" / PROJECT
    assert f"slot:{slots / '1'}" in rows(h)[first]["resources"]
    assert f"slot:{slots / '2'}" in rows(h)[second]["resources"]
    assert sorted(path.name for path in slots.iterdir()) == ["1", "2"]


def test_a_job_creates_its_branch_in_the_slot_at_launch(h, workspace, slots):
    start(h, workspace, "a", branch="feat-a")
    project = session_cwd(h)
    assert git(project, "rev-parse", "--abbrev-ref", "HEAD") == "feat-a"
    assert git(project, "rev-parse", "HEAD") == git(project, "rev-parse", "origin/main")


def test_a_third_job_waits_when_both_slots_are_taken(h, workspace, slots, capsys):
    first = start(h, workspace, "a")
    start(h, workspace, "b")
    third = h.new(workspace.parent, repos=(str(workspace / PROJECT),), slug="c")
    h.approve(third)
    assert h.run("launch", third) == 1
    assert "no free slot" in capsys.readouterr().err
    assert h.cli.jobs.store.load(third).run == 0
    finish(h, first)
    assert h.run("launch", third) == 0
    assert session_cwd(h) == slots / "1" / PROJECT


def test_a_needs_input_job_keeps_its_slot_and_resumes_in_it(h, workspace, slots):
    job_id = start(h, workspace, "a")
    finish(h, job_id, NEEDS_INPUT_RESULT)
    h.claude.statuses[job_id] = SessionStatus.IDLE
    other = h.new(workspace.parent, repos=(str(workspace / PROJECT),), slug="b")
    h.approve(other)
    assert h.run("launch", other) == 0
    assert session_cwd(h) == slots / "2" / PROJECT
    assert h.run("resume", job_id) == 0
    assert Path(h.claude.resumed[-1][2]) == slots / "1" / PROJECT


def test_a_done_job_releases_its_slot_and_the_next_job_reuses_it_without_the_previous_branches(
        h, workspace, slots, repo_log):
    first = start(h, workspace, "a", branch="feat-a")
    project = session_cwd(h)
    git(project, "push", "-q", "origin", "feat-a")
    (slots / "1" / "build" / "tmp").mkdir(parents=True)
    (slots / "1" / "build" / "tmp" / "marker").write_text("built", encoding="utf-8")
    finish(h, first)
    start(h, workspace, "b", branch="feat-b")
    assert session_cwd(h) == project
    assert (slots / "1" / "build" / "tmp" / "marker").read_text(encoding="utf-8") == "built"
    branches = git(project, "branch", "--format=%(refname:short)").split()
    assert "feat-a" not in branches and "feat-b" in branches
    assert [name for _, args in repo_calls(repo_log) if (name := args[0]) == "init"] == ["init", "init"]


def test_an_after_job_starts_its_branch_from_the_predecessor_branch(h, workspace, slots):
    first = start(h, workspace, "a", branch="feat-a")
    git(session_cwd(h), "commit", "-q", "--allow-empty", "-m", "predecessor work")
    tip = git(session_cwd(h), "rev-parse", "HEAD")
    finish(h, first)
    start(h, workspace, "b", branch="feat-b", after=first)
    project = session_cwd(h)
    assert git(project, "rev-parse", "feat-b") == tip != git(project, "rev-parse", "origin/main")


def test_a_job_outside_a_repo_workspace_keeps_its_worktree(h, tmp_path, slots):
    plain = tmp_path / "plain" / "video-core"
    plain.mkdir(parents=True)
    git(plain, "init", "-q", "-b", "main")
    git(plain, "commit", "-q", "--allow-empty", "-m", "base")
    job_id = h.new(tmp_path, repos=(str(plain),))
    h.approve(job_id)
    assert h.run("launch", job_id) == 0
    assert slots not in session_cwd(h).parents
    assert rows(h)[job_id]["resources"] == []


# --- reuse without a job record, predecessors without a branch, dirty slots -------------------------------

def push_new_branch(project: Path, name: str, push: bool) -> str:
    git(project, "switch", "-q", "-c", name)
    git(project, "commit", "-q", "--allow-empty", "-m", f"work on {name}")
    if push:
        git(project, "push", "-q", "origin", name)
    return git(project, "rev-parse", "HEAD")


def local_branches(project: Path) -> list[str]:
    return git(project, "branch", "--format=%(refname:short)").split()


@pytest.mark.parametrize("prune", [False, True], ids=["record-kept", "record-pruned"])
def test_reusing_a_slot_deletes_pushed_branches_whatever_the_job_record_says(h, workspace, slots, prune):
    first = start(h, workspace, "a")
    project = session_cwd(h)
    push_new_branch(project, "pushed", push=True)
    push_new_branch(project, "local-only", push=False)
    finish(h, first)
    if prune:
        h.cli.jobs.store.remove(first)
    start(h, workspace, "b")
    assert session_cwd(h) == project
    branches = local_branches(project)
    assert "pushed" not in branches and "local-only" in branches


@pytest.mark.parametrize("other_slot", [False, True], ids=["same-slot", "other-slot"])
def test_an_after_job_without_a_predecessor_branch_gets_its_local_branches(h, workspace, slots, other_slot):
    filler = start(h, workspace, "f") if other_slot else None
    first = start(h, workspace, "a")
    predecessor = session_cwd(h)
    tip = push_new_branch(predecessor, "wip", push=False)
    finish(h, first)
    if filler:
        finish(h, filler)
    start(h, workspace, "b", after=first)
    project = session_cwd(h)
    assert (project != predecessor) is other_slot
    assert git(project, "rev-parse", "wip") == tip


def test_a_reused_slot_is_clean_after_the_next_launch_and_keeps_local_commits(workspace, repo_log, tmp_path):
    target = tmp_path / "slots" / "1"
    slot.create(workspace, target)
    project = clone_in(target)
    git(project, "switch", "-q", "-c", "local-only")
    (project / "tracked.txt").write_text("one", encoding="utf-8")
    git(project, "add", "tracked.txt")
    git(project, "commit", "-q", "-m", "local work")
    kept = git(project, "rev-parse", "HEAD")
    (project / "tracked.txt").write_text("two", encoding="utf-8")
    (project / "untracked.txt").write_text("x", encoding="utf-8")
    slot.prepare(target)
    assert git(project, "status", "--porcelain") == ""
    assert not (project / "untracked.txt").exists()
    assert git(project, "rev-parse", "local-only") == kept
    assert git(project, "rev-parse", "HEAD") == git(project, "rev-parse", "origin/main")


def test_a_slot_job_does_not_record_a_worktree_root(h, workspace, slots):
    job_id = start(h, workspace, "a")
    assert h.cli.jobs.store.load(job_id).worktree_root is None


def test_prepare_keeps_a_branch_named_on_the_remote_when_its_tip_has_a_local_commit(workspace, repo_log, tmp_path):
    target = tmp_path / "slots" / "1"
    slot.create(workspace, target)
    project = clone_in(target)
    push_new_branch(project, "ahead", push=True)
    push_new_branch(project, "merged", push=True)
    git(project, "switch", "-q", "ahead")
    git(project, "commit", "-q", "--allow-empty", "-m", "unpushed")
    kept = git(project, "rev-parse", "HEAD")
    slot.prepare(target)
    assert git(project, "rev-parse", "ahead") == kept
    assert "merged" not in local_branches(project)


def test_pruning_an_expired_slot_job_removes_only_its_record(h, workspace, slots, monkeypatch):
    job_id = start(h, workspace, "a")
    project = session_cwd(h)
    assert h.run("finish", job_id, "--status", "done") == 0
    assert h.run("reported", job_id) == 0
    assert h.run("remove-sessions", job_id) == 0

    def refuse(*args, **kwargs):
        raise AssertionError("a slot job has no worktree to remove")

    monkeypatch.setattr("cure_job.worktree.remove_all", refuse)
    assert h.run("prune") == 0
    assert not (h.root / "jobs" / job_id).exists()
    assert project.is_dir()
