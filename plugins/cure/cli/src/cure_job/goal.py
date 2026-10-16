"""Plugin paths in a goal file.

A goal file names files of the cure plugin by the path of the version that
wrote it, ``.../plugins/cache/<marketplace>/cure/<version>/``. A plugin update
can remove that directory, so ``launch`` points each such path at the plugin
this CLI belongs to.
"""
from __future__ import annotations

import re
from pathlib import Path

#: <root>/cli/src/cure_job/goal.py: plugins/cure/ in a checkout, the version
#: directory in the plugin cache.
PLUGIN_ROOT = Path(__file__).resolve().parents[3]

#: The rules every goal file names in its read-first line, relative to the
#: plugin root. ``launch`` refuses while it is missing.
RULES = Path("skills", "goal", "rules.md")

# Starts at "/" or "~", so a leading "@" or quote stays in place.
_CACHED_ROOT = re.compile(r"[/~][^\s\"'`<>()\[\]]*?/plugins/cache/[^/\s]+/cure/[^/\s]+/")


def retarget(text: str, plugin_root: Path) -> str:
    """``text`` with each cached cure plugin root replaced by ``plugin_root``."""
    replacement = str(plugin_root).rstrip("/") + "/"
    return _CACHED_ROOT.sub(lambda match: replacement, text)
