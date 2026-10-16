"""``cure-job claim`` — add a resource to the ones a job names."""
from __future__ import annotations

import argparse

from .. import resource
from ..providers.jobs import JobsProvider
from .base import Command, job_id_arg


class ClaimCommand(Command):
    name = "claim"
    usage = "cure-job claim ID RESOURCE"
    help = "claim a resource for a job"
    description = "Claim a resource for a job. Exit 0 means the job holds the resource"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("id", metavar="ID", type=job_id_arg, help="job id")
        parser.add_argument("resource", metavar="RESOURCE", type=_resource_arg,
                            help=f"{resource.DEVICE_BENCH} or an absolute repository path")

    def run(self, args: argparse.Namespace, jobs: JobsProvider) -> int:
        jobs.claim(args.id, args.resource)
        return 0


def _resource_arg(text: str) -> str:
    try:
        return resource.parse(text)
    except ValueError as e:
        raise argparse.ArgumentTypeError(f"{e}; expected {resource.DEVICE_BENCH} or an absolute path") from e
