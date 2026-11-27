"""``cure-job stats`` — per repository and tier, the job count and the medians of the job ledgers."""
from __future__ import annotations

import argparse
import statistics

from ..ledger import TOKEN_TYPES
from ..providers.jobs import JobsProvider
from .base import Command

#: What a column prints for a missing tier and for a median over no value.
NONE = "-"


class StatsCommand(Command):
    name = "stats"
    usage = "cure-job stats [--repo REPO]"
    help = "print the job count and median tokens, turns and changed lines per repository and tier"
    description = ("Print one line per repository and tier with the job count and the median of each token type, "
                   "of turns and of changed lines, over the last ledger record of every current and removed job. "
                   "A token value adds the orchestrator's and the subagents' tokens. A null value is left out of a "
                   "median; a median over no value prints -")

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--repo", help="print only the jobs of this repository")

    def run(self, args: argparse.Namespace, jobs: JobsProvider) -> int:
        groups: dict[tuple[str, str], list[dict]] = {}
        for row in jobs.job_records():
            repo = str(row.get("repo") or NONE)
            if args.repo is None or repo == args.repo:
                groups.setdefault((repo, str(row.get("tier") or NONE)), []).append(row)
        table = [["repo", "tier", "jobs", *TOKEN_TYPES, "turns", "lines"]]
        for (repo, tier), rows in sorted(groups.items()):
            values = [[_tokens(row, kind) for row in rows] for kind in TOKEN_TYPES]
            values += [[_number(row.get("turns")) for row in rows], [_lines(row) for row in rows]]
            table.append([repo, tier, str(len(rows)), *map(_median, values)])
        widths = [max(len(line[column]) for line in table) for column in range(len(table[0]))]
        for line in table:
            self.cli.out("  ".join(cell.ljust(width) for cell, width in zip(line, widths)).rstrip())
        return 0


def _number(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _sum(values: list[int | None]) -> int | None:
    present = [value for value in values if value is not None]
    return sum(present) if present else None


def _field(row: dict, key: str) -> dict:
    value = row.get(key)
    return value if isinstance(value, dict) else {}


def _tokens(row: dict, kind: str) -> int | None:
    return _sum([_number(_field(row, key).get(kind)) for key in ("orchestrator_tokens", "subagent_tokens")])


def _lines(row: dict) -> int | None:
    return _sum([_number(value) for value in _field(row, "lines").values()])


def _median(values: list[int | None]) -> str:
    present = [value for value in values if value is not None]
    if not present:
        return NONE
    median = statistics.median(present)
    return str(int(median)) if median == int(median) else str(median)
