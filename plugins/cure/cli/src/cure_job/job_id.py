"""The job id formats: ``<ticket>-<repo>-<slug>`` when the handoff names a ticket, else
``<yymmdd>-<hhmm>-<repo>-<slug>``.

The ticket part is ``issue-<n>`` for a GitHub issue (``owner/repo#<n>``, ``#<n>`` or its
``github.com`` URL) and the lowercased key for a tracker key such as ``ABC-123``. Any other ticket
text, a tracker URL included, gives the time format. A cut to the length limit shortens the repository
and the slug and keeps both.
The id is also the directory name and the session name, so every rule about its shape lives here.
"""
from __future__ import annotations

import re
from datetime import datetime

MAX_LENGTH = 60
MAX_SUFFIX = 99

_NOT_SLUG = re.compile(r"[^a-z0-9]+")
_VALID = re.compile(r"[0-9]{6}-[0-9]{4}(-[a-z0-9]+)+|[a-z][a-z0-9]*-[0-9]+(-[a-z0-9]+){2,}")
_GITHUB_ISSUE = re.compile(r"(?:[\w.-]+/[\w.-]+)?#([0-9]+)|https://github\.com/[\w.-]+/[\w.-]+/issues/([0-9]+)/?")
_TRACKER_KEY = re.compile(r"[A-Za-z][A-Za-z0-9]*-[0-9]+")
_PREFIX = re.compile(r"[0-9]{6}-[0-9]{4}-|[a-z][a-z0-9]*-[0-9]+-")
_RUN_MARKER = re.compile(r"(^|-)r[0-9]+$")


def slugify(text: str) -> str:
    """Lowercase ``text`` and join its ``[a-z0-9]`` runs with ``-``. May return ``""``."""
    return _NOT_SLUG.sub("-", text.lower()).strip("-")


def ends_in_run_marker(slug: str) -> bool:
    """True when ``slugify(slug)`` ends as a session name of a later run does.
    The id would then equal the session name of another job: ``<id>-r<n>``."""
    return _RUN_MARKER.search(slugify(slug)) is not None


def make_id(created: datetime, repo: str, slug: str, ticket: str | None = None) -> str:
    repo_slug = slugify(repo)
    name_slug = slugify(slug)
    if not repo_slug:
        raise ValueError(f"repository name {repo!r} has no character in [a-z0-9]")
    if not name_slug:
        raise ValueError(f"slug {slug!r} has no character in [a-z0-9]")
    part = _ticket_part(ticket or "")
    if part is not None:
        # A ticket part too long to leave room for the repository and the slug fails the check.
        with_ticket = _join(part, repo_slug, name_slug)
        if is_valid(with_ticket):
            return with_ticket
    return _join(f"{created:%y%m%d-%H%M}", repo_slug, name_slug)


def _join(prefix: str, repo_slug: str, name_slug: str) -> str:
    """``<prefix>-<repo>-<slug>`` within the limit. The slug keeps its full length where the room allows,
    else at least half the room; the repository takes the rest."""
    room = MAX_LENGTH - len(prefix) - 2
    name = name_slug[:max(room - len(repo_slug), room // 2)].rstrip("-")
    repo = repo_slug[:room - len(name)].rstrip("-")
    return f"{prefix}-{repo}-{name}"


def slug_of(job_id: str, repo: str) -> str | None:
    """The slug part of ``job_id``, a job of ``repo``, as :func:`_join` cut it, with any collision suffix;
    ``None`` when the id does not hold the repository part.

    An id whose repository part was cut is ambiguous when the slug starts with text that continues the
    repository name up to a hyphen: that text is read as part of the repository, and the returned slug
    lacks it."""
    prefix = _PREFIX.match(job_id)
    repo_slug = slugify(repo)
    rest = job_id[prefix.end():] if prefix is not None else ""
    # Longest first: the cut shortens the repository only as far as it must.
    for end in range(len(repo_slug), 0, -1):
        part = repo_slug[:end].rstrip("-") + "-"
        if rest.startswith(part) and len(rest) > len(part):
            return rest[len(part):]
    return None


def _ticket_part(ticket: str) -> str | None:
    text = ticket.strip()
    issue = _GITHUB_ISSUE.fullmatch(text)
    if issue is not None:
        return f"issue-{int(issue[1] or issue[2])}"
    return text.lower() if _TRACKER_KEY.fullmatch(text) else None


def with_suffix(base: str, n: int) -> str:
    """``base`` with the collision suffix ``-n``, shortened so the id still fits."""
    suffix = f"-{n}"
    return base[:MAX_LENGTH - len(suffix)].rstrip("-") + suffix


def is_valid(text: str) -> bool:
    return len(text) <= MAX_LENGTH and _VALID.fullmatch(text) is not None


def session_name(job_id: str, run: int) -> str:
    return job_id if run == 1 else f"{job_id}-r{run}"
