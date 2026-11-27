"""The trust of a session directory in ``~/.claude.json``, the user file of Claude Code.

Claude Code asks the owner to trust each new directory, and the trust of a parent does not carry
over, so every start and resume of a job session first marks the directory the session starts in.
Claude Code writes the file too: it is reread right before the write, every other key is kept and
the file is replaced in one rename. An exclusive ``flock`` on the file's directory, the way the store
locks ``jobs/``, keeps two cure-job processes from dropping each other's entry.
"""
from __future__ import annotations

import contextlib
import fcntl
import json
import os
import stat
import tempfile

from .errors import CureJobError

CLAUDE_JSON = "~/.claude.json"
_ACCEPTED = "hasTrustDialogAccepted"


def mark_trusted(directory: str) -> None:
    """Set ``projects[<real path of directory>].hasTrustDialogAccepted`` unless it is already true.

    A missing file is left missing: Claude Code has not run under this home."""
    path = os.path.realpath(os.path.expanduser(CLAUDE_JSON))
    # Claude Code keys a project by getcwd, which resolves symlinks.
    directory = os.path.realpath(directory)
    try:
        lock = os.open(os.path.dirname(path), os.O_RDONLY | os.O_DIRECTORY)
    except FileNotFoundError:
        return
    except OSError as e:
        raise CureJobError(f"cannot mark {directory} trusted: {os.path.dirname(path)}: {e}") from e
    try:
        # Serialises cure-job processes only; Claude Code takes no such lock.
        fcntl.flock(lock, fcntl.LOCK_EX)
        _update(path, directory)
    except OSError as e:
        raise CureJobError(f"cannot mark {directory} trusted: {path}: {e}") from e
    finally:
        os.close(lock)


def _update(path: str, directory: str) -> None:
    try:
        with open(path, encoding="utf-8") as source:
            data = json.load(source)
        mode = stat.S_IMODE(os.stat(path).st_mode)
    except FileNotFoundError:
        return
    except (OSError, ValueError) as e:
        raise CureJobError(f"cannot mark {directory} trusted: {path}: {e}") from e
    projects = data.setdefault("projects", {}) if isinstance(data, dict) else None
    entry = projects.setdefault(directory, {}) if isinstance(projects, dict) else None
    if not isinstance(entry, dict):
        raise CureJobError(f"cannot mark {directory} trusted: {path}: the projects entry is not an object")
    if entry.get(_ACCEPTED) is True:
        return
    entry[_ACCEPTED] = True
    temporary = None
    try:
        descriptor, temporary = tempfile.mkstemp(prefix=".claude.json.", dir=os.path.dirname(path))
        with os.fdopen(descriptor, "w", encoding="utf-8") as sink:
            os.fchmod(sink.fileno(), mode)
            json.dump(data, sink, indent=2, ensure_ascii=False)
        os.replace(temporary, path)
    except BaseException as e:
        if temporary is not None:
            with contextlib.suppress(OSError):
                os.unlink(temporary)
        if isinstance(e, OSError):
            raise CureJobError(f"cannot mark {directory} trusted: {path}: {e}") from e
        raise
