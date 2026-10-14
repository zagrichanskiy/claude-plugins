"""The handoff: the two fields of ``handoff.md`` that the CLI consumes.

``repos`` and ``device`` name the resources a job locks. Every other field and
section belongs to the dispatcher and is not checked here.
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

    @property
    def launch_dir(self) -> str:
        return self.repos[0]

    @property
    def resources(self) -> frozenset[str]:
        names = set(self.repos)
        if self.device is Device.BENCH:
            names.add(resource.DEVICE_BENCH)
        return frozenset(names)


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
    device = entries.get("device")
    try:
        return Handoff(repos=tuple(repos), device=Device(device))
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
