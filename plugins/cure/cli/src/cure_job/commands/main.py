"""``cure-job main-claim``, ``main-release`` and ``main-check`` — the claim ``main`` on the main workspace."""
from __future__ import annotations

import argparse
import json

from .. import main_claim
from ..goal import PLUGIN_ROOT
from ..kinds import CURE_JOB
from ..providers.jobs import JobsProvider
from .base import Command, read_stdin


class MainClaimCommand(Command):
    name = "main-claim"
    usage = "cure-job main-claim SESSION"
    help = "take the claim main for a session"
    description = ("Take the claim main, which an interactive session needs before its first write in the main "
                   "workspace. Exit 0 means SESSION holds it; exit 1 names the session that holds it and the "
                   "main-release command for it")

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("session", metavar="SESSION", type=_session_arg, help="the session id")

    def run(self, args: argparse.Namespace, jobs: JobsProvider) -> int:
        main_claim.claim(jobs.store, args.session)
        return 0


class MainReleaseCommand(MainClaimCommand):
    name = "main-release"
    usage = "cure-job main-release SESSION"
    help = "release the claim main of a session"
    description = "End the claim main of SESSION. Exit 0 means SESSION does not hold it"

    def run(self, args: argparse.Namespace, jobs: JobsProvider) -> int:
        main_claim.release(jobs.store, args.session)
        return 0


class MainCheckCommand(Command):
    name = "main-check"
    usage = "cure-job main-check < PAYLOAD"
    help = "deny a write in the main workspace without the claim main"
    description = ("Read a PreToolUse hook payload on standard input. Print nothing to allow the tool call, or a "
                   "deny decision when it writes in the main workspace and its session does not hold the claim main")

    def run(self, args: argparse.Namespace, jobs: JobsProvider) -> int:
        try:
            payload = json.loads(read_stdin())
        except ValueError as e:
            payload = e
        if isinstance(payload, dict):
            reason = main_claim.denial(jobs.store, payload, jobs.config["slots.root"], jobs.config["worktree.root"],
                                       PLUGIN_ROOT / CURE_JOB)
        else:
            problem = payload if isinstance(payload, ValueError) else "not a JSON object"
            reason = f"cure-job main-check cannot read the hook payload: {problem}"
        if reason is not None:
            self.cli.out(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                                            "permissionDecision": "deny",
                                                            "permissionDecisionReason": reason}}))
        return 0


def _session_arg(text: str) -> str:
    if not text.strip() or "\n" in text:
        raise argparse.ArgumentTypeError(f"invalid session id: {text!r}")
    return text
