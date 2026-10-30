"""``cure-job drafted`` — end the open draft of a job: the goal-writer's last call."""
from __future__ import annotations

import argparse

from ..providers.jobs import JobsProvider
from .base import Command, job_id_arg, notify_line

SUMMARY_LINES = 3


class DraftedCommand(Command):
    name = "drafted"
    usage = "cure-job drafted ID --summary LINE --summary LINE --summary LINE"
    help = "end the open draft of a job"
    description = ("Record the end of the open draft of a job, with the ## Open item count of goal.md and the "
                   "summary, and print the goal path, open=<count> and the message to send")
    epilog = """The three --summary lines, in this order:
  1  the outcome
  2  the tier and the repository
  3  the done-when count, the delivery, and each classifier-gated action the goal needs

Each line is one line of text.
Exit 2 means wrong arguments: fix them, do not repeat the same command."""

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("id", metavar="ID", type=job_id_arg, help="job id")
        parser.add_argument("--summary", metavar="LINE", action="append", type=_line, required=True,
                            help=f"one summary line; exactly {SUMMARY_LINES}")
        # Kept for run(): a wrong count of summary lines is a usage error.
        self._parser = parser

    def run(self, args: argparse.Namespace, jobs: JobsProvider) -> int:
        if len(args.summary) != SUMMARY_LINES:
            self._parser.error(f"argument --summary: expected {SUMMARY_LINES} lines, got {len(args.summary)}")
        goal, open_items = jobs.drafted(args.id, args.summary)
        self.cli.out(str(goal))
        self.cli.out(f"open={open_items}")
        self.cli.out(notify_line(args.id))
        return 0


def _line(text: str) -> str:
    text = text.strip()
    if not text or "\n" in text:
        raise argparse.ArgumentTypeError("expected one non-empty line")
    return text
