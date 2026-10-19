"""``cure-job claim`` — add resources to the ones a job's run names."""
from __future__ import annotations

import argparse

from ..providers.jobs import CLAIM_WAIT_MAX_SECONDS, JobsProvider
from .base import RESOURCE_CHOICES, Command, job_id_arg, resource_arg


class ClaimCommand(Command):
    name = "claim"
    usage = "cure-job claim ID RESOURCE... [--wait SECONDS]"
    help = "claim resources for a job's run"
    description = ("Claim resources for the launched run of a job. Exit 0 means the job holds every one. "
                   "A short hold (device:, build:) ends at release, at the run's result or at the next run")

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("id", metavar="ID", type=job_id_arg, help="job id")
        parser.add_argument("resources", metavar="RESOURCE", nargs="+", type=resource_arg, help=RESOURCE_CHOICES)
        parser.add_argument("--wait", metavar="SECONDS", type=_wait_arg, default=0,
                            help=f"wait up to SECONDS (at most {CLAIM_WAIT_MAX_SECONDS}) for held resources")

    def run(self, args: argparse.Namespace, jobs: JobsProvider) -> int:
        jobs.claim(args.id, args.resources, args.wait)
        return 0


def _wait_arg(text: str) -> int:
    try:
        seconds = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid seconds: {text!r}") from None
    if not 0 <= seconds <= CLAIM_WAIT_MAX_SECONDS:
        raise argparse.ArgumentTypeError(f"{seconds} is outside 0..{CLAIM_WAIT_MAX_SECONDS}")
    return seconds
