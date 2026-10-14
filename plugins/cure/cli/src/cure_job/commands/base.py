"""Base class for commands.

A command owns one subcommand (``cure-job <name> ...``). It declares its
arguments, calls one :class:`~cure_job.providers.jobs.JobsProvider` method and
prints through the output sink of the owning :class:`~cure_job.cli.Cli`.
"""
from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

from .. import job_id
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

    def __init__(self, cli: "Cli"):
        self.cli = cli

    def register(self, subparsers) -> None:
        parser = style(subparsers.add_parser(
            self.name, formatter_class=HelpFormatter,
            usage=self.usage, help=self.help, description=self.description))
        self.add_arguments(parser)
        parser.set_defaults(handler=self.run)

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Declare the arguments of the command. The default adds none."""

    def run(self, args: argparse.Namespace, jobs: JobsProvider) -> int:
        raise NotImplementedError


def job_id_arg(text: str) -> str:
    if not job_id.is_valid(text):
        raise argparse.ArgumentTypeError(f"invalid job id: {text!r}")
    return text
