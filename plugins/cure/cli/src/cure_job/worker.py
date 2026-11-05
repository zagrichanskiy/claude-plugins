"""The ``claude`` arguments the caller of ``launch`` and ``resume`` may choose: only the permission mode.

The permission rules a session needs to report back come from its kind
(:func:`cure_job.kinds.settings_arguments`).
"""
from __future__ import annotations

from typing import Sequence

from .errors import CureJobError


class RunArguments:
    """The arguments after ``--``: at most one ``--permission-mode`` of :attr:`MODES`."""

    OPTION = "--permission-mode"
    MODES = ("acceptEdits", "default", "auto")

    def __init__(self, given: Sequence[str]):
        self.mode = self._mode(list(given))

    def arguments(self) -> list[str]:
        return [self.OPTION, self.mode] if self.mode is not None else []

    def _mode(self, given: list[str]) -> str | None:
        if not given:
            return None
        if len(given) == 2 and given[0] == self.OPTION:
            mode = given[1]
        elif len(given) == 1 and given[0].startswith(self.OPTION + "="):
            mode = given[0][len(self.OPTION) + 1:]
        else:
            raise CureJobError(f"refused claude arguments {' '.join(given)!r}; after -- only "
                               f"{self.OPTION} {'|'.join(self.MODES)} is accepted")
        if mode not in self.MODES:
            raise CureJobError(f"refused {self.OPTION} {mode!r}; expected one of {', '.join(self.MODES)}")
        return mode

