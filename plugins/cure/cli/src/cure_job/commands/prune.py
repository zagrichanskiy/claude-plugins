"""``cure-job prune`` — remove the finished jobs that are due, and half-created job directories."""
from __future__ import annotations

import argparse
import sys

from ..providers.jobs import JobsProvider
from .base import Command


class PruneCommand(Command):
    name = "prune"
    usage = "cure-job prune"
    help = "remove finished jobs that are due and half-created job directories"
    description = ("Remove a done job once it is reported and its sessions are removed, an abandoned job once "
                   "its sessions are removed, and a failed job after prune.failed-days of config.json. "
                   "Keep a job that an open job names as after. Remove half-created job directories "
                   "after one day. Print each removed directory path, then each removed id. While config.json "
                   "has an error, remove half-created directories only and exit 1")

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.set_defaults(config_mode="none")

    def run(self, args: argparse.Namespace, jobs: JobsProvider) -> int:
        # First: they need no job file to parse, so an invalid one cannot block them.
        for path in jobs.prune_half_created():
            self.cli.out(str(path))
        if self.cli.config.problems:
            for problem in self.cli.config.problems:
                print(f"{problem}; no job removed", file=sys.stderr)
            return 1
        for job_id in jobs.prune():
            self.cli.out(job_id)
        return 0
