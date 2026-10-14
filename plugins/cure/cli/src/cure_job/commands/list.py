"""``cure-job list`` — every job with its derived state."""
from __future__ import annotations

import argparse
import json

from ..providers.jobs import JobsProvider
from ..state import JobView
from .base import Command


class ListCommand(Command):
    name = "list"
    usage = "cure-job list [--json]"
    help = "list every job with its state"
    description = "List every job with its derived state, in ascending id order"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--json", action="store_true",
                            help="print one compact JSON array instead of text")

    def run(self, args: argparse.Namespace, jobs: JobsProvider) -> int:
        views = jobs.views()
        if args.json:
            self.cli.out(json.dumps([_as_json(view) for view in views], separators=(",", ":")))
            return 0
        width = max((len(view.record.id) for view in views), default=0)
        for view in views:
            line = f"{view.record.id:<{width}}  {view.state.value}"
            if view.blocked_by:
                line += "  blocked-by=" + ",".join(view.blocked_by)
            self.cli.out(line)
        return 0


def _as_json(view: JobView) -> dict:
    record = view.record
    return {
        "id": record.id,
        "state": view.state.value,
        "dir": str(record.dir),
        "run": record.run,
        "session": record.session,
        "resources": sorted(record.resources),
        "blocked-by": list(view.blocked_by),
        "problem": record.result.problem if record.result else None,
    }
