"""The claim ``main``: the one interactive session that may write in the main workspace.

The main workspace is a ``repo`` tool workspace that is not a slot, that is, whose parent is not ``slots.root``.
The claim is the file ``main-claim`` in the state root, holding the session id. A write is an Edit or a Write of
a file, or a Bash command that runs ``bitbake``, a ``git`` command :func:`_git_reads` does not accept, or a ``repo``
subcommand outside :data:`REPO_READS`. A target under ``slots.root`` or ``worktree.root`` is never in the main
workspace, even where that root lies inside it.
"""
from __future__ import annotations

import os
import re
import shlex
from pathlib import Path
from typing import Mapping

from .errors import MainHeld, StoreError
from .slot import find_workspace
from .store import JobStore

MAIN = "main"
_FILE = "main-claim"

GIT_READS = frozenset({"status", "log", "diff", "show", "blame", "grep", "rev-parse", "rev-list", "ls-files",
                       "ls-tree", "ls-remote", "cat-file", "describe", "shortlog", "merge-base", "for-each-ref",
                       "show-ref", "name-rev", "help", "version", "reflog", "symbolic-ref"})

REPO_READS = frozenset({"status", "info", "list", "manifest", "diff", "branches"})

_SEPARATORS = re.compile(r"&&|\|\||[;|&\n()]")

_TAG_LIST_FLAGS = re.compile(r"-l|--list|-n\d*|-i|--ignore-case|--(sort|format|color|column)(=.*)?|--no-column")


def holder(store: JobStore) -> str | None:
    try:
        return (store.root / _FILE).read_text(encoding="utf-8").strip() or None
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError) as e:
        raise StoreError(f"cannot read {store.root / _FILE}: {e}") from e


def claim(store: JobStore, session: str) -> None:
    """Make ``session`` the holder of ``main``. Raises :class:`MainHeld` while another session holds it."""
    with store.locked():
        current = holder(store)
        if current not in (None, session):
            raise MainHeld(current, f"cure-job {MAIN}-release {current}")
        path = store.root / _FILE
        try:
            with os.fdopen(os.open(path.with_suffix(".new"), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w",
                           encoding="utf-8") as f:
                f.write(session + "\n")
            os.replace(path.with_suffix(".new"), path)
        except OSError as e:
            raise StoreError(f"cannot write {path}: {e}") from e


def release(store: JobStore, session: str) -> None:
    """End the claim of ``session``. A claim another session holds stays."""
    with store.locked():
        if holder(store) == session:
            try:
                (store.root / _FILE).unlink()
            except OSError as e:
                raise StoreError(f"cannot remove {store.root / _FILE}: {e}") from e


def denial(store: JobStore, payload: Mapping[str, object], slots_root: str, worktree_root: str,
           cure_job: Path) -> str | None:
    """The reason to deny the tool call of the PreToolUse ``payload``, or ``None`` to allow it."""
    session = str(payload.get("session_id") or "")
    job_roots = [os.path.realpath(os.path.expanduser(root)) for root in (slots_root, worktree_root)]
    for target in _targets(payload):
        workspace = find_workspace(target)
        if workspace is None or any(_under(target, root) for root in job_roots):
            continue
        try:
            current = holder(store)
        except StoreError as e:
            return f"{target} is in the main workspace {workspace}, and the claim {MAIN} cannot be read: {e}"
        if current == session and session:
            return None
        held = (f"Session {current} holds it; wait for it to end, or run the change as a job. When session {current} "
                f"no longer runs, release its claim: {cure_job} {MAIN}-release {current}. ") if current else ""
        return (f"{target} is in the main workspace {workspace}; a write there needs the claim {MAIN}. {held}"
                f"Take the claim with: {cure_job} {MAIN}-claim {session}")
    return None


def _targets(payload: Mapping[str, object]) -> list[str]:
    """The directories or files the tool call writes in."""
    cwd = str(payload.get("cwd") or os.getcwd())
    tool_input = payload.get("tool_input")
    tool_input = tool_input if isinstance(tool_input, dict) else {}
    if payload.get("tool_name") in ("Edit", "Write"):
        path = tool_input.get("file_path")
        return [os.path.join(cwd, os.path.expanduser(path))] if isinstance(path, str) and path else []
    command = tool_input.get("command")
    if payload.get("tool_name") != "Bash" or not isinstance(command, str):
        return []
    found = []
    directory = cwd
    for segment in _SEPARATORS.split(command):
        try:
            words = shlex.split(segment)
        except ValueError:
            words = segment.split()
        while words and re.fullmatch(r"\w+=.*", words[0]):
            words.pop(0)
        if not words:
            continue
        name = os.path.basename(words[0])
        if name == "cd" and len(words) > 1:
            directory = os.path.join(directory, os.path.expanduser(words[1]))
        elif name == "bitbake":
            found.append(directory)
        elif name == "git":
            where, rest = _git(words[1:], directory)
            if rest and not _git_reads(rest[0], rest[1:]):
                found.append(where)
        elif name == "repo":
            subcommand = next((word for word in words[1:] if not word.startswith("-")), None)
            if subcommand is not None and subcommand not in REPO_READS:
                found.append(directory)
    return found


def _under(path: str, root: str) -> bool:
    return os.path.commonpath([os.path.realpath(path), root]) == root


def _git_reads(subcommand: str, args: list[str]) -> bool:
    if subcommand == "reflog":
        return not args or args[0] not in ("expire", "delete")
    if subcommand == "symbolic-ref":
        return not {"-d", "--delete"} & set(args) and len([arg for arg in args if not arg.startswith("-")]) <= 1
    if subcommand == "remote":
        return not args or args[0] in ("-v", "--verbose", "get-url", "show")
    if subcommand == "fetch":
        # The first word that is not an option names the repository, which may be a URL holding a colon.
        positional = [arg for arg in args if not arg.startswith("-")]
        return "--stdin" not in args and not any(":" in arg for arg in positional[1:])
    if subcommand == "tag":
        return args[:1] in (["-l"], ["--list"]) or all(_TAG_LIST_FLAGS.fullmatch(arg) for arg in args)
    if subcommand == "worktree":
        return args[:1] == ["list"]
    return subcommand in GIT_READS


def _git(words: list[str], directory: str) -> tuple[str, list[str]]:
    """The directory of the ``git`` arguments ``words`` and the words from its subcommand on."""
    index = 0
    while index < len(words) and words[index].startswith("-"):
        if words[index] == "-C" and index + 1 < len(words):
            directory = os.path.join(directory, os.path.expanduser(words[index + 1]))
            index += 1
        elif words[index] == "-c":
            index += 1
        index += 1
    return directory, words[index:]
