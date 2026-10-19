"""``cure-job release`` — end a job's short hold on a resource."""
from __future__ import annotations

import argparse

from ..providers.jobs import JobsProvider
from .base import RESOURCE_CHOICES, Command, job_id_arg, resource_arg


class ReleaseCommand(Command):
    name = "release"
    usage = "cure-job release ID RESOURCE"
    help = "release a short hold of a job"
    description = ("Release a device: or build: resource of a job. Exit 0 means the job does not hold it. "
                   "A repository is held until the job ends")

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("id", metavar="ID", type=job_id_arg, help="job id")
        parser.add_argument("resource", metavar="RESOURCE", type=resource_arg, help=RESOURCE_CHOICES)

    def run(self, args: argparse.Namespace, jobs: JobsProvider) -> int:
        jobs.release(args.id, args.resource)
        return 0
