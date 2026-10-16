"""The job id format: ``<yymmdd>-<hhmm>-<repo>-<slug>``.

The id is also the directory name and the session name, and its string order is
the lock order, so every rule about its shape lives here.
"""
from __future__ import annotations

import re
from datetime import datetime

MAX_LENGTH = 60
MAX_SUFFIX = 99

_NOT_SLUG = re.compile(r"[^a-z0-9]+")
_VALID = re.compile(r"[0-9]{6}-[0-9]{4}(-[a-z0-9]+)+")
_RUN_MARKER = re.compile(r"(^|-)r[0-9]+$")


def slugify(text: str) -> str:
    """Lowercase ``text`` and join its ``[a-z0-9]`` runs with ``-``. May return ``""``."""
    return _NOT_SLUG.sub("-", text.lower()).strip("-")


def ends_in_run_marker(slug: str) -> bool:
    """True when ``slugify(slug)`` ends as a session name of a later run does.
    The id would then equal the session name of another job: ``<id>-r<n>``."""
    return _RUN_MARKER.search(slugify(slug)) is not None


def make_id(created: datetime, repo: str, slug: str) -> str:
    repo_slug = slugify(repo)
    name_slug = slugify(slug)
    if not repo_slug:
        raise ValueError(f"repository name {repo!r} has no character in [a-z0-9]")
    if not name_slug:
        raise ValueError(f"slug {slug!r} has no character in [a-z0-9]")
    return f"{created:%y%m%d-%H%M}-{repo_slug}-{name_slug}"[:MAX_LENGTH].rstrip("-")


def with_suffix(base: str, n: int) -> str:
    """``base`` with the collision suffix ``-n``, shortened so the id still fits."""
    suffix = f"-{n}"
    return base[:MAX_LENGTH - len(suffix)].rstrip("-") + suffix


def is_valid(text: str) -> bool:
    return len(text) <= MAX_LENGTH and _VALID.fullmatch(text) is not None


def session_name(job_id: str, run: int) -> str:
    return job_id if run == 1 else f"{job_id}-r{run}"
