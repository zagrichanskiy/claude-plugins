"""Every read and write under the state root.

``JobStore`` is the state-root seam: production code builds it on
``~/.claude/cure`` and a test builds it on a temporary directory. The layout is
``<root>/jobs/<id>/`` with ``handoff.md``, ``goal.md``, ``dispatch.jsonl``,
``result.md`` and ``result-<run>.md``.
"""
from __future__ import annotations

import contextlib
import errno
import fcntl
import os
import re
import shutil
import stat
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterator, NamedTuple, Sequence

from . import job_id as ids
from .errors import HandoffError, StoreError, UnknownJob
from .events import Event, decode, encode
from .goal import digest
from .handoff import Handoff, parse_handoff
from .job import JobRecord
from .result import parse_result

_JOBS = "jobs"
_HANDOFF = "handoff.md"
_GOAL = "goal.md"
_EVENTS = "dispatch.jsonl"
_RESULT = "result.md"
_ENCODING = "utf-8"
_NEW_PREFIX = ".new-"
_ARCHIVED = re.compile(r"result-([1-9][0-9]*)\.md")


class HalfCreated(NamedTuple):
    """A directory an interrupted ``new`` left: ``jobs/.new-*`` or an empty ``jobs/<id>``."""
    path: Path
    #: The directory's own mtime, aware UTC.
    mtime: datetime


class InvalidJob(NamedTuple):
    """A jobs/<id> whose stored files cannot be read. Its state and resources are unknown."""
    id: str
    dir: Path
    #: The error. It names the file.
    problem: str


class Snapshot(NamedTuple):
    records: list[JobRecord]
    invalid: list[InvalidJob]


class JobStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self._jobs = self.root / _JOBS

    def job_dir(self, job_id: str) -> Path:
        if not ids.is_valid(job_id):
            raise ValueError(f"invalid job id {job_id!r}")
        return self._jobs / job_id

    def goal_path(self, job_id: str) -> Path:
        return self.job_dir(job_id) / _GOAL

    def result_path(self, job_id: str) -> Path:
        return self.job_dir(job_id) / _RESULT

    def create(self, base_id: str, render: Callable[[str], str]) -> str:
        """Reserve the first free id from ``base_id`` on, write ``render(id)`` as its handoff."""
        with _store_errors(self._jobs):
            os.makedirs(self._jobs, exist_ok=True)
        job_id = self._reserve(base_id)
        reserved = self.job_dir(job_id)
        staging = None
        try:
            with _store_errors(reserved):
                staging = tempfile.mkdtemp(prefix=_NEW_PREFIX, dir=self._jobs)
                Path(staging, _HANDOFF).write_text(render(job_id), encoding=_ENCODING)
                # POSIX rename replaces the empty reserved directory in one
                # step, so a job directory never appears without handoff.md.
                os.rename(staging, reserved)
        except BaseException:
            if staging is not None:
                shutil.rmtree(staging, ignore_errors=True)
            shutil.rmtree(reserved, ignore_errors=True)
            raise
        return job_id

    def load(self, job_id: str) -> JobRecord:
        record = self._read(job_id)
        if record is None:
            raise UnknownJob(f"unknown job {job_id}: {self.job_dir(job_id) / _HANDOFF} does not exist")
        return record

    def load_all(self) -> list[JobRecord]:
        """The readable jobs, ascending id."""
        return self.snapshot().records

    def snapshot(self) -> Snapshot:
        """Every job, ascending id. A job whose files do not read is an :class:`InvalidJob`."""
        try:
            with _store_errors(self._jobs):
                names = sorted(os.listdir(self._jobs))
        except StoreError as e:
            if isinstance(e.__cause__, FileNotFoundError):
                return Snapshot([], [])
            raise
        records, invalid = [], []
        for name in names:
            # An interrupted `new` leaves an empty jobs/<id> or a jobs/.new-*
            # directory. Neither is a job.
            if not ids.is_valid(name) or not (self._jobs / name).is_dir():
                continue
            try:
                record = self._read(name)
            except (HandoffError, StoreError) as e:
                invalid.append(InvalidJob(name, self._jobs / name, str(e)))
                continue
            if record is not None:
                records.append(record)
        return Snapshot(records, invalid)

    @contextlib.contextmanager
    def locked(self) -> Iterator[None]:
        """Hold an exclusive ``flock`` on the ``jobs/`` directory. Creates no lock file."""
        with _store_errors(self._jobs):
            os.makedirs(self._jobs, exist_ok=True)
            descriptor = os.open(self._jobs, os.O_RDONLY | os.O_DIRECTORY)
        try:
            with _store_errors(self._jobs):
                fcntl.flock(descriptor, fcntl.LOCK_EX)
            yield
        finally:
            # Closing the descriptor releases the lock.
            os.close(descriptor)

    def append_event(self, job_id: str, event: Event) -> None:
        self.append_events(job_id, [event])

    def append_events(self, job_id: str, events: Sequence[Event]) -> None:
        """Append ``events`` in one write: a failed write records none of them."""
        if not events:
            return
        path = self.job_dir(job_id) / _EVENTS
        line = "".join(encode(event) + "\n" for event in events).encode(_ENCODING)
        with _store_errors(path):
            descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
            try:
                # One write call on an O_APPEND descriptor: a concurrent
                # command cannot interleave inside the lines.
                os.write(descriptor, line)
            finally:
                os.close(descriptor)

    def archive_result(self, job_id: str, run: int) -> bool:
        """Rename ``result.md`` to ``result-<run>.md``. False when there is no ``result.md``."""
        directory = self.job_dir(job_id)
        try:
            with _store_errors(directory / _RESULT):
                os.rename(directory / _RESULT, directory / _archived(run))
        except StoreError as e:
            if isinstance(e.__cause__, FileNotFoundError):
                return False
            raise
        return True

    def write_result(self, job_id: str, text: str) -> bool:
        """Publish ``text`` as ``result.md`` in one step. False when ``result.md`` exists."""
        target = self.result_path(job_id)
        with _store_errors(target.parent):
            descriptor, temp = tempfile.mkstemp(prefix=".result-", suffix=".tmp", dir=target.parent)
        try:
            with _store_errors(Path(temp)):
                with os.fdopen(descriptor, "w", encoding=_ENCODING) as sink:
                    sink.write(text)
            # link, not rename: rename would replace a result.md written since
            # the caller's check, and that result would be lost.
            try:
                with _store_errors(target):
                    os.link(temp, target)
            except StoreError as e:
                if isinstance(e.__cause__, FileExistsError):
                    return False
                raise
        finally:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(temp)
        return True

    def rewrite_goal(self, job_id: str, change: Callable[[str], str]) -> bool:
        """Replace ``goal.md`` with ``change(text)`` in one step. False when the text is unchanged."""
        target = self.goal_path(job_id)
        text, _ = _read_text(target)
        if text is None:
            raise UnknownJob(f"job {job_id}: {target} does not exist")
        changed = change(text)
        if changed == text:
            return False
        with _store_errors(target):
            descriptor, temp = tempfile.mkstemp(prefix=".goal-", suffix=".tmp", dir=target.parent)
            try:
                with os.fdopen(descriptor, "w", encoding=_ENCODING) as sink:
                    sink.write(changed)
                os.chmod(temp, stat.S_IMODE(os.stat(target).st_mode))
                os.replace(temp, target)
            except BaseException:
                with contextlib.suppress(FileNotFoundError):
                    os.unlink(temp)
                raise
        return True

    def restore_result(self, job_id: str, run: int) -> None:
        directory = self.job_dir(job_id)
        with _store_errors(directory / _archived(run)):
            os.rename(directory / _archived(run), directory / _RESULT)

    def remove(self, job_id: str) -> None:
        directory = self.job_dir(job_id)
        with _store_errors(directory):
            shutil.rmtree(directory)

    def half_created(self) -> list[HalfCreated]:
        """Each ``jobs/.new-*`` directory and each empty ``jobs/<id>`` directory, ascending name."""
        try:
            with _store_errors(self._jobs):
                names = sorted(os.listdir(self._jobs))
        except StoreError as e:
            if isinstance(e.__cause__, FileNotFoundError):
                return []
            raise
        entries = []
        for name in names:
            path = self._jobs / name
            if not (name.startswith(_NEW_PREFIX) or ids.is_valid(name)):
                continue
            try:
                with _store_errors(path):
                    # lstat: a symlink is never followed, so never removed through.
                    status = os.lstat(path)
                    if not stat.S_ISDIR(status.st_mode):
                        continue
                    if not name.startswith(_NEW_PREFIX) and os.listdir(path):
                        continue
            except StoreError as e:
                if isinstance(e.__cause__, FileNotFoundError):
                    continue
                raise
            entries.append(HalfCreated(path, datetime.fromtimestamp(status.st_mtime, timezone.utc)))
        return entries

    def remove_half_created(self, entry: HalfCreated) -> bool:
        """True when removed. False when the directory is gone or a concurrent ``new`` filled it."""
        if entry.path.parent != self._jobs:
            raise ValueError(f"{entry.path} is not directly under {self._jobs}")
        try:
            with _store_errors(entry.path):
                if entry.path.name.startswith(_NEW_PREFIX):
                    shutil.rmtree(entry.path)
                else:
                    # rmdir fails on a non-empty directory, so a job that
                    # appeared since the listing is kept.
                    os.rmdir(entry.path)
        except StoreError as e:
            cause = e.__cause__
            if isinstance(cause, FileNotFoundError) or (
                    isinstance(cause, OSError) and cause.errno in (errno.ENOTEMPTY, errno.EEXIST)):
                return False
            raise
        return True

    def _reserve(self, base_id: str) -> str:
        candidates = [base_id] + [ids.with_suffix(base_id, n) for n in range(2, ids.MAX_SUFFIX + 1)]
        for candidate in candidates:
            path = self.job_dir(candidate)
            try:
                with _store_errors(path):
                    # No parents and no exist_ok: the failure is how a collision is detected.
                    os.mkdir(path)
            except StoreError as e:
                if isinstance(e.__cause__, FileExistsError):
                    continue
                raise
            return candidate
        raise StoreError(f"no free job id: {self.job_dir(base_id)} and its suffixes up to "
                         f"-{ids.MAX_SUFFIX} exist")

    def _read(self, job_id: str) -> JobRecord | None:
        """The record of ``job_id``, or ``None`` when it has no ``handoff.md``."""
        directory = self.job_dir(job_id)
        handoff_text, _ = _read_text(directory / _HANDOFF)
        if handoff_text is None:
            return None
        events, events_mtime = self._read_events(directory / _EVENTS)
        result_text, result_mtime = _read_text(directory / _RESULT)
        return JobRecord(
            id=job_id,
            dir=directory,
            handoff=_parse_stored_handoff(directory / _HANDOFF, handoff_text),
            goal_digest=_goal_digest(directory / _GOAL),
            events=events,
            result=None if result_text is None else parse_result(result_text),
            result_mtime=result_mtime,
            events_mtime=events_mtime,
            archived_runs=_archived_runs(directory))

    def _read_events(self, path: Path) -> tuple[tuple[Event, ...], datetime | None]:
        text, mtime = _read_text(path)
        events = []
        for number, line in enumerate((text or "").splitlines(), start=1):
            if not line.strip():
                continue
            try:
                event = decode(line)
            except ValueError as e:
                raise StoreError(f"{path}:{number}: invalid event: {e}") from e
            if event is not None:
                events.append(event)
        return tuple(events), mtime


def _archived(run: int) -> str:
    return f"result-{run}.md"


def _archived_runs(directory: Path) -> frozenset[int]:
    try:
        with _store_errors(directory):
            names = os.listdir(directory)
    except StoreError as e:
        # The job directory was removed or replaced while it was read.
        if isinstance(e.__cause__, (FileNotFoundError, NotADirectoryError)):
            return frozenset()
        raise
    return frozenset(int(match.group(1)) for match in map(_ARCHIVED.fullmatch, names) if match)


def _goal_digest(path: Path) -> str | None:
    try:
        with _store_errors(path):
            with open(path, "rb") as source:
                return digest(source.read())
    except StoreError as e:
        if isinstance(e.__cause__, (FileNotFoundError, NotADirectoryError)):
            return None
        raise


def _parse_stored_handoff(path: Path, text: str) -> Handoff:
    try:
        return parse_handoff(text)
    except HandoffError as e:
        raise HandoffError(f"{path}: {e}") from e


def _read_text(path: Path) -> tuple[str | None, datetime | None]:
    """The text and the mtime of ``path``, or ``(None, None)`` when it is absent."""
    try:
        with _store_errors(path):
            with open(path, encoding=_ENCODING) as source:
                # fstat on the open file: the mtime belongs to the text read.
                mtime = os.fstat(source.fileno()).st_mtime
                return source.read(), datetime.fromtimestamp(mtime, timezone.utc)
    except StoreError as e:
        # NotADirectoryError: the job directory was replaced while it was read.
        if isinstance(e.__cause__, (FileNotFoundError, NotADirectoryError)):
            return None, None
        raise


@contextlib.contextmanager
def _store_errors(path: Path) -> Iterator[None]:
    """Turn an ``OSError``, or undecodable text, into a ``StoreError`` that names ``path``."""
    try:
        yield
    except OSError as e:
        raise StoreError(f"{path}: {e.strerror or e}") from e
    except UnicodeDecodeError as e:
        raise StoreError(f"{path}: not UTF-8: {e}") from e
