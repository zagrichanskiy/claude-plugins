"""``cure-job new`` — queue a handoff as a new job."""
from __future__ import annotations

import argparse
import sys

from .. import job_id
from ..providers.jobs import JobsProvider
from .base import Command

_STDIN = "-"


class NewCommand(Command):
    name = "new"
    usage = "cure-job new --slug SLUG [FILE]"
    help = "queue a handoff as a new job"
    description = "Queue a handoff as a new job and print the job id"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("file", metavar="FILE", nargs="?", default=_STDIN,
                            help="handoff file; - or absent reads stdin")
        parser.add_argument("--slug", metavar="SLUG", required=True, type=_slug_arg,
                            help="short name of the job, the last part of the job id")
        # Kept for run(): an unreadable FILE is a usage error.
        self._parser = parser

    def run(self, args: argparse.Namespace, jobs: JobsProvider) -> int:
        self.cli.out(jobs.new(self._read(args.file), args.slug))
        return 0

    def _read(self, path: str) -> str:
        if path == _STDIN:
            return sys.stdin.read()
        try:
            with open(path, encoding="utf-8") as source:
                return source.read()
        except (OSError, UnicodeDecodeError) as e:
            self._parser.error(f"argument FILE: cannot read {path}: {e}")


def _slug_arg(text: str) -> str:
    if not job_id.slugify(text):
        raise argparse.ArgumentTypeError(f"no character in [a-z0-9]: {text!r}")
    return text
