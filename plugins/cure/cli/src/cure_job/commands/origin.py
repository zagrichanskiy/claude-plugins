"""``cure-job origin`` — set the session a job reports back to."""
from __future__ import annotations

import argparse

from ..providers.jobs import JobsProvider
from .base import Command, job_id_arg


class OriginCommand(Command):
    name = "origin"
    usage = "cure-job origin ID ADDRESS"
    help = "set the session a job reports back to, before its first launch"
    description = ("Set the session a job reports back to, before its first launch. A job that already has "
                   "an origin is refused")

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("id", metavar="ID", type=job_id_arg, help="job id")
        parser.add_argument("address", metavar="ADDRESS", type=_address_arg,
                            help="the address a message to the origin session goes to")

    def run(self, args: argparse.Namespace, jobs: JobsProvider) -> int:
        jobs.set_origin(args.id, args.address)
        return 0


def _address_arg(text: str) -> str:
    if not text or text != text.strip() or len(text.splitlines()) != 1:
        raise argparse.ArgumentTypeError(f"invalid address: {text!r}; expected one non-empty line "
                                         "without surrounding whitespace")
    return text
