"""``cure-job launch`` — start the next run of a job in a background session."""
from __future__ import annotations

import argparse

from ..providers.jobs import JobsProvider
from .base import Command, job_id_arg

_SEPARATOR = "--"


class LaunchCommand(Command):
    name = "launch"
    usage = "cure-job launch ID [-- CLAUDE_ARG ...]"
    help = "start the next run of a job"
    description = "Start the next run of a job in a background session and print the session name"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("id", metavar="ID", type=job_id_arg, help="job id")
        parser.add_argument("claude_args", metavar="CLAUDE_ARG", nargs=argparse.REMAINDER,
                            help="arguments after -- are passed to claude before the prompt")

    def run(self, args: argparse.Namespace, jobs: JobsProvider) -> int:
        claude_args = list(args.claude_args)
        # argparse keeps the separator in a REMAINDER value.
        if claude_args[:1] == [_SEPARATOR]:
            del claude_args[0]
        self.cli.out(jobs.launch(args.id, claude_args))
        return 0
