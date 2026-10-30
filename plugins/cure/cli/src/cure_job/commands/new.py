"""``cure-job new`` — queue a handoff as a new job."""
from __future__ import annotations

import argparse
import sys

from .. import job_id
from ..frontmatter import is_writable
from ..providers.jobs import JobsProvider
from .base import Command, notify_line

_STDIN = "-"


class NewCommand(Command):
    name = "new"
    usage = "cure-job new --slug SLUG [--ticket-summary TEXT] [FILE]"
    help = "queue a handoff as a new job"
    description = ("Queue a handoff as a new job and print the job id and the message to send. The origin is "
                   "the session of $CLAUDE_CODE_MESSAGING_SOCKET; a handoff that names an origin is refused")

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("file", metavar="FILE", nargs="?", default=_STDIN,
                            help="handoff file; - or absent reads stdin")
        parser.add_argument("--slug", metavar="SLUG", required=True, type=_slug_arg,
                            help="short name of the job, the last part of the job id")
        parser.add_argument("--ticket-summary", metavar="TEXT", type=_summary_arg,
                            help="the ticket's title, stored as the handoff's ticket-summary")
        # Kept for run(): an unreadable FILE is a usage error.
        self._parser = parser

    def run(self, args: argparse.Namespace, jobs: JobsProvider) -> int:
        job_id = jobs.new(self._read(args.file), args.slug, self.cli.origin(), args.ticket_summary)
        self.cli.out(job_id)
        self.cli.out(notify_line(job_id))
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
    if job_id.ends_in_run_marker(text):
        raise argparse.ArgumentTypeError(f"ends in -r<digits>, the run marker of a session name: {text!r}")
    return text


def _summary_arg(text: str) -> str:
    if not is_writable(text.strip()):
        raise argparse.ArgumentTypeError(f"empty or more than one line: {text!r}")
    return text.strip()
