"""The handoff: the fields of ``handoff.md`` that the CLI consumes.

``repos`` names the resources a job locks. ``device`` declares bench use; the
bench is a short hold the job claims per step. ``origin``, optional,
names the session the job reports back to. Every other field and section
belongs to the dispatcher and is not checked here.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime

from . import resource
from .clock import format_local
from .errors import HandoffError
from .frontmatter import FrontmatterError, as_list, parse, set_scalars


class Device(enum.Enum):
    BENCH = "bench"
    NONE = "none"


@dataclass(frozen=True)
class Handoff:
    repos: tuple[str, ...]
    device: Device
    origin: str | None = None

    @property
    def launch_dir(self) -> str:
        return self.repos[0]

    @property
    def resources(self) -> frozenset[str]:
        return frozenset(self.repos)


def parse_handoff(text: str) -> Handoff:
    try:
        entries = parse(text)
    except FrontmatterError as e:
        raise HandoffError(f"invalid frontmatter: {e}") from e
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
    origin = entries.get("origin")
    if isinstance(origin, list):
        raise HandoffError("origin is a list; expected one session name")
    device = entries.get("device")
    try:
        return Handoff(repos=tuple(repos), device=Device(device), origin=origin or None)
    except ValueError:
        choices = " or ".join(member.value for member in Device)
        if device is None:
            raise HandoffError(f"device is missing; expected {choices}") from None
        raise HandoffError(f"device is {device!r}; expected {choices}") from None


def stamp(text: str, job_id: str, created: datetime) -> str:
    """``text`` with the ``id`` and ``created`` entries the CLI owns."""
    try:
        return set_scalars(text, {"id": job_id, "created": format_local(created)})
    except FrontmatterError as e:
        raise HandoffError(f"invalid frontmatter: {e}") from e
