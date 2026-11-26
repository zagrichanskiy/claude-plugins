"""The workspace slots of the jobs launched from a ``repo`` tool workspace.

A slot is a copy of the launch workspace with its own ``sources/`` and build directories. ``repo init``
makes it from the launch workspace's manifest, with ``--reference`` to the launch workspace. The build
configuration is copied with the launch workspace root rewritten to the slot, so downloads and sstate stay
shared through the paths that configuration names outside the workspace.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import xml.etree.ElementTree as ElementTree
from pathlib import Path
from typing import Sequence

from .errors import SlotError

#: The free space a new slot needs under ``slots.root``: its checkouts and the work directories of its builds.
NEEDED_BYTES = 100 * 2**30

#: Files the manifest does not create and sessions read. A slot links to the launch workspace's copy.
_LINKS = ("CLAUDE.md", ".claude", "sources/CLAUDE.md", "sources/CLAUDE.local.md")

#: The file of a slot that names the workspace its build configuration and links come from.
_SOURCE = ".repo/cure-workspace"

#: The ``repo forall`` script of :func:`prepare`. A remote that cannot be read keeps every branch.
_PREPARE = ('git reset -q --hard && git clean -fdq && git checkout -q --detach "$REPO_LREV" || exit 1; '
            'remote=$(git ls-remote -q --heads "${REPO_REMOTE:-origin}" | cut -f2); '
            "for ref in $(git for-each-ref --format='%(refname)' refs/heads/); do "
            'if printf "%s\\n" "$remote" | grep -qxF "$ref" && git fetch -q "${REPO_REMOTE:-origin}" "$ref" '
            '&& git merge-base --is-ancestor "$ref" FETCH_HEAD; then git branch -q -D "${ref#refs/heads/}" || exit 1; fi; '
            "done")


def find_workspace(path: str | Path) -> Path | None:
    """The nearest ancestor of ``path``, ``path`` included, that holds a ``.repo`` directory."""
    start = Path(os.path.abspath(path))
    return next((directory for directory in (start, *start.parents) if os.path.isdir(directory / ".repo")), None)


def ready(workspace: Path, slot: Path) -> None:
    """:func:`create` a missing ``slot``. Point an existing one at the launch manifest again and :func:`prepare` it.
    An existing slot made from another workspace gets the build configuration and links of ``workspace``."""
    if not slot.is_dir():
        create(workspace, slot)
        return
    _init(workspace, slot)
    prepare(slot)
    source = slot / _SOURCE
    try:
        if not source.is_file() or source.read_text(encoding="utf-8") != str(workspace):
            _configure(workspace, slot)
    except OSError as e:
        raise SlotError(f"cannot point the slot {slot} at {workspace}: {e}") from e


def create(workspace: Path, slot: Path) -> None:
    """Create ``slot`` from ``workspace``. A failure removes what was created."""
    free = shutil.disk_usage(_existing(slot.parent)).free
    if free < NEEDED_BYTES:
        raise SlotError(f"cannot create the slot {slot}: {free} bytes free, {NEEDED_BYTES} bytes needed")
    try:
        slot.mkdir(parents=True)
    except OSError as e:
        raise SlotError(f"cannot create the slot {slot}: {e}") from e
    try:
        _init(workspace, slot)
        _checked(slot, "repo", "sync", "-c")
        _configure(workspace, slot)
    except OSError as e:
        shutil.rmtree(slot, ignore_errors=True)
        raise SlotError(f"cannot create the slot {slot}: {e}") from e
    except BaseException:
        shutil.rmtree(slot, ignore_errors=True)
        raise


def prepare(slot: Path) -> None:
    """Discard the uncommitted changes and untracked files of every project of ``slot``, detach it at its manifest
    revision, delete each local branch whose tip the same branch on the project's remote contains, and sync. A
    local-only branch and a branch ahead of or diverged from the remote stay."""
    _checked(slot, "repo", "forall", "-c", _PREPARE)
    _checked(slot, "repo", "sync", "-c")


def copy_branches(workspace: Path, source: Path, slot: Path, repos: Sequence[str], branch: str | None) -> None:
    """Make every local branch of the slot ``source`` a local branch of ``slot``, in the project that holds each
    of ``repos``. A branch ``slot`` already has is only fast-forwarded; any other update is refused, except for
    ``branch``: ``slot`` takes it from ``source`` and keeps its own as ``<branch>-backup-<short sha>``."""
    for project in _projects(workspace, slot, repos):
        if os.path.realpath(source / project) != os.path.realpath(slot / project):
            # git refuses to fetch into the branch checked out.
            _checked(slot / project, "git", "switch", "-q", "--detach")
            if branch is not None:
                _back_up_diverged(slot / project, source / project, branch)
            _checked(slot / project, "git", "fetch", "-q", str(source / project), "refs/heads/*:refs/heads/*")


def start_branches(workspace: Path, slot: Path, repos: Sequence[str], branch: str,
                   after: tuple[Path, str] | None) -> None:
    """Check out ``branch`` in the project of ``slot`` that holds each of ``repos``.

    A new branch starts at the tip of the branch ``after[1]`` in the slot ``after[0]`` with ``after``, else at
    ``branch`` in the launch workspace; else on a remote, else at the manifest revision.
    A branch that already exists at that start is checked out as it is."""
    for project in _projects(workspace, slot, repos):
        if after is not None:
            start = _fetched(slot / project, [str(after[0] / project)], after[1])
        else:
            start = _fetched(slot / project, [str(workspace / project)], branch)
        existing = _run(slot / project, "git", "rev-parse", "-q", "--verify", f"refs/heads/{branch}").stdout.strip()
        if not existing:
            _checked(slot / project, "git", "switch", "-q", "-c", branch, start)
        elif existing == start:
            _checked(slot / project, "git", "switch", "-q", branch)
        else:
            raise SlotError(f"{slot / project}: branch {branch} exists at {existing}, not at its start {start}")


def _init(workspace: Path, slot: Path) -> None:
    manifests = workspace / ".repo" / "manifests"
    url = _checked(manifests, "git", "config", "remote.origin.url")
    branch = _checked(manifests, "git", "config", "branch.default.merge").removeprefix("refs/heads/")
    _checked(slot, "repo", "init", "-u", url, "-m", _manifest_file(workspace), "-b", branch,
             f"--reference={workspace}")
    local = workspace / ".repo" / "local_manifests"
    if local.is_dir():
        shutil.copytree(local, slot / ".repo" / "local_manifests", dirs_exist_ok=True)


def _manifest_file(workspace: Path) -> str:
    """The manifest file ``repo init -m`` chose for ``workspace``."""
    path = workspace / ".repo" / "manifest.xml"
    if path.is_symlink():
        return os.path.basename(os.readlink(path))
    try:
        includes = ElementTree.parse(path).getroot().findall("include")
    except (OSError, ElementTree.ParseError) as e:
        raise SlotError(f"cannot read {path}: {e}") from e
    if len(includes) != 1 or not includes[0].get("name"):
        raise SlotError(f"{path} does not include exactly one manifest file")
    return includes[0].get("name")


def _configure(workspace: Path, slot: Path) -> None:
    """Replace the ``conf/`` of each build directory of ``slot`` that ``workspace`` has with a copy of the one of
    ``workspace``, and link ``slot`` to its session files."""
    (slot / _SOURCE).unlink(missing_ok=True)
    for build in sorted(path.name for path in workspace.iterdir() if (path / "conf" / "bblayers.conf").is_file()):
        if os.path.lexists(slot / build / "conf"):
            shutil.rmtree(slot / build / "conf")
        _copy_conf(workspace / build / "conf", slot / build / "conf", workspace, slot)
    for name in _LINKS:
        if (slot / name).is_symlink():
            (slot / name).unlink()
        if (workspace / name).exists() and not os.path.lexists(slot / name):
            (slot / name).parent.mkdir(parents=True, exist_ok=True)
            (slot / name).symlink_to(workspace / name)
    (slot / _SOURCE).write_text(str(workspace), encoding="utf-8")


def _copy_conf(source: Path, target: Path, workspace: Path, slot: Path) -> None:
    root = re.compile(re.escape(os.fsencode(workspace)) + rb"(?![\w.+-])")
    replacement = os.fsencode(slot)
    for directory, _, files in os.walk(source):
        copy = target / os.path.relpath(directory, source)
        copy.mkdir(parents=True, exist_ok=True)
        for name in files:
            (copy / name).write_bytes(root.sub(lambda _: replacement, Path(directory, name).read_bytes()))


def _projects(workspace: Path, slot: Path, repos: Sequence[str]) -> list[str]:
    """The path of each project holding one of ``repos``, relative to the workspace root, without repeats."""
    found: list[str] = []
    for repo in repos:
        inside = os.path.relpath(os.path.abspath(repo), workspace)
        if inside.split(os.sep)[0] == os.pardir:
            raise SlotError(f"{repo} is outside the workspace {workspace}")
        toplevel = _checked(slot / inside, "git", "rev-parse", "--show-toplevel")
        project = os.path.relpath(toplevel, os.path.realpath(slot))
        if project not in found:
            found.append(project)
    return found


def _fetched(project: Path, sources: Sequence[str], branch: str) -> str:
    """The commit of ``branch`` fetched from the first of ``sources``, then the remotes of ``project``, that has it.
    Without one, the commit ``project`` has checked out. A source that cannot be read is an error."""
    ref = f"refs/heads/{branch}"
    for source in sources:
        if _checked(project, "git", "ls-remote", "--heads", source, ref):
            _checked(project, "git", "fetch", "-q", source, ref)
            return _checked(project, "git", "rev-parse", "FETCH_HEAD")
    for remote in _checked(project, "git", "remote").split():
        if _run(project, "git", "fetch", "-q", remote, ref).returncode == 0:
            return _checked(project, "git", "rev-parse", "FETCH_HEAD")
    return _checked(project, "git", "rev-parse", "HEAD")


def _back_up_diverged(project: Path, source: Path, branch: str) -> None:
    """Rename ``branch`` of ``project`` to ``<branch>-backup-<short sha>`` unless the same branch of ``source``
    contains its tip."""
    ref = f"refs/heads/{branch}"
    if not _run(project, "git", "rev-parse", "-q", "--verify", ref).stdout.strip():
        return
    if _run(project, "git", "fetch", "-q", str(source), ref).returncode != 0:
        return
    if _run(project, "git", "merge-base", "--is-ancestor", ref, "FETCH_HEAD").returncode == 0:
        return
    short = _checked(project, "git", "rev-parse", "--short", ref)
    _checked(project, "git", "branch", "-q", "-m", branch, f"{branch}-backup-{short}")


def _existing(path: Path) -> Path:
    while not path.exists():
        path = path.parent
    return path


def _run(cwd: Path, *argv: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, stdin=subprocess.DEVNULL)
    except OSError as e:
        raise SlotError(f"{' '.join(argv[:2])} in {cwd}: {e}") from e


def _checked(cwd: Path, *argv: str) -> str:
    done = _run(cwd, *argv)
    if done.returncode != 0:
        raise SlotError(f"{' '.join(argv[:2])} in {cwd}: {done.stderr.strip()}")
    return done.stdout.strip()
