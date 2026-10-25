"""``cure-job config`` — read, check and create ``config.json``."""
from __future__ import annotations

import argparse
import json
import sys

from .. import config
from ..help import HelpFormatter, style
from ..providers.jobs import JobsProvider
from .base import Command


class ConfigCommand(Command):
    name = "config"
    usage = "cure-job config get [KEY] | check | init"
    help = "read, check or create config.json"
    description = (f"Read, check or create {config.FILE} at $CURE_JOB_CONFIG, "
                   "else $XDG_CONFIG_HOME/cure/config.json, else ~/.config/cure/config.json")

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        actions = parser.add_subparsers(dest="config_action", required=True)
        get = style(actions.add_parser("get", formatter_class=HelpFormatter, usage="cure-job config get [KEY]",
                                       help="print the effective configuration, or one value, as JSON"))
        get.add_argument("key", metavar="KEY", nargs="?", help="a dotted config.json key, such as handoff.delivery")
        style(actions.add_parser("check", formatter_class=HelpFormatter, usage="cure-job config check",
                                 help="exit 1 when config.json has an error")).set_defaults(config_mode="strict")
        style(actions.add_parser("init", formatter_class=HelpFormatter, usage="cure-job config init",
                                 help="move config.json from the state root, else write it from the defaults "
                                      "and defaults.md and rename defaults.md to defaults.md.bak")).set_defaults(config_mode="none")

    def run(self, args: argparse.Namespace, jobs: JobsProvider) -> int:
        if args.config_action == "init":
            self.cli.out(str(config.init(self.cli.config_path, jobs.store.root, self.cli.version,
                                         lambda line: print(line, file=sys.stderr))))
        elif args.config_action == "get":
            values = self.cli.config.values
            if args.key is None:
                self.cli.out(json.dumps(config.nest(values), separators=(",", ":")))
            elif args.key in values:
                self.cli.out(json.dumps(values[args.key]))
            else:
                problem = config.removed(args.key)
                raise config.ConfigError(f"{problem.key}: {problem.problem}" if problem else f"unknown key: {args.key}")
        return 0
