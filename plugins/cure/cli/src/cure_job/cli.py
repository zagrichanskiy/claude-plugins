"""Command-line interface for cure-job.

:class:`Cli` owns the output sink and the :class:`~cure_job.providers.jobs.JobsProvider`,
assembles the root parser by asking each command to register itself, and drives
dispatch. :func:`main` is the composition root and the only reader of the
environment: a test builds a :class:`Cli` with its own root and its own
``claude``, and can reach neither ``~/.claude`` nor the real binary by default.
"""
from __future__ import annotations

import argparse
import functools
import os
import sys
from pathlib import Path
from typing import Callable

from .claude import Claude, ClaudeCli
from .clock import Clock, local_now
from .commands.claim import ClaimCommand
from .commands.close import CloseCommand
from .commands.finish import FinishCommand
from .commands.launch import LaunchCommand
from .commands.list import ListCommand
from .commands.new import NewCommand
from .commands.origin import OriginCommand
from .commands.prune import PruneCommand
from .errors import CureJobError
from .goal import PLUGIN_ROOT
from .help import HelpFormatter, style
from .providers.jobs import JobsProvider
from .store import JobStore

ROOT_ENV = "CURE_JOB_ROOT"
CLAUDE_ENV = "CURE_JOB_CLAUDE"
DEFAULT_ROOT = "~/.claude/cure"
DEFAULT_CLAUDE = "claude"

#: Flush every line so a caller that reads a pipe sees the output at once.
_flush_print = functools.partial(print, flush=True)


class Cli:
    def __init__(self, *, root: Path, claude: Claude, clock: Clock = local_now,
                 out: Callable[[str], None] = _flush_print, plugin_root: Path = PLUGIN_ROOT):
        self.out = out
        self.jobs = JobsProvider(JobStore(root), claude, clock, plugin_root)
        self._commands = [NewCommand(self), ListCommand(self), LaunchCommand(self),
                          ClaimCommand(self), CloseCommand(self), OriginCommand(self), FinishCommand(self),
                          PruneCommand(self)]
        self._parser = self._build_parser()

    def _build_parser(self) -> argparse.ArgumentParser:
        parser = style(argparse.ArgumentParser(
            prog="cure-job", formatter_class=HelpFormatter,
            usage="cure-job COMMAND",
            description="Queue, launch and track the jobs of the cure dispatcher"))
        # The command is optional at the argparse level so that a bare
        # `cure-job` prints help (like -h) instead of a terse error — see run().
        commands = parser.add_subparsers(dest="command", required=False)
        for command in self._commands:
            command.register(commands)
        return parser

    def run(self, argv: list[str] | None = None) -> int:
        args = self._parser.parse_args(argv)
        if not hasattr(args, "handler"):
            self._parser.print_help()
            return 0
        try:
            return args.handler(args, self.jobs)
        except CureJobError as e:  # expected operational failure; a real bug propagates
            print(f"error: {e}", file=sys.stderr)
            return 1


def main(argv: list[str] | None = None) -> int:
    # The environment is read on each call, never at import, so that a test
    # which sets it after the import is still isolated.
    root = Path(os.path.abspath(os.path.expanduser(os.environ.get(ROOT_ENV) or DEFAULT_ROOT)))
    binary = os.environ.get(CLAUDE_ENV) or DEFAULT_CLAUDE
    # A relative path would break in `start`, which runs with another cwd. A
    # bare name is left to the PATH lookup.
    if os.sep in binary:
        binary = os.path.abspath(binary)
    return Cli(root=root, claude=ClaudeCli(binary)).run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
