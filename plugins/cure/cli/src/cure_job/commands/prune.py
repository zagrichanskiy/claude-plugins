"""``cure-job prune`` — remove the jobs past their retention period, and half-created job directories."""
from __future__ import annotations

import argparse

from ..providers.jobs import JobsProvider
from .base import Command


class PruneCommand(Command):
    name = "prune"
    usage = "cure-job prune"
    help = "remove finished jobs past their retention period and half-created job directories"
    description = ("Remove done, failed and abandoned jobs after prune.done-days, prune.failed-days and "
                   "prune.abandoned-days of config.json, and half-created job directories after one day. "
                   "Print each removed directory path, then each removed id")

    def run(self, args: argparse.Namespace, jobs: JobsProvider) -> int:
        # First: they need no job file to parse, so an invalid one cannot block them.
        for path in jobs.prune_half_created():
            self.cli.out(str(path))
        for job_id in jobs.prune():
            self.cli.out(job_id)
        return 0
