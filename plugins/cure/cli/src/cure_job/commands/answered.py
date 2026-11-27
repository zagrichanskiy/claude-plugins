"""``cure-job answered`` — record the origin's answer to a job's latest question."""
from __future__ import annotations

import argparse

from ..providers.jobs import JobsProvider
from .base import Command, job_id_arg, line_arg


class AnsweredCommand(Command):
    name = "answered"
    usage = "cure-job answered ID --answer TEXT [--answer TEXT ...]"
    help = "record the answer to a job's latest question"
    description = ("Record the answer the run session of a job got to its latest question. Runs only in the job's "
                   "own session, after cure-job ask. A second call for an answered question does nothing")

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("id", metavar="ID", type=job_id_arg, help="job id")
        parser.add_argument("--answer", metavar="TEXT", action="append", type=line_arg, required=True,
                            help="one line of the answer; repeatable")

    def run(self, args: argparse.Namespace, jobs: JobsProvider) -> int:
        jobs.answered(args.id, args.answer, self.cli.caller_job())
        return 0
