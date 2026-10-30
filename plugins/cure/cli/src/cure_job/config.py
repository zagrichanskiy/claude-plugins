"""``config.json``: the key table, the built-in defaults and the validation.

The file is a JSON object of groups, each an object of keys:
``{"handoff": {"delivery": "pr"}}``. Internally every key goes by its dotted
name in :data:`DEFAULTS` (``handoff.delivery``); a key without a dot sits at the
top level. A missing file means every default. A key in error takes its default and is
reported as a :class:`Problem`; any problem puts the CLI in safe mode, in which
``prune`` removes no job and ``approve --by auto`` is refused.

``skills/dispatch/config.example.json`` is the output of :func:`example`;
regenerate it with ``PYTHONPATH=src python3 -m cure_job.config > ../skills/dispatch/config.example.json``.
"""
from __future__ import annotations

import json
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .errors import CureJobError

FILE = "config.json"
OLD_FILE = "defaults.md"

TIERS = ("Solo", "Light", "Full")

DEFAULTS: dict[str, object] = {
    "handoff.delivery": "commit",
    "handoff.branch": "new",
    "handoff.resource-risk": [],
    "dispatcher.auto-approve-tiers": ["Solo", "Light"],
    "dispatcher.stalled-confirm-seconds": 60,
    "reviews.Solo": 0,
    "reviews.Light": 2,
    "reviews.Full": 3,
    "split.limit": 1200,
    "split.factor": 1.5,
    "split.tracker": "github",
    "split.jira-command": "",
    "short-hold.wait-seconds": 540,
    "short-hold.wait-total-minutes": 120,
    "prune.failed-days": 30,
    "band.jira-url": "https://ienso-team.atlassian.net",
    "launch-grace-seconds": 60,
}


GROUPS = tuple(dict.fromkeys(key.split(".")[0] for key in DEFAULTS if "." in key))

#: Removed keys by (group, name), and why.
REMOVED = {
    ("handoff", "base"): "a job's base is the base stated in the handoff, else the repository's default branch",
    ("prune", "done-days"): "a done job is pruned once its finish is reported and its sessions are removed",
    ("prune", "abandoned-days"): "an abandoned job is pruned once its sessions are removed",
}


class ConfigError(CureJobError):
    """``config init`` cannot write ``config.json``."""


@dataclass(frozen=True)
class Problem:
    #: ``None`` when the whole file is in error.
    key: str | None
    problem: str
    #: ``problem`` is the whole line, without the file name.
    bare: bool = False

    def __str__(self) -> str:
        if self.bare:
            return self.problem
        if self.key:
            return f"{FILE}: {self.key}: {self.problem}"
        return f"{FILE}: {self.problem}"


@dataclass(frozen=True)
class Config:
    values: dict[str, object] = field(default_factory=lambda: dict(DEFAULTS))
    problems: tuple[Problem, ...] = ()

    def __getitem__(self, key: str) -> object:
        return self.values[key]


def fallback(problem: Problem) -> str:
    """The line a command that goes on with the defaults prints for ``problem``."""
    if problem.key is None:
        return f"{problem}; using every default"
    if problem.key not in DEFAULTS:
        return f"{problem}; ignored"
    return f"{problem}; using default {json.dumps(DEFAULTS[problem.key])}"


def plugin_version(plugin_root: Path) -> str | None:
    """The ``version`` in the plugin's ``plugin.json``, or ``None`` when it cannot be read."""
    try:
        version = json.loads((plugin_root / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
    except (OSError, UnicodeDecodeError, ValueError, KeyError, TypeError):
        return None
    return version if isinstance(version, str) else None


def load(path: Path, root: Path, version: str | None) -> Config:
    """Load ``path``; a ``config.json`` left in the state ``root`` while ``path`` is missing is an error."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        if (root / FILE).exists():
            return Config(problems=(Problem(None, f"{FILE} found at the old location {root / FILE}; "
                                                  "run cure-job config init", bare=True),))
        return Config()
    except (OSError, UnicodeDecodeError) as e:
        return Config(problems=(Problem(None, f"cannot read {path}: {e}"),))
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return Config(problems=(Problem(None, f"invalid JSON: {e}"),))
    if not isinstance(data, dict):
        return Config(problems=(Problem(None, "not a JSON object"),))
    return validate(data, version)


def validate(data: dict, version: str | None) -> Config:
    """Validate the nested form of ``config.json``."""
    values = dict(DEFAULTS)
    problems: list[Problem] = []
    for key, value in data.items():
        if key in GROUPS:
            if isinstance(value, dict):
                for name, item in value.items():
                    _check(f"{key}.{name}", item, values, problems, version)
            else:
                problems.append(Problem(key, f"group is not a JSON object, got {json.dumps(value)}"))
        elif "." in key and key in DEFAULTS:
            group, name = key.split(".", 1)
            problems.append(Problem(key, f'flat key; write it as {{"{group}": {{"{name}": ...}}}}'))
        else:
            _check(key, value, values, problems, version)
    return Config(values, tuple(problems))


def nest(values: dict[str, object]) -> dict[str, object]:
    """Return the dotted ``values`` in the nested form of ``config.json``."""
    nested: dict[str, object] = {}
    for key, value in values.items():
        if "." in key:
            group, name = key.split(".", 1)
            nested.setdefault(group, {})[name] = value
        else:
            nested[key] = value
    return nested


def example() -> str:
    """The text of ``config.example.json``: every key with its default."""
    return json.dumps(nest(DEFAULTS), indent=2) + "\n"


def _check(key: str, value: object, values: dict[str, object], problems: list[Problem],
           version: str | None) -> None:
    if problem := removed(key):
        if problem not in problems:
            problems.append(problem)
    elif key not in DEFAULTS:
        cure = f"cure {version}" if version else "this cure"
        problems.append(Problem(key, f"unknown to {cure}; restart the dispatcher after an update"))
    elif problem := _CHECKS[key](value):
        problems.append(Problem(key, problem))
    else:
        values[key] = value


def removed(key: str) -> Problem | None:
    """The problem for a removed dotted ``key``, reported under its group; ``None`` when ``key`` is not removed."""
    group, _, name = key.partition(".")
    reason = REMOVED.get((group, name))
    return Problem(group, f'"{name}" is removed; {reason}') if reason else None


def _int_range(low: int, high: int) -> Callable[[object], str | None]:
    def check(value: object) -> str | None:
        if type(value) is not int:
            return f"expected an integer, got {json.dumps(value)}"
        if not low <= value <= high:
            return f"{value} is outside {low}..{high}"
        return None
    return check


def _int_at_least(low: int) -> Callable[[object], str | None]:
    def check(value: object) -> str | None:
        if type(value) is not int:
            return f"expected an integer, got {json.dumps(value)}"
        if value < low:
            return f"{value} is below {low}"
        return None
    return check


def _number_range(low: float, high: float) -> Callable[[object], str | None]:
    def check(value: object) -> str | None:
        if type(value) not in (int, float):
            return f"expected a number, got {json.dumps(value)}"
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


def _tracker(value: object) -> str | None:
    return None if value in ("github", "jira") else f"expected \"github\" or \"jira\", got {json.dumps(value)}"


def _text(value: object) -> str | None:
    return None if isinstance(value, str) else f"expected a string, got {json.dumps(value)}"


def _https_url(value: object) -> str | None:
    if not isinstance(value, str) or not re.fullmatch(r"https://[^\s/]+(/\S*)?", value):
        return f"expected an https URL, got {json.dumps(value)}"
    return None


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
    "handoff.branch": _branch,
    "handoff.resource-risk": _risks,
    "dispatcher.auto-approve-tiers": _tiers,
    "dispatcher.stalled-confirm-seconds": _int_range(10, 600),
    "reviews.Solo": _int_range(0, 0),
    "reviews.Light": _int_at_least(1),
    "reviews.Full": _int_at_least(2),
    "split.limit": _int_range(100, 5000),
    "split.factor": _number_range(1.0, 1.9),
    "split.tracker": _tracker,
    "split.jira-command": _text,
    "short-hold.wait-seconds": _int_range(10, 540),
    "short-hold.wait-total-minutes": _int_range(10, 1440),
    "prune.failed-days": _int_range(1, 365),
    "band.jira-url": _https_url,
    "launch-grace-seconds": _int_range(10, 600),
}

#: The ``defaults.md`` keys whose rows hold one scalar, and their ``config.json`` keys.
_OLD_SCALARS = {"delivery": "handoff.delivery", "branch": "handoff.branch"}


def init(path: Path, root: Path, version: str | None, notice: Callable[[str], None]) -> Path:
    """Create ``path``: move ``config.json`` from the state ``root``, else write it from the defaults
    and ``defaults.md`` and rename ``defaults.md``.

    ``notice`` receives one line for each ``defaults.md`` row that is dropped.
    """
    old = root / OLD_FILE
    if path.exists():
        raise ConfigError(f"{path} exists")
    if (root / FILE).exists():
        try:
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            (root / FILE).chmod(0o600)
            shutil.move(root / FILE, path)
        except OSError as e:
            raise ConfigError(f"cannot move {root / FILE} to {path}: {e}") from e
        return path
    data: dict[str, object] = dict(DEFAULTS)
    if old.exists():
        data.update(_from_defaults_md(old, notice))
    data = nest(data)
    problems = validate(data, version).problems
    if problems:
        raise ConfigError(f"{old}: " + "; ".join(f"{p.key}: {p.problem}" for p in problems))
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w", encoding="utf-8") as f:
            f.write(json.dumps(data, indent=2) + "\n")
        if old.exists():
            old.rename(old.with_name(OLD_FILE + ".bak"))
    except OSError as e:
        raise ConfigError(f"cannot write {path}: {e}") from e
    return path


def _from_defaults_md(path: Path, notice: Callable[[str], None]) -> dict[str, object]:
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
        elif reason := REMOVED.get(("handoff", key)):
            notice(f'{OLD_FILE}: handoff: "{key}" is removed; row dropped; {reason}')
        elif key in _OLD_SCALARS and scope == "all":
            found[_OLD_SCALARS[key]] = value
        else:
            raise ConfigError(f"{path}:{number}: row {key!r} with scope {scope!r} has no config.json key")
    if risks:
        found["handoff.resource-risk"] = risks
    return found


if __name__ == "__main__":
    print(example(), end="")
