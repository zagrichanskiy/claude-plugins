"""argparse styling shared by every command parser.

Docker-style help: a ``Usage:`` prefix, no ``{choices}`` header, and each
option's metavar shown once (``--slug SLUG``) with its help on one line. A
description or epilog of several lines keeps its line breaks.
"""
from __future__ import annotations

import argparse


class HelpFormatter(argparse.HelpFormatter):
    def __init__(self, prog):
        super().__init__(prog, max_help_position=32)

    def add_usage(self, usage, actions, groups, prefix=None):
        return super().add_usage(usage, actions, groups, prefix or "Usage:  ")

    def _fill_text(self, text, width, indent):
        # A text of several lines is laid out by hand, as the finish table is.
        if "\n" in text:
            return "".join(indent + line for line in text.splitlines(keepends=True))
        return super()._fill_text(text, width, indent)

    def _format_action(self, action: argparse.Action) -> str:
        text = super()._format_action(action)
        if action.nargs == argparse.PARSER:
            text = "\n".join(text.split("\n")[1:])
        return text

    def _format_action_invocation(self, action: argparse.Action) -> str:
        if not action.option_strings or action.nargs == 0:
            return super()._format_action_invocation(action)
        metavar = self._format_args(action, self._get_default_metavar_for_optional(action))
        return ", ".join(action.option_strings) + " " + metavar


def style(parser: argparse.ArgumentParser) -> argparse.ArgumentParser:
    parser._optionals.title = "Options"
    parser._positionals.title = "Commands"
    return parser
