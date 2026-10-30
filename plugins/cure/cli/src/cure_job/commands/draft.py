"""``cure-job draft`` — start a goal-writer session that writes a job's goal or applies answers to it."""
from __future__ import annotations

import argparse

from ..providers.jobs import JobsProvider
from ..worker import RunArguments
from .base import Command, job_id_arg, read_input
from .launch import claude_args


class DraftCommand(Command):
    name = "draft"
    usage = "cure-job draft ID [--answers FILE|-] [-- --permission-mode MODE]"
    help = "start a goal-writer session for a job"
    description = ("Start a cure:goal-writer background session and print the session name. Without --answers "
                   "it writes goal.md; with --answers it applies the answers, copied to answers-<n>.md in the job "
                   "directory, to goal.md. It stops the live session of the previous draft first. The session "
                   "ends with cure-job drafted")

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("id", metavar="ID", type=job_id_arg, help="job id")
        parser.add_argument("--answers", metavar="FILE|-",
                            help="the user's answers to apply; - reads stdin; needs goal.md")
        parser.add_argument("claude_args", metavar="CLAUDE_ARG", nargs=argparse.REMAINDER,
                            help="after --, only --permission-mode " + "|".join(RunArguments.MODES)
                                 + "; passed to claude before the prompt")
        # Kept for run(): a remainder that holds --answers is parsed again, and empty answers are a usage error.
        self._parser = parser

    def run(self, args: argparse.Namespace, jobs: JobsProvider) -> int:
        rest = list(args.claude_args)
        cut = rest.index("--") if "--" in rest else len(rest)
        # A REMAINDER after ID takes the options after ID too; put them before ID.
        if cut and rest[0].startswith("--answers"):
            args = self._parser.parse_args([*rest[:cut], args.id, *rest[cut:]])
        arguments = claude_args(args)
        answers = None
        if args.answers is not None:
            answers = read_input(self._parser, "--answers", args.answers)
            if not answers.strip():
                self._parser.error("argument --answers: no answers")
        self.cli.out(jobs.draft(args.id, answers, self.cli.config_path.parent, arguments))
        return 0
