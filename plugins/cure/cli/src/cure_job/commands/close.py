"""``cure-job close`` — abandon a job."""
from __future__ import annotations

import argparse

from ..providers.jobs import JobsProvider
from .base import Command, job_id_arg


class CloseCommand(Command):
    name = "close"
    usage = "cure-job close ID [--reason TEXT]"
    help = "abandon a job"
    description = "Abandon a job that has no live session. It does not stop a session; use cure-job stop first"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("id", metavar="ID", type=job_id_arg, help="job id")
        parser.add_argument("--reason", metavar="TEXT", default="",
                            help="why the job is abandoned")

    def run(self, args: argparse.Namespace, jobs: JobsProvider) -> int:
        jobs.close(args.id, args.reason)
        return 0
