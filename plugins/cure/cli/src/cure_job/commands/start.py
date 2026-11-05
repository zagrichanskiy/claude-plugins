"""``cure-job start`` — start a session of a kind other than work for a job."""
from __future__ import annotations

import argparse
import sys

from ..errors import CureJobError
from ..kinds import event_kinds
from ..providers.jobs import JobsProvider
from ..worker import RunArguments
from .base import Command, job_id_arg, kind_arg
from .launch import claude_args

_STDIN = "-"


class StartCommand(Command):
    name = "start"
    usage = "cure-job start ID KIND [--input FILE|-] [-- --permission-mode MODE]"
    help = "start a session of a kind other than work"
    description = ("Start the next session of KIND for a job in the background and print the session name. "
                   "A work session starts with cure-job launch")

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        kinds = event_kinds(self.cli.jobs.kinds)
        parser.add_argument("id", metavar="ID", type=job_id_arg, help="job id")
        parser.add_argument("kind", metavar="KIND", type=kind_arg(kinds, "work starts with cure-job launch"),
                            help="the session kind: " + (", ".join(kinds) or "none in this version"))
        parser.add_argument("options", metavar="OPTION", nargs=argparse.REMAINDER,
                            help="--input FILE: the input of the session, copied to the job; - reads stdin. "
                                 "After --, only --permission-mode " + "|".join(RunArguments.MODES)
                                 + "; passed to claude before the prompt")
        # A REMAINDER positional takes every argument after KIND, so --input is parsed from it.
        self._options = argparse.ArgumentParser(prog="cure-job start", usage=self.usage, add_help=False)
        self._options.add_argument("--input", metavar="FILE")
        self._options.add_argument("claude_args", nargs=argparse.REMAINDER)

    def run(self, args: argparse.Namespace, jobs: JobsProvider) -> int:
        options = self._options.parse_args(args.options)
        self.cli.out(jobs.start(args.id, args.kind, claude_args(options), _read_input(options.input)))
        return 0


def _read_input(source: str | None) -> str | None:
    if source is None:
        return None
    if source == _STDIN:
        return sys.stdin.read()
    try:
        with open(source, encoding="utf-8") as text:
            return text.read()
    except (OSError, UnicodeDecodeError) as e:
        raise CureJobError(f"cannot read the input {source}: {e}") from e
