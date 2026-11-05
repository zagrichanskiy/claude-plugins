"""``cure-job end`` — record the end of a session of a kind other than work."""
from __future__ import annotations

import argparse

from ..kinds import event_kinds
from ..providers.jobs import JobsProvider
from .base import Command, job_id_arg, kind_arg, notify_line


class EndCommand(Command):
    name = "end"
    usage = "cure-job end ID KIND [--summary LINE ...]"
    help = "record the end of a session of a kind other than work"
    description = ("Record the end of a job's open KIND session and print the message to send. "
                   "A work session ends with cure-job finish")

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        kinds = event_kinds(self.cli.jobs.kinds)
        parser.add_argument("id", metavar="ID", type=job_id_arg, help="job id")
        parser.add_argument("kind", metavar="KIND", type=kind_arg(kinds, "work ends with cure-job finish"),
                            help="the session kind: " + (", ".join(kinds) or "none in this version"))
        parser.add_argument("--summary", metavar="LINE", action="append", type=_line, default=[],
                            help="one summary line; repeatable; the kind sets how many")

    def run(self, args: argparse.Namespace, jobs: JobsProvider) -> int:
        jobs.end(args.id, args.kind, args.summary)
        self.cli.out(notify_line(args.id))
        return 0


def _line(text: str) -> str:
    text = text.strip()
    if "\n" in text:
        raise argparse.ArgumentTypeError("a summary line holds no line break")
    return text
