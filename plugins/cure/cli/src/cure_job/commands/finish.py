"""``cure-job finish`` — record the result of a job run in ``result.md``."""
from __future__ import annotations

import argparse
import os

from ..providers.jobs import JobsProvider
from ..result import Report, ResultStatus
from .base import Command, job_id_arg, notify_line


class FinishCommand(Command):
    name = "finish"
    usage = ("cure-job finish ID --status STATUS [--unproven N[,N...]] [--question TEXT ...] "
             "[--retro PATH] [--pr URL ...] [--kept PATH ...]")
    help = "record the result of a job run"
    description = "Write result.md for a launched job and print its path and the message to send"
    epilog = """\
What each option records:
  --status done|failed|needs-input  the outcome of the run
  --unproven N[,N...]               with done: each done-when item whose proof is unavailable
  --question TEXT                   with needs-input: one per question; repeatable
  --retro PATH                      the absolute path of the retrospective
  --pr URL                          the full URL https://<host>/<owner>/<repo>/pull/<n>; one per pull request
                                    on the job's branch; repeatable
  --kept PATH                       one per file left in the repository; repeatable

Each text value is one line. Separate the parts of a long question with "; ".
Exit 2 means wrong arguments: fix them, do not repeat the same command.
Exit 1 with an error naming --pr or --retro means the value is refused: fix the value,
then run finish again; do not repeat the same command."""

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("id", metavar="ID", type=job_id_arg, help="job id")
        parser.add_argument("--status", metavar="STATUS", required=True,
                            choices=[status.value for status in ResultStatus],
                            help=", ".join(status.value for status in ResultStatus))
        parser.add_argument("--unproven", metavar="N[,N...]", type=_numbers, default=(),
                            help="done-when numbers left unproven; needs --status done")
        parser.add_argument("--question", metavar="TEXT", action="append", type=str.strip, default=[],
                            help="a question for the user; repeatable; needed by --status needs-input")
        parser.add_argument("--retro", metavar="PATH", type=_text, help="absolute path of the retrospective")
        parser.add_argument("--pr", metavar="URL", action="append", type=str.strip, default=[],
                            help="a pull request on the job's branch, as a full URL; repeatable")
        parser.add_argument("--kept", metavar="PATH", action="append", type=_path, default=[],
                            help="a file kept for the user; repeatable")
        # Kept for run(): a refusal of Report is a usage error.
        self._parser = parser

    def run(self, args: argparse.Namespace, jobs: JobsProvider) -> int:
        try:
            report = Report(status=ResultStatus(args.status), unproven=args.unproven,
                            questions=tuple(args.question), retro=args.retro, prs=tuple(args.pr),
                            kept=tuple(args.kept))
        except ValueError as e:
            self._parser.error(str(e))
        self.cli.out(str(jobs.finish(args.id, report)))
        self.cli.out(notify_line(args.id))
        return 0


def _numbers(text: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in text.split(","))


def _text(text: str) -> str:
    text = text.strip()
    if not text:
        raise argparse.ArgumentTypeError("empty path")
    return text


def _path(text: str) -> str:
    # Absolute against the session's cwd: the dispatcher reads it from another.
    return os.path.abspath(_text(text))
