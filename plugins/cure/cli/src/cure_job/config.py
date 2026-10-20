"""``config.json``: the key table, the built-in defaults and the validation.

The file is one flat JSON object keyed by the dotted names of :data:`DEFAULTS`.
A missing file means every default. A key in error takes its default and is
reported as a :class:`Problem`; :class:`~cure_job.cli.Cli` decides whether a
problem stops the command.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .errors import CureJobError

FILE = "config.json"
OLD_FILE = "defaults.md"

TIERS = ("Solo", "Light", "Full")

DEFAULTS: dict[str, object] = {
    "handoff.delivery": "commit",
    "handoff.base": "main",
    "handoff.branch": "new",
    "handoff.resource-risk": [],
    "dispatcher.auto-approve-tiers": ["Solo", "Light"],
    "dispatcher.stalled-confirm-seconds": 60,
    "split.limit": 800,
    "short-hold.wait-seconds": 540,
    "short-hold.wait-total-minutes": 120,
    "prune.done-days": 14,
    "prune.failed-days": 30,
    "prune.abandoned-days": 30,
    "launch-grace-seconds": 60,
}


class ConfigError(CureJobError):
    """``config init`` cannot write ``config.json``."""


@dataclass(frozen=True)
class Problem:
    #: ``None`` when the whole file is in error.
    key: str | None
    problem: str

    def __str__(self) -> str:
        return f"{FILE}: {self.key}: {self.problem}" if self.key else f"{FILE}: {self.problem}"


@dataclass(frozen=True)
class Config:
    values: dict[str, object] = field(default_factory=lambda: dict(DEFAULTS))
    problems: tuple[Problem, ...] = ()

    def __getitem__(self, key: str) -> object:
        return self.values[key]


def load(root: Path) -> Config:
    path = root / FILE
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return Config()
    except (OSError, UnicodeDecodeError) as e:
        return Config(problems=(Problem(None, f"cannot read {path}: {e}"),))
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return Config(problems=(Problem(None, f"invalid JSON: {e}"),))
    if not isinstance(data, dict):
        return Config(problems=(Problem(None, "not a JSON object"),))
    return validate(data)


def validate(data: dict) -> Config:
    values = dict(DEFAULTS)
    problems = []
    for key, value in data.items():
        if key not in DEFAULTS:
            problems.append(Problem(key, "unknown key"))
            continue
        problem = _CHECKS[key](value)
        if problem:
            problems.append(Problem(key, problem))
        else:
            values[key] = value
    return Config(values, tuple(problems))


def _int_range(low: int, high: int) -> Callable[[object], str | None]:
    def check(value: object) -> str | None:
        if type(value) is not int:
            return f"expected an integer, got {json.dumps(value)}"
        if not low <= value <= high:
            return f"{value} is outside {low}..{high}"
        return None
    return check


def _branch(value: object) -> str | None:
    if not isinstance(value, str) or not value or re.search(r"\s", value):
        return f"expected a branch name, got {json.dumps(value)}"
    return None


def _delivery(value: object) -> str | None:
    return None if value in ("commit", "pr") else f"expected \"commit\" or \"pr\", got {json.dumps(value)}"


def _tiers(value: object) -> str | None:
    if (not isinstance(value, list) or any(tier not in TIERS for tier in value)
            or len(set(value)) != len(value)):
        return f"expected a list of distinct tiers from {', '.join(TIERS)}, got {json.dumps(value)}"
    return None


_SCOPE = re.compile(r"all|(device|repo): \S.*")


def _risks(value: object) -> str | None:
    if not isinstance(value, list):
        return f"expected a list, got {json.dumps(value)}"
    for index, item in enumerate(value, 1):
        if (not isinstance(item, dict) or set(item) != {"scope", "text"}
                or not isinstance(item["scope"], str) or not _SCOPE.fullmatch(item["scope"])
                or not isinstance(item["text"], str) or not item["text"].strip()):
            return (f"item {index}: expected {{\"scope\": \"all\" | \"device: <name>\" | \"repo: <path>\", "
                    f"\"text\": \"<risk>\"}}, got {json.dumps(item)}")
    return None


_CHECKS: dict[str, Callable[[object], str | None]] = {
    "handoff.delivery": _delivery,
    "handoff.base": _branch,
    "handoff.branch": _branch,
    "handoff.resource-risk": _risks,
    "dispatcher.auto-approve-tiers": _tiers,
    "dispatcher.stalled-confirm-seconds": _int_range(10, 600),
    "split.limit": _int_range(100, 5000),
    "short-hold.wait-seconds": _int_range(10, 540),
    "short-hold.wait-total-minutes": _int_range(10, 1440),
    "prune.done-days": _int_range(1, 365),
    "prune.failed-days": _int_range(1, 365),
    "prune.abandoned-days": _int_range(1, 365),
    "launch-grace-seconds": _int_range(10, 600),
}

#: The ``defaults.md`` keys whose rows hold one scalar, and their ``config.json`` keys.
_OLD_SCALARS = {"delivery": "handoff.delivery", "base": "handoff.base", "branch": "handoff.branch"}


def init(root: Path) -> Path:
    """Write ``config.json`` from the defaults and ``defaults.md``, then rename ``defaults.md``."""
    path, old = root / FILE, root / OLD_FILE
    if path.exists():
        raise ConfigError(f"{path} exists")
    data: dict[str, object] = dict(DEFAULTS)
    if old.exists():
        data.update(_from_defaults_md(old))
    problems = validate(data).problems
    if problems:
        raise ConfigError(f"{old}: " + "; ".join(f"{p.key}: {p.problem}" for p in problems))
    try:
        root.mkdir(parents=True, exist_ok=True)
        with open(path, "x", encoding="utf-8") as f:
            f.write(json.dumps(data, indent=2) + "\n")
        if old.exists():
            old.rename(old.with_name(OLD_FILE + ".bak"))
    except OSError as e:
        raise ConfigError(f"cannot write {path}: {e}") from e
    return path


def _from_defaults_md(path: Path) -> dict[str, object]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError) as e:
        raise ConfigError(f"cannot read {path}: {e}") from e
    found: dict[str, object] = {}
    risks: list[dict[str, str]] = []
    in_table = False
    for number, line in enumerate(lines, 1):
        text = line.strip()
        cells = [cell.strip() for cell in text.strip("|").split("|")]
        if not text:
            in_table = False
            continue
        if text.startswith("|") and cells[0] == "key":
            in_table = True
            continue
        if not in_table or ("-" in text and set(text) <= set("|-: ")):
            continue
        if "\\|" in text:
            problem = "escaped '|' is not supported"
        elif not text.startswith("|"):
            problem = "row does not start with '|'"
        elif len(cells) != 3:
            problem = f"row has {len(cells)} cells, expected 3"
        elif not cells[0]:
            problem = "row has an empty key"
        else:
            problem = ""
        if problem:
            raise ConfigError(f"{path}:{number}: {problem}")
        key, value, scope = cells
        if key == "resource risk":
            risks.append({"scope": scope, "text": value})
        elif key in _OLD_SCALARS and scope == "all":
            found[_OLD_SCALARS[key]] = value
        else:
            raise ConfigError(f"{path}:{number}: row {key!r} with scope {scope!r} has no config.json key")
    if risks:
        found["handoff.resource-risk"] = risks
    return found
