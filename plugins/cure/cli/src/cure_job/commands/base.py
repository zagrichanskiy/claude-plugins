"""Base class for commands.

A command owns one subcommand (``cure-job <name> ...``). It declares its
arguments, calls one :class:`~cure_job.providers.jobs.JobsProvider` method and
prints through the output sink of the owning :class:`~cure_job.cli.Cli`.
"""
from __future__ import annotations

import argparse
import sys
from typing import TYPE_CHECKING

from .. import job_id, resource
from ..help import HelpFormatter, style
from ..providers.jobs import JobsProvider

if TYPE_CHECKING:
    from ..cli import Cli


class Command:
    name: str
    usage: str
    #: Must be non-empty: argparse lists a subcommand in --help only when it has help.
    help: str
    description: str
    epilog: str | None = None

    def __init__(self, cli: "Cli"):
        self.cli = cli

    def register(self, subparsers) -> None:
        parser = style(subparsers.add_parser(
            self.name, formatter_class=HelpFormatter,
            usage=self.usage, help=self.help, description=self.description, epilog=self.epilog))
        self.add_arguments(parser)
        parser.set_defaults(handler=self.run)

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Declare the arguments of the command. The default adds none."""

    def run(self, args: argparse.Namespace, jobs: JobsProvider) -> int:
        raise NotImplementedError


#: The argument value that reads stdin.
STDIN = "-"


def read_input(parser: argparse.ArgumentParser, label: str, path: str) -> str:
    """The text of ``path``, or of stdin for ``-``. An unreadable file is a usage error of ``label``."""
    if path == STDIN:
        return sys.stdin.read()
    try:
        with open(path, encoding="utf-8") as source:
            return source.read()
    except (OSError, UnicodeDecodeError) as e:
        parser.error(f"argument {label}: cannot read {path}: {e}")


#: The session that ``finish``, ``drafted`` and ``new`` tell to wake.
DISPATCHER = "dispatcher"


def notify_line(job_id: str) -> str:
    """The line that names the message to send once the job changed."""
    return f'notify: SendMessage {DISPATCHER} "job {job_id}"'


def job_id_arg(text: str) -> str:
    if not job_id.is_valid(text):
        raise argparse.ArgumentTypeError(f"invalid job id: {text!r}")
    return text


#: The resource names ``claim`` and ``release`` accept, for help and errors.
RESOURCE_CHOICES = f"{resource.DEVICE_BENCH}, build:<absolute path> or an absolute repository path"


def resource_arg(text: str) -> str:
    try:
        return resource.parse(text)
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"{e}; expected {RESOURCE_CHOICES}") from e
