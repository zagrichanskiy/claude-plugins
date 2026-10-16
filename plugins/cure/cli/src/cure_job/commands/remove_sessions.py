"""``cure-job remove-sessions`` — delete the session of every run of a finished job."""
from __future__ import annotations

import argparse

from ..providers.jobs import JobsProvider
from .base import Command, job_id_arg


class RemoveSessionsCommand(Command):
    name = "remove-sessions"
    usage = "cure-job remove-sessions ID"
    help = "delete the sessions of every run of a done or abandoned job"
    description = ("Stop and delete the session of every run of a done or abandoned job with claude rm, "
                   "print each deleted session name and record sessions-removed when none is left listed. "
                   "A failed or open job keeps its sessions")

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("id", metavar="ID", type=job_id_arg, help="job id")

    def run(self, args: argparse.Namespace, jobs: JobsProvider) -> int:
        for name in jobs.remove_sessions(args.id):
            self.cli.out(name)
        return 0
