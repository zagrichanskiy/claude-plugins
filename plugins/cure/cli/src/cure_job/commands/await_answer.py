"""``cure-job await-answer`` — wait until the origin's answer to a job's pending question is recorded."""
from __future__ import annotations

import argparse

from ..providers.jobs import JobsProvider
from .base import Command, job_id_arg


class AwaitAnswerCommand(Command):
    name = "await-answer"
    usage = "cure-job await-answer ID"
    help = "wait until a job's pending question is answered"
    description = ("Wait until cure-job answered records the answer to the pending question of a job's run, then exit "
                   "0. Exit 1 when the run asked nothing, gets a result or the job is abandoned. Runs only in the "
                   "job's own session")

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("id", metavar="ID", type=job_id_arg, help="job id")

    def run(self, args: argparse.Namespace, jobs: JobsProvider) -> int:
        jobs.await_answer(args.id, self.cli.caller_job())
        return 0
