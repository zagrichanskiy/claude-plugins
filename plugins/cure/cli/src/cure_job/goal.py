"""The goal file: its digest, its tier, and the plugin paths in it.

An approval names the sha256 of the goal file's bytes, so any edit of the file
revokes it. A goal file names files of the cure plugin by the path of the version that
wrote it, ``.../plugins/cache/<marketplace>/cure/<version>/``. A plugin update
can remove that directory, so ``launch`` points each such path at the plugin
this CLI belongs to.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from .config import TIERS

#: <root>/cli/src/cure_job/goal.py: plugins/cure/ in a checkout, the version
#: directory in the plugin cache.
PLUGIN_ROOT = Path(__file__).resolve().parents[3]

#: The rules every goal file names in its read-first line, relative to the
#: plugin root. ``launch`` refuses while it is missing.
RULES = Path("skills", "goal", "rules.md")

# Starts at "/" or "~", so a leading "@" or quote stays in place.
_CACHED_ROOT = re.compile(r"[/~][^\s\"'`<>()\[\]]*?/plugins/cache/[^/\s]+/cure/[^/\s]+/")

_RULES_HEADING = re.compile(r"^## Rules[ \t]*$", re.MULTILINE)
_NEXT_HEADING = re.compile(r"^#{1,2} ", re.MULTILINE)
_TIER_LINE = re.compile(r"^(?:[-*] )?Tier: (\w+)\b", re.MULTILINE)


def tier(text: str) -> str | None:
    """The tier the first ``Tier:`` line of the Rules section names, or None when no line names one of :data:`TIERS`."""
    heading = _RULES_HEADING.search(text)
    if heading is None:
        return None
    following = _NEXT_HEADING.search(text, heading.end())
    match = _TIER_LINE.search(text, heading.end(), following.start() if following else len(text))
    if match is None or match.group(1) not in TIERS:
        return None
    return match.group(1)


def retarget(text: str, plugin_root: Path) -> str:
    """``text`` with each cached cure plugin root replaced by ``plugin_root``."""
    replacement = str(plugin_root).rstrip("/") + "/"
    return _CACHED_ROOT.sub(lambda match: replacement, text)


def digest(data: bytes) -> str:
    """The digest an ``approved`` event names for a goal file of ``data``."""
    return "sha256:" + hashlib.sha256(data).hexdigest()
