"""The claim ``main``: the one interactive session that may write in the main workspace.

The main workspace is a ``repo`` tool workspace that is not a slot, that is, whose parent is not ``slots.root``.
The claim is the file ``main-claim`` in the state root, holding the session id. An Edit or a Write of a file in the
main workspace needs the claim. A Bash command that runs there, or names a path there in any word, needs the claim
unless it is one simple command of :data:`_READS`, or ``cure-job main-claim`` or ``main-release``, without a
character of :data:`_METACHARACTERS`. A target under ``slots.root``, ``worktree.root`` or the worktree root a job
recorded is never in the main workspace, even where that root lies inside it.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Mapping

from .errors import MainHeld, StoreError
from .slot import find_workspace
from .store import JobStore

MAIN = "main"
_FILE = "main-claim"

_METACHARACTERS = ";&|<>`$\n"

_READS = frozenset({"ls", "cat", "head", "tail", "grep", "rg", "find", "wc", "stat", "file"})

_GIT_READS = frozenset({"status", "log", "diff", "show", "branch", "rev-parse", "ls-files", "grep", "blame"})

_BRANCH_LISTS = frozenset({"-a", "--all", "-r", "--remotes", "-v", "-vv", "--verbose", "-l", "--list",
                           "--show-current"})

_FIND_ACTIONS = frozenset({"-exec", "-execdir", "-ok", "-okdir", "-delete", "-fprint", "-fprint0", "-fprintf", "-fls"})

# Each piece that may name a path: the shell may cut words at these characters, and an option may carry its value
# after ``=``.
_PIECES = re.compile(r"[^\s;&|<>()`'\"=]+")


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
    recorded: list[str] | None = None
    for target in _targets(payload, cure_job):
        workspace = find_workspace(target)
        if workspace is None or any(_under(target, root) for root in job_roots):
            continue
        if recorded is None:
            recorded = _recorded_roots(store)
        if any(_under(target, root) for root in recorded):
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


def _recorded_roots(store: JobStore) -> list[str]:
    """The worktree root each job recorded at its launch, which a later change of ``worktree.root`` leaves in use.
    A store that does not read exempts no root, so the write needs the claim."""
    try:
        records = store.load_all()
    except StoreError:
        return []
    return [os.path.realpath(record.worktree_root) for record in records if record.worktree_root is not None]


def _targets(payload: Mapping[str, object], cure_job: Path) -> list[str]:
    """The directories or files the tool call touches without the claim."""
    cwd = str(payload.get("cwd") or os.getcwd())
    tool_input = payload.get("tool_input")
    tool_input = tool_input if isinstance(tool_input, dict) else {}
    if payload.get("tool_name") in ("Edit", "Write"):
        path = tool_input.get("file_path")
        return [os.path.join(cwd, os.path.expanduser(path))] if isinstance(path, str) and path else []
    command = tool_input.get("command")
    if payload.get("tool_name") != "Bash" or not isinstance(command, str) or _allowed(command, cure_job):
        return []
    pieces = _PIECES.findall(command)
    # A short option may carry its value without a space, as in ``-C/path``.
    pieces += [piece[2:] for piece in pieces if piece[:1] == "-" and piece[1:2] not in ("-", "")]
    return [cwd, *(os.path.join(cwd, os.path.expandvars(os.path.expanduser(piece))) for piece in pieces)]


def _allowed(command: str, cure_job: Path) -> bool:
    if any(char in command for char in _METACHARACTERS):
        return False
    # Quotes and backslashes join a word without changing it, so ``'--output=f'`` is still that option.
    words = re.sub(r"[\\'\"]", "", command).split()
    if not words:
        return True
    if words[0] == str(cure_job):
        return words[1:2] in ([f"{MAIN}-claim"], [f"{MAIN}-release"])
    if words[0] == "git":
        return words[1:] == ["remote", "-v"] or len(words) > 1 and _git_reads(words[1], words[2:])
    if words[0] == "find":
        return not any(word in _FIND_ACTIONS for word in words)
    if words[0] == "rg":
        return not any(word.split("=")[0] in ("--pre", "--pre-glob", "--hostname-bin") for word in words)
    if words[0] == "file":
        return not any(_short(word, "C") or _long(word, "--compile") for word in words[1:])
    return words[0] in _READS


def _git_reads(subcommand: str, args: list[str]) -> bool:
    if any(_long(arg, "--output") or _long(arg, "--open-files-in-pager") for arg in args):
        return False
    if subcommand == "branch":
        return all(arg in _BRANCH_LISTS for arg in args)
    if subcommand == "grep" and any(_short(arg, "O") for arg in args):
        return False
    return subcommand in _GIT_READS


def _short(word: str, letter: str) -> bool:
    """Whether ``word`` holds the short option ``-<letter>``, alone or bundled with others."""
    return word[:1] == "-" and word[1:2] != "-" and letter in word


def _long(word: str, option: str) -> bool:
    """Whether ``word`` may be the long ``option``. Git and ``file`` accept an unambiguous prefix of a long option,
    such as ``--outp`` for ``--output``."""
    name = word.split("=")[0]
    return name.startswith("--") and (len(name) > 2 and option.startswith(name) or name.startswith(option))


def _under(path: str, root: str) -> bool:
    try:
        return os.path.commonpath([os.path.realpath(path), root]) == root
    except (OSError, ValueError):
        return False
