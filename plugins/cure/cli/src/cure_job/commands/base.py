"""Base class for commands.

A command owns one subcommand (``cure-job <name> ...``). It declares its
arguments, calls one :class:`~cure_job.providers.jobs.JobsProvider` method and
prints through the output sink of the owning :class:`~cure_job.cli.Cli`.
"""
from __future__ import annotations

import argparse
import io
import sys
from typing import TYPE_CHECKING, Callable, Mapping

from .. import job_id, resource
from ..events import WORK
from ..help import HelpFormatter, style
from ..providers.jobs import JobsProvider

if TYPE_CHECKING:
    from ..cli import Cli
    from ..kinds import SessionKind


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


#: The session that ``finish`` and ``new`` tell to wake.
DISPATCHER = "dispatcher"


def notify_line(job_id: str) -> str:
    """The line that names the message to send once the job changed."""
    return f'notify: SendMessage {DISPATCHER} "job {job_id}"'


def read_stdin() -> str:
    """Standard input decoded as UTF-8 with universal newlines, as a file opened in text mode reads."""
    text = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8")
    try:
        return text.read()
    finally:
        # Without detach, the collected wrapper would close sys.stdin.buffer.
        text.detach()


def job_id_arg(text: str) -> str:
    if not job_id.is_valid(text):
        raise argparse.ArgumentTypeError(f"invalid job id: {text!r}")
    return text


def kind_arg(kinds: Mapping[str, "SessionKind"], work: str | None = None) -> Callable[[str], "SessionKind"]:
    """The parser of a session kind among ``kinds``. ``work`` is the refusal of the work kind when it is not one."""
    def parse(text: str) -> "SessionKind":
        if text in kinds:
            return kinds[text]
        if text == WORK and work is not None:
            raise argparse.ArgumentTypeError(work)
        raise argparse.ArgumentTypeError(f"unknown session kind {text!r}; expected {', '.join(kinds) or 'none'}")
    return parse


#: The resource names ``claim`` and ``release`` accept, for help and errors.
RESOURCE_CHOICES = f"{resource.DEVICE_BENCH}, build:<absolute path> or an absolute repository path"


def resource_arg(text: str) -> str:
    try:
        return resource.parse(text)
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"{e}; expected {RESOURCE_CHOICES}") from e
