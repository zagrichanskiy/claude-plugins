"""Command-line interface for cure-job.

:class:`Cli` owns the output sink and the :class:`~cure_job.providers.jobs.JobsProvider`,
assembles the root parser by asking each command to register itself, and drives
dispatch. :func:`main` is the composition root and reads the root, the
``config.json`` path and the binary from the environment: a test builds a
:class:`Cli` with its own root, its own ``config.json`` path and its own
``claude``, and can reach neither ``~/.claude``, ``~/.config`` nor the real
binary. :meth:`Cli.origin` reads the messaging socket of the calling session.
"""
from __future__ import annotations

import argparse
import functools
import os
import sys
import time
from pathlib import Path
from typing import Callable

from .claude import Claude, ClaudeCli
from . import config
from .clock import Clock, local_now
from .commands.approve import ApproveCommand
from .commands.claim import ClaimCommand
from .commands.close import CloseCommand
from .commands.config import ConfigCommand
from .commands.draft import DraftCommand
from .commands.drafted import DraftedCommand
from .commands.finish import FinishCommand
from .commands.launch import LaunchCommand
from .commands.list import ListCommand
from .commands.new import NewCommand
from .commands.next import NextCommand
from .commands.origin import OriginCommand
from .commands.prune import PruneCommand
from .commands.release import ReleaseCommand
from .commands.remove_sessions import RemoveSessionsCommand
from .commands.reported import ReportedCommand
from .commands.resume import ResumeCommand
from .commands.stop import StopCommand
from .errors import CureJobError
from .goal import PLUGIN_ROOT
from .help import HelpFormatter, style
from .providers.jobs import JobsProvider
from .store import JobStore

ROOT_ENV = "CURE_JOB_ROOT"
CLAUDE_ENV = "CURE_JOB_CLAUDE"
CONFIG_ENV = "CURE_JOB_CONFIG"
DEFAULT_ROOT = "~/.claude/cure"
DEFAULT_CLAUDE = "claude"
MESSAGING_SOCKET_ENV = "CLAUDE_CODE_MESSAGING_SOCKET"

#: Flush every line so a caller that reads a pipe sees the output at once.
_flush_print = functools.partial(print, flush=True)


class Cli:
    def __init__(self, *, root: Path, config_path: Path, claude: Claude, clock: Clock = local_now,
                 out: Callable[[str], None] = _flush_print, plugin_root: Path = PLUGIN_ROOT,
                 sleep: Callable[[float], None] = time.sleep, monotonic: Callable[[], float] = time.monotonic):
        self.out = out
        self.config_path = config_path
        self.version = config.plugin_version(plugin_root)
        self.config = config.load(config_path, root, self.version)
        self.jobs = JobsProvider(JobStore(root), claude, clock, plugin_root, sleep, monotonic, self.config)
        self._commands = [NewCommand(self), ListCommand(self), NextCommand(self), DraftCommand(self),
                          DraftedCommand(self), ApproveCommand(self), LaunchCommand(self), ResumeCommand(self),
                          ClaimCommand(self), ReleaseCommand(self), StopCommand(self), CloseCommand(self), OriginCommand(self), FinishCommand(self),
                          ReportedCommand(self), RemoveSessionsCommand(self), PruneCommand(self), ConfigCommand(self)]
        self._parser = self._build_parser()

    def origin(self) -> str | None:
        """The address of the calling session, ``uds:<socket path>``, or ``None`` outside a session."""
        socket = os.environ.get(MESSAGING_SOCKET_ENV)
        return f"uds:{socket}" if socket else None

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
        mode = getattr(args, "config_mode", "lenient")
        if mode == "strict" and self.config.problems:
            for problem in self.config.problems:
                print(problem, file=sys.stderr)
            return 1
        if mode == "lenient":
            for problem in self.config.problems:
                print(config.fallback(problem), file=sys.stderr)
        try:
            return args.handler(args, self.jobs)
        except CureJobError as e:  # expected operational failure; a real bug propagates
            print(f"error: {e}", file=sys.stderr)
            return 1


def main(argv: list[str] | None = None) -> int:
    # The environment is read on each call, never at import, so that a test
    # which sets it after the import is still isolated.
    root = Path(os.path.abspath(os.path.expanduser(os.environ.get(ROOT_ENV) or DEFAULT_ROOT)))
    config_path = os.environ.get(CONFIG_ENV) or os.path.join(
        os.environ.get("XDG_CONFIG_HOME") or "~/.config", "cure", config.FILE)
    config_path = Path(os.path.abspath(os.path.expanduser(config_path)))
    binary = os.environ.get(CLAUDE_ENV) or DEFAULT_CLAUDE
    # A relative path would break in `start`, which runs with another cwd. A
    # bare name is left to the PATH lookup.
    if os.sep in binary:
        binary = os.path.abspath(binary)
    try:
        cli = Cli(root=root, config_path=config_path, claude=ClaudeCli(binary))
    except CureJobError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return cli.run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
