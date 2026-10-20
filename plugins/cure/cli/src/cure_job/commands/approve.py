"""``cure-job approve`` — record the approval of a job's goal file."""
from __future__ import annotations

import argparse

from ..events import APPROVERS
from ..providers.jobs import JobsProvider
from .base import Command, job_id_arg


class ApproveCommand(Command):
    name = "approve"
    usage = "cure-job approve ID [--by user|auto]"
    help = "approve the goal of a job before its first launch"
    description = ("Approve the current goal.md of a job that has no launched run and no result. "
                   "An edit of goal.md revokes the approval. A second call for the same goal does nothing")

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("id", metavar="ID", type=job_id_arg, help="job id")
        parser.add_argument("--by", choices=APPROVERS, default=APPROVERS[0],
                            help="user: the user approved; auto: the auto-approve rule applied (default: user)")

    def run(self, args: argparse.Namespace, jobs: JobsProvider) -> int:
        jobs.approve(args.id, args.by)
        return 0
