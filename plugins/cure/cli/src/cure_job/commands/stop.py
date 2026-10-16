"""``cure-job stop`` — stop the live session of a job's latest run."""
from __future__ import annotations

import argparse

from ..providers.jobs import JobsProvider
from .base import Command, job_id_arg


class StopCommand(Command):
    name = "stop"
    usage = "cure-job stop ID"
    help = "stop the live session of a job"
    description = ("Stop the live session of a job's latest run, wait until it is down and print the session "
                   "name. A session that is already down prints \"<session> not live\" and also exits 0")

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("id", metavar="ID", type=job_id_arg, help="job id")

    def run(self, args: argparse.Namespace, jobs: JobsProvider) -> int:
        stopped = jobs.stop(args.id)
        self.cli.out(stopped.session if stopped.was_live else f"{stopped.session} not live")
        return 0
