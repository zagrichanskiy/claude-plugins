"""``cure-job requested`` — record that the dispatcher sent an action of a job to its origin."""
from __future__ import annotations

import argparse

from ..events import REQUESTABLE
from ..providers.jobs import JobsProvider
from .base import Command, job_id_arg


class RequestedCommand(Command):
    name = "requested"
    usage = f"cure-job requested ID --action {{{','.join(REQUESTABLE)}}}"
    help = "record that the origin was sent an action of a job"
    description = ("Record that the dispatcher sent a route-origin action of a job's latest run to the origin "
                   "session. cure-job next then omits that action for the run; ask-approval returns when goal.md "
                   "changes")

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("id", metavar="ID", type=job_id_arg, help="job id")
        parser.add_argument("--action", required=True, choices=REQUESTABLE, help="the action sent")

    def run(self, args: argparse.Namespace, jobs: JobsProvider) -> int:
        jobs.requested(args.id, args.action)
        return 0
