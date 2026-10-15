"""``cure-job reported`` — record that a job's origin was told of its latest result."""
from __future__ import annotations

import argparse

from ..providers.jobs import JobsProvider
from .base import Command, job_id_arg


class ReportedCommand(Command):
    name = "reported"
    usage = "cure-job reported ID"
    help = "record that the origin was told of a job's result"
    description = ("Record that the origin session was told of the result of a job's latest run. "
                   "A second call for the same run does nothing")

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("id", metavar="ID", type=job_id_arg, help="job id")

    def run(self, args: argparse.Namespace, jobs: JobsProvider) -> int:
        jobs.mark_reported(args.id)
        return 0
