"""The result: what a job session reports in ``result.md``."""
from __future__ import annotations

import enum
import re
from dataclasses import dataclass

from .frontmatter import FrontmatterError, Value, as_list, is_writable, parse, render

STATUS = "status"
UNPROVEN = "unproven"
QUESTION = "question"
RETRO = "retro"
PR = "pr"
KEPT = "kept"

_DONE_WHEN_NUMBER = re.compile(r"[1-9][0-9]*")

#: The question a worker reports when its short-hold wait budget is spent.
SHORT_HOLD_TIMEOUT = "short-hold timeout:"
_HELD_BY = " held by "


class ResultStatus(enum.Enum):
    DONE = "done"
    FAILED = "failed"
    NEEDS_INPUT = "needs-input"


@dataclass(frozen=True)
class Result:
    status: ResultStatus
    unproven: tuple[str, ...]
    problem: str | None
    prs: tuple[str, ...] = ()
    questions: tuple[str, ...] = ()


@dataclass(frozen=True)
class ShortHoldTimeout:
    resource: str
    holder: str | None


def short_hold_timeout(result: Result) -> ShortHoldTimeout | None:
    """The timeout when the only question starts with ``short-hold timeout:``.

    The expected form is ``short-hold timeout: <resource> held by <holder id>``; without
    ``held by`` the holder is ``None``.
    """
    if len(result.questions) != 1 or not result.questions[0].startswith(SHORT_HOLD_TIMEOUT):
        return None
    rest = result.questions[0][len(SHORT_HOLD_TIMEOUT):]
    resource, held_by, holder = rest.rpartition(_HELD_BY)
    if not held_by:
        return ShortHoldTimeout(rest.strip(), None)
    return ShortHoldTimeout(resource.strip(), holder.strip())


@dataclass(frozen=True)
class Report:
    """What a job session reports through ``cure-job finish``. Valid by construction."""
    status: ResultStatus
    unproven: tuple[str, ...] = ()
    #: Written under the key ``question``.
    questions: tuple[str, ...] = ()
    retro: str | None = None
    prs: tuple[str, ...] = ()
    kept: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.unproven and self.status is not ResultStatus.DONE:
            raise ValueError("unproven needs status done")
        if self.status is ResultStatus.NEEDS_INPUT and not self.questions:
            raise ValueError(f"status {ResultStatus.NEEDS_INPUT.value} needs a question")
        for item in self.unproven:
            if not _DONE_WHEN_NUMBER.fullmatch(item):
                raise ValueError(f"unproven: {item} is not a done-when number")
        texts = (("questions", self.questions), ("retro", (self.retro,)), ("prs", self.prs), ("kept", self.kept))
        for field, values in texts:
            if not all(is_writable(value) for value in values if value is not None):
                raise ValueError(f"{field}: empty or more than one line")


def render_result(report: Report) -> str:
    """The text of ``result.md``. ``parse_result`` reads it back as ``report``'s status, unproven and prs."""
    entries: dict[str, Value] = {STATUS: report.status.value}
    optional: dict[str, Value | None] = {
        UNPROVEN: list(report.unproven), QUESTION: list(report.questions),
        RETRO: report.retro, PR: list(report.prs), KEPT: list(report.kept)}
    entries.update((key, value) for key, value in optional.items() if value)
    return render(entries)


def parse_result(text: str) -> Result:
    """Never raises: a job session wrote the file, and a malformed one needs the user."""
    try:
        entries = parse(text)
    except FrontmatterError as e:
        return _malformed(f"invalid frontmatter: {e}")
    status = entries.get(STATUS)
    if status is None:
        return _malformed("status is missing")
    try:
        return Result(ResultStatus(status), tuple(as_list(entries.get(UNPROVEN))), None,
                      tuple(as_list(entries.get(PR))), tuple(as_list(entries.get(QUESTION))))
    except ValueError:
        choices = ", ".join(member.value for member in ResultStatus)
        return _malformed(f"status is {status!r}; expected one of {choices}")


def _malformed(problem: str) -> Result:
    return Result(ResultStatus.NEEDS_INPUT, (), problem)
