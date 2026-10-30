"""The handoff: the fields of ``handoff.md`` that the CLI consumes.

``repos`` names the resources a job locks. ``device`` declares bench use; the
bench is a short hold the job claims per step. ``origin``, optional,
names the session the job reports back to; ``cure-job new`` writes it, and a
submitted handoff that names it is refused. ``after``, optional, names the
job this one is stacked on. ``ticket``, ``ticket-summary`` and ``branch``,
optional, are read for ``cure-job list``. Every other field and section
belongs to the dispatcher and is not checked here.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime

from . import job_id as ids
from . import resource
from .clock import format_local
from .errors import HandoffError
from .frontmatter import FrontmatterError, Value, as_list, is_writable, parse, render_value, set_scalars

ORIGIN = "origin"
TICKET_SUMMARY = "ticket-summary"


class Device(enum.Enum):
    BENCH = "bench"
    NONE = "none"


@dataclass(frozen=True)
class Handoff:
    repos: tuple[str, ...]
    device: Device
    origin: str | None = None
    after: str | None = None
    ticket: str | None = None
    ticket_summary: str | None = None
    branch: str | None = None

    @property
    def launch_dir(self) -> str:
        return self.repos[0]

    @property
    def resources(self) -> frozenset[str]:
        return frozenset(self.repos)


def parse_handoff(text: str) -> Handoff:
    return _handoff(_entries(text))


def parse_submitted(text: str) -> Handoff:
    """The handoff ``cure-job new`` receives. It must not name the origin, which ``new`` binds."""
    entries = _entries(text)
    if ORIGIN in entries:
        raise HandoffError(f"{ORIGIN} is set; cure-job new binds the origin itself, so remove the entry")
    return _handoff(entries)


def _entries(text: str) -> dict[str, Value]:
    try:
        return parse(text)
    except FrontmatterError as e:
        raise HandoffError(f"invalid frontmatter: {e}") from e


def _handoff(entries: dict[str, Value]) -> Handoff:
    repos: list[str] = []
    for entry in as_list(entries.get("repos")):
        try:
            name = resource.repo(entry)
        except ValueError as e:
            raise HandoffError(f"repos: {e}") from e
        if name not in repos:
            repos.append(name)
    if not repos:
        raise HandoffError("repos is missing or empty")
    origin = entries.get(ORIGIN)
    if isinstance(origin, list):
        raise HandoffError("origin is a list; expected one session name")
    after = entries.get("after") or None
    if isinstance(after, list):
        raise HandoffError("after is a list; expected one job id")
    if after is not None and not ids.is_valid(after):
        raise HandoffError(f"after is {after!r}; expected a job id")
    ticket, ticket_summary, branch = (_scalar(entries, key) for key in ("ticket", TICKET_SUMMARY, "branch"))
    device = entries.get("device")
    try:
        return Handoff(repos=tuple(repos), device=Device(device), origin=origin or None, after=after,
                       ticket=ticket, ticket_summary=ticket_summary, branch=branch)
    except ValueError:
        choices = " or ".join(member.value for member in Device)
        if device is None:
            raise HandoffError(f"device is missing; expected {choices}") from None
        raise HandoffError(f"device is {device!r}; expected {choices}") from None


def _scalar(entries: dict[str, Value], key: str) -> str | None:
    value = entries.get(key) or None
    if isinstance(value, list):
        raise HandoffError(f"{key} is a list; expected one line of text")
    return value


def stamp(text: str, job_id: str, created: datetime, origin: str | None = None,
          ticket_summary: str | None = None) -> str:
    """``text`` with the ``id``, ``created`` and, when given, ``origin`` entries the CLI owns,
    and ``ticket-summary`` when given."""
    values = {"id": job_id, "created": format_local(created)}
    if origin is not None:
        if not is_writable(origin):
            raise HandoffError(f"{ORIGIN} {origin!r} is empty, padded or more than one line")
        values[ORIGIN] = origin
    try:
        if ticket_summary is not None:
            values[TICKET_SUMMARY] = render_value(TICKET_SUMMARY, ticket_summary)
        return set_scalars(text, values)
    except FrontmatterError as e:
        raise HandoffError(f"invalid frontmatter: {e}") from e
