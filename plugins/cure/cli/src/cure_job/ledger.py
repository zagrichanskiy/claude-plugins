"""The job ledger: one JSON object per line, the job record that ``finish`` appends.

Tokens come from the session transcripts under the Claude Code projects root, ``<project>/<uuid>.jsonl``, and their
subagent transcripts, ``<project>/<uuid>/subagents/*.jsonl``. A value no transcript gives is ``None``, never 0.
"""
from __future__ import annotations

import glob
import json
import os
import re
from pathlib import Path
from typing import Iterable, Mapping, NamedTuple

_USAGE_KEYS = (("input", "input_tokens"), ("output", "output_tokens"),
               ("cache_creation", "cache_creation_input_tokens"), ("cache_read", "cache_read_input_tokens"))
_SETTLED_HEADING = re.compile(r"^## Settled[ \t]*$", re.MULTILINE)
_NEXT_HEADING = re.compile(r"^#{1,2} ", re.MULTILINE)
_ESTIMATE_LINE = re.compile(r"^[-*] Estimate: ~?(\d+) changed lines\b", re.MULTILINE)


class Usage(NamedTuple):
    input: int | None
    output: int | None
    cache_creation: int | None
    cache_read: int | None
    #: The assistant messages that carry a usage.
    turns: int | None


def read_usage(paths: Iterable[Path]) -> Usage:
    """The tokens by type of the assistant messages in ``paths``. A message streamed over several lines shares one
    ``message.id`` and counts once, with its last usage. A sidechain line, and a file or line that does not
    read, is skipped."""
    usages: dict[object, dict] = {}
    for path in paths:
        try:
            with open(path, encoding="utf-8", errors="replace") as source:
                lines = source.readlines()
        except OSError:
            continue
        for number, text in enumerate(lines):
            try:
                entry = json.loads(text)
            except ValueError:
                continue
            assistant = isinstance(entry, dict) and entry.get("type") == "assistant" and not entry.get("isSidechain")
            message = entry.get("message") if assistant else None
            usage = message.get("usage") if isinstance(message, dict) else None
            if isinstance(usage, dict):
                key = message.get("id")
                usages[key if isinstance(key, str) and key else (str(path), number)] = usage
    totals = []
    for _, key in _USAGE_KEYS:
        values = [usage[key] for usage in usages.values()
                  if isinstance(usage.get(key), int) and not isinstance(usage.get(key), bool)]
        totals.append(sum(values) if values else None)
    return Usage(*totals, len(usages) or None)


def locate(projects_root: Path, uuid: str) -> tuple[Path | None, tuple[Path, ...]]:
    """The main transcript of session ``uuid`` in any project directory, and its subagent transcripts."""
    root, name = glob.escape(str(projects_root)), glob.escape(uuid)
    main = sorted(glob.glob(os.path.join(root, "*", f"{name}.jsonl")))
    subagents = glob.glob(os.path.join(root, "*", name, "subagents", "*.jsonl"))
    return (Path(main[0]) if main else None), tuple(Path(path) for path in sorted(subagents))


def est_lines(handoff_text: str) -> int | None:
    """The N of the Settled ``Estimate: ~N changed lines`` line, or ``None`` without one."""
    heading = _SETTLED_HEADING.search(handoff_text)
    if heading is None:
        return None
    following = _NEXT_HEADING.search(handoff_text, heading.end())
    match = _ESTIMATE_LINE.search(handoff_text, heading.end(), following.start() if following else len(handoff_text))
    return int(match.group(1)) if match else None


def job_record(*, job_id: str, date: str, repo: str, slug: str, tier: str | None, outcome: str,
               est_lines: int | None, lines: Mapping[str, int | None] | None, orchestrator: Usage,
               subagents: Usage) -> dict:
    """The orchestrator's tokens and the subagents' tokens stay separate fields; ``turns`` is the orchestrator's."""
    return {"job": job_id, "date": date, "repo": repo, "slug": slug, "tier": tier, "outcome": outcome,
            "est_lines": est_lines, "lines": dict(lines) if lines is not None else None,
            "turns": orchestrator.turns, "orchestrator_tokens": _tokens(orchestrator),
            "subagent_tokens": _tokens(subagents)}


def append(path: Path, record: Mapping) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as sink:
        sink.write(json.dumps(record, separators=(",", ":")) + "\n")


def _tokens(usage: Usage) -> dict[str, int | None]:
    return {field: getattr(usage, field) for field, _ in _USAGE_KEYS}

