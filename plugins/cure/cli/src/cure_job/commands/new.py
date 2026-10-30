"""``cure-job new`` — queue a handoff as a new job."""
from __future__ import annotations

import argparse

from .. import job_id
from ..providers.jobs import JobsProvider
from .base import STDIN, Command, notify_line, read_input


class NewCommand(Command):
    name = "new"
    usage = "cure-job new --slug SLUG [FILE]"
    help = "queue a handoff as a new job"
    description = ("Queue a handoff as a new job and print the job id and the message to send. The origin is "
                   "the session of $CLAUDE_CODE_MESSAGING_SOCKET; a handoff that names an origin is refused")

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("file", metavar="FILE", nargs="?", default=STDIN,
                            help="handoff file; - or absent reads stdin")
        parser.add_argument("--slug", metavar="SLUG", required=True, type=_slug_arg,
                            help="short name of the job, the last part of the job id")
        # Kept for run(): an unreadable FILE is a usage error.
        self._parser = parser

    def run(self, args: argparse.Namespace, jobs: JobsProvider) -> int:
        job_id = jobs.new(read_input(self._parser, "FILE", args.file), args.slug, self.cli.origin())
        self.cli.out(job_id)
        self.cli.out(notify_line(job_id))
        return 0


def _slug_arg(text: str) -> str:
    if not job_id.slugify(text):
        raise argparse.ArgumentTypeError(f"no character in [a-z0-9]: {text!r}")
    if job_id.ends_in_run_marker(text):
        raise argparse.ArgumentTypeError(f"ends in -r<digits>, the run marker of a session name: {text!r}")
    return text
