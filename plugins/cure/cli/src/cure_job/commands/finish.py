"""``cure-job finish`` — record the result of a job run in ``result.md``."""
from __future__ import annotations

import argparse
import os

from ..providers.jobs import JobsProvider
from ..result import Report, ResultStatus
from .base import Command, job_id_arg


class FinishCommand(Command):
    name = "finish"
    usage = ("cure-job finish ID --status STATUS [--unproven N[,N...]] [--question TEXT ...] "
             "[--retro PATH] [--pr URL] [--kept PATH ...]")
    help = "record the result of a job run"
    description = "Write result.md for a launched job and print its path"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("id", metavar="ID", type=job_id_arg, help="job id")
        parser.add_argument("--status", metavar="STATUS", required=True,
                            choices=[status.value for status in ResultStatus],
                            help=", ".join(status.value for status in ResultStatus))
        parser.add_argument("--unproven", metavar="N[,N...]", type=_numbers, default=(),
                            help="done-when numbers left unproven; needs --status done")
        parser.add_argument("--question", metavar="TEXT", action="append", type=str.strip, default=[],
                            help="a question for the user; repeatable; needed by --status needs-input")
        parser.add_argument("--retro", metavar="PATH", type=_path, help="retrospective file")
        parser.add_argument("--pr", metavar="URL", type=str.strip, help="pull request")
        parser.add_argument("--kept", metavar="PATH", action="append", type=_path, default=[],
                            help="a file kept for the user; repeatable")
        # Kept for run(): a refusal of Report is a usage error.
        self._parser = parser

    def run(self, args: argparse.Namespace, jobs: JobsProvider) -> int:
        try:
            report = Report(status=ResultStatus(args.status), unproven=args.unproven,
                            questions=tuple(args.question), retro=args.retro, pr=args.pr,
                            kept=tuple(args.kept))
        except ValueError as e:
            self._parser.error(str(e))
        self.cli.out(str(jobs.finish(args.id, report)))
        return 0


def _numbers(text: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in text.split(","))


def _path(text: str) -> str:
    # Absolute against the session's cwd: the dispatcher reads it from another.
    text = text.strip()
    if not text:
        raise argparse.ArgumentTypeError("empty path")
    return os.path.abspath(text)
