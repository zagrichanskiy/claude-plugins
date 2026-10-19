"""``cure-job list`` — every job with its derived state."""
from __future__ import annotations

import argparse
import json
from typing import Mapping

from ..claude import Session
from ..providers.jobs import JobsProvider
from ..state import JobView, State
from ..store import InvalidJob
from .base import Command


class ListCommand(Command):
    name = "list"
    usage = "cure-job list [--json]"
    help = "list every job with its state"
    description = "List every job with its derived state, in ascending id order"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--json", action="store_true",
                            help="print one compact JSON array instead of text")

    def run(self, args: argparse.Namespace, jobs: JobsProvider) -> int:
        listing = jobs.listing()
        rows = sorted([job_row(view, listing.sessions) for view in listing.views]
                      + [invalid_row(job) for job in listing.invalid],
                      key=lambda row: row["id"])
        if args.json:
            self.cli.out(json.dumps(rows, separators=(",", ":")))
            return 0
        width = max((len(row["id"]) for row in rows), default=0)
        for row in rows:
            line = f"{row['id']:<{width}}  {row['state']}"
            if row["blocked-by"]:
                line += "  blocked-by=" + ",".join(row["blocked-by"])
            if row["prs"]:
                line += "  prs=" + ",".join(row["prs"])
            if row["state"] == INVALID:
                line += "  " + row["problem"]
            self.cli.out(line)
        return 0


#: The state of a job whose stored files do not read; ``problem`` names the file.
INVALID = "invalid"


def invalid_row(job: InvalidJob) -> dict:
    return {"id": job.id, "state": INVALID, "dir": str(job.dir), "run": None, "session": None,
            "origin": None, "resources": [], "blocked-by": [], "problem": job.problem,
            "waiting-for": None, "reported": None, "sessions-removed": None, "prs": []}


def job_row(view: JobView, sessions: Mapping[str, Session]) -> dict:
    record = view.record
    waiting_for = None
    if view.state is State.BLOCKED:
        waiting_for = sessions[record.session].waiting_for
    return {
        "id": record.id,
        "state": view.state.value,
        "dir": str(record.dir),
        "run": record.run,
        "session": record.session,
        "origin": record.origin,
        "resources": sorted(record.resources),
        "blocked-by": list(view.blocked_by),
        "problem": record.result.problem if record.result else None,
        "waiting-for": waiting_for,
        "reported": record.reported,
        "sessions-removed": record.sessions_removed,
        "prs": list(record.result.prs) if record.result else [],
    }
