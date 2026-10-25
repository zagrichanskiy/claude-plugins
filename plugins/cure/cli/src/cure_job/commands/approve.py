"""``cure-job approve`` — record the approval of a job's goal file."""
from __future__ import annotations

import argparse
import sys

from .. import config
from ..events import APPROVERS
from ..providers.jobs import JobsProvider
from .base import Command, job_id_arg


class ApproveCommand(Command):
    name = "approve"
    usage = "cure-job approve ID --by user|auto"
    help = "approve the goal of a job before its first launch"
    description = ("Approve the current goal.md of a job that has no launched run and no result. A goal.md "
                   "with items under ## Open is refused. An edit of goal.md revokes the approval. A second call "
                   "for the same goal does nothing. --by auto exits 1 while config.json has an error")

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("id", metavar="ID", type=job_id_arg, help="job id")
        parser.add_argument("--by", choices=APPROVERS, required=True,
                            help="user: the user approved; auto: the auto-approve rule applied")
        parser.set_defaults(config_mode="none")

    def run(self, args: argparse.Namespace, jobs: JobsProvider) -> int:
        auto = args.by == "auto"
        for problem in self.cli.config.problems:
            print(problem if auto else config.fallback(problem), file=sys.stderr)
        if auto and self.cli.config.problems:
            return 1
        jobs.approve(args.id, args.by)
        return 0
