"""The git worktrees of a job: one per repository of its handoff, at ``<root>/<repo name>/<job id>``.

``<repo name>`` is the basename of the repository's git toplevel. A worktree is detached at the HEAD of
the predecessor's worktree of the same repository where it exists, else at the repository's HEAD; the
run session creates the job's branch. :data:`git` is the seam a test replaces.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path
from typing import Callable, Sequence

from .errors import GitError


class Git:
    def toplevel(self, repo: str) -> str:
        return _checked(repo, "rev-parse", "--show-toplevel")

    def add(self, repo: str, path: Path, base: Path | None) -> str:
        """Create the worktree and return the commit it is detached at."""
        start = self.head(base if base is not None and base.is_dir() else Path(repo))
        _checked(repo, "worktree", "add", "--detach", str(path), start)
        return start

    def head(self, checkout: Path) -> str:
        return _checked(str(checkout), "rev-parse", "HEAD")

    def changed_lines(self, checkout: Path, base: str) -> int:
        """Insertions plus deletions of the commits of ``checkout`` since ``base``."""
        stat = _checked(str(checkout), "diff", "--shortstat", base, "HEAD")
        return sum(int(count) for count in re.findall(r"(\d+) (?:insertion|deletion)", stat))

    def remove(self, repo: str, path: Path) -> None:
        _checked(repo, "worktree", "remove", str(path))


git = Git()


def open_all(root: str, repos: Sequence[str], job_id: str, predecessor: Callable[[], tuple[str, str] | None],
             started: Callable[[str, str], None]) -> Path:
    """Create each missing worktree of ``repos``, passing its repository and start commit to ``started``, and
    return the directory of the first repository in its worktree. An existing worktree is kept as it is.
    ``predecessor`` gives the worktree root and id of the job whose worktrees the missing ones start from, and
    is called only when one is missing."""
    found = paths(root, repos, job_id)
    missing = [repo for repo, path in found.items() if not path.is_dir()]
    if missing:
        after = predecessor()
        bases = paths(after[0], missing, after[1]) if after is not None else {}
        for repo in missing:
            started(repo, git.add(repo, found[repo], bases.get(repo)))
    toplevel = git.toplevel(repos[0])
    return found[repos[0]] / os.path.relpath(os.path.realpath(repos[0]), os.path.realpath(toplevel))


def remove_all(root: str, repos: Sequence[str], job_id: str) -> list[tuple[Path, GitError]]:
    """Remove each worktree of ``repos`` that exists and return each one git refused to remove, with its error.
    The branches stay."""
    left = []
    for repo, path in paths(root, repos, job_id).items():
        if path.is_dir():
            try:
                git.remove(repo, path)
            except GitError as e:
                left.append((path, e))
    return left


def paths(root: str, repos: Sequence[str], job_id: str) -> dict[str, Path]:
    """The worktree of each repository, keyed by the first of ``repos`` in each toplevel."""
    found: dict[str, Path] = {}
    for toplevel, repo in firsts(repos).items():
        path = Path(os.path.expanduser(root)) / os.path.basename(toplevel) / job_id
        if path in found.values():
            raise GitError(f"{repo}: another repository of job {job_id} has the worktree {path}")
        found[repo] = path
    return found


def firsts(repos: Sequence[str]) -> dict[str, str]:
    """Each git toplevel of ``repos`` mapped to the first of ``repos`` in it."""
    found: dict[str, str] = {}
    for repo in repos:
        found.setdefault(git.toplevel(repo), repo)
    return found


def _run(cwd: str, *args: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    except OSError as e:
        raise GitError(f"git {' '.join(args)} in {cwd}: {e}") from e


def _checked(cwd: str, *args: str) -> str:
    done = _run(cwd, *args)
    if done.returncode != 0:
        raise GitError(f"git {' '.join(args)} in {cwd}: {done.stderr.strip()}")
    return done.stdout.strip()
