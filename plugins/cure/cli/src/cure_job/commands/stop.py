"""``cure-job stop`` — stop the latest session of a job, of one kind or of every kind."""
from __future__ import annotations

import argparse

from ..providers.jobs import JobsProvider
from .base import Command, job_id_arg, kind_arg


class StopCommand(Command):
    name = "stop"
    usage = "cure-job stop ID [KIND]"
    help = "stop the live session of a job"
    description = ("Stop the latest session of a job's KIND, or without KIND of every kind the job has, work first. "
                   "Wait until each is down and print its name, one line each. A session that is already down "
                   "prints \"<session> not live\" and also exits 0")

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("id", metavar="ID", type=job_id_arg, help="job id")
        kinds = self.cli.jobs.kinds
        parser.add_argument("kind", metavar="KIND", nargs="?", type=kind_arg(kinds),
                            help="the session kind: " + ", ".join(kinds))

    def run(self, args: argparse.Namespace, jobs: JobsProvider) -> int:
        for stopped in jobs.stop(args.id, args.kind):
            self.cli.out(stopped.session if stopped.was_live else f"{stopped.session} not live")
        return 0
