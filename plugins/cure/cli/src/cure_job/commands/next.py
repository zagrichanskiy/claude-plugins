"""``cure-job next`` — the actions the dispatcher takes, per job."""
from __future__ import annotations

import argparse
import json

from ..actions import actions
from ..providers.jobs import JobsProvider
from ..state import lock_rank
from .base import Command
from .list import invalid_row, job_row


class NextCommand(Command):
    name = "next"
    usage = "cure-job next --json"
    help = "list the actions the dispatcher takes for each job"
    description = ("Print one compact JSON array: the list --json row of each job that has an action, "
                   "with its ordered actions and their args, in lock order")

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--json", action="store_true", required=True, help="print JSON; the only format")
        parser.set_defaults(config_mode="strict")

    def run(self, args: argparse.Namespace, jobs: JobsProvider) -> int:
        listing = jobs.listing()
        # An invalid job's launches are unknown, so it ranks as launched: it may hold any resource.
        ranked = sorted([(lock_rank(view.record), view, job_row(view, listing.sessions)) for view in listing.views]
                        + [((False, job.id), None, invalid_row(job)) for job in listing.invalid],
                        key=lambda entry: entry[0])
        elements = []
        for _, view, row in ranked:
            found = actions(view, row, jobs.config)
            if found:
                elements.append({**row, "actions": [action.name for action in found],
                                 "args": {action.name: dict(action.args) for action in found if action.args}})
        self.cli.out(json.dumps(elements, separators=(",", ":")))
        return 0
