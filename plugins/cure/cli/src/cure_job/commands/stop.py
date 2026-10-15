"""``cure-job stop`` — stop the live session of a job's latest run."""
from __future__ import annotations

import argparse

from ..providers.jobs import JobsProvider
from .base import Command, job_id_arg


class StopCommand(Command):
    name = "stop"
    usage = "cure-job stop ID"
    help = "stop the live session of a job"
    description = "Stop the live session of a job's latest run and print the session name"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("id", metavar="ID", type=job_id_arg, help="job id")

    def run(self, args: argparse.Namespace, jobs: JobsProvider) -> int:
        self.cli.out(jobs.stop(args.id))
        return 0
