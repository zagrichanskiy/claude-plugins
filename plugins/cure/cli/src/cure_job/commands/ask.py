"""``cure-job ask`` — record that a job's run session asks its origin a question."""
from __future__ import annotations

import argparse

from ..providers.jobs import JobsProvider
from .base import Command, job_id_arg, line_arg, notify_line


class AskCommand(Command):
    name = "ask"
    usage = "cure-job ask ID --question TEXT [--question TEXT ...]"
    help = "record a question of a job's run session to its origin"
    description = ("Record that the run session of a job asks its origin session a question, and print the message "
                   "to send to the origin. The job waits for the answer as awaiting-answer. Runs only in the job's "
                   "own session, during a run without a result, and needs an origin that is a live session")

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("id", metavar="ID", type=job_id_arg, help="job id")
        parser.add_argument("--question", metavar="TEXT", action="append", type=line_arg, required=True,
                            help="one line of the question; repeatable")

    def run(self, args: argparse.Namespace, jobs: JobsProvider) -> int:
        origin = jobs.ask(args.id, args.question, self.cli.caller_job())
        self.cli.out(notify_line(args.id, origin))
        return 0
