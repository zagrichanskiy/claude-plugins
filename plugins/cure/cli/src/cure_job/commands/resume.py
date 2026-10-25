"""``cure-job resume`` — continue the session of a needs-input job as its next run."""
from __future__ import annotations

import argparse

from ..providers.jobs import JobsProvider
from .launch import LaunchCommand, claude_args


class ResumeCommand(LaunchCommand):
    name = "resume"
    usage = "cure-job resume ID [-- --permission-mode MODE]"
    help = "continue the session of a needs-input job"
    description = ("Stop the session of a needs-input job's latest run, resume it in the background with the "
                   "goal file as its next run, and print the session name. A session that no longer exists "
                   "exits 1 and starts nothing; use cure-job launch then")

    def run(self, args: argparse.Namespace, jobs: JobsProvider) -> int:
        self.cli.out(jobs.resume(args.id, claude_args(args)))
        return 0
