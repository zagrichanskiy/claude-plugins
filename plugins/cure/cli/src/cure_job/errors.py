"""The errors the CLI is expected to report.

``CureJobError`` marks an operational failure: a handoff that does not parse, a
job in the wrong state, a resource another job holds. :class:`~cure_job.cli.Cli`
reports each as a one-line ``error: ...`` with exit 1 and catches nothing else,
so a programming error keeps its traceback.
"""
from __future__ import annotations


class CureJobError(Exception):
    """An expected operational failure the CLI reports as ``error: ...``."""


class HandoffError(CureJobError):
    """Handoff text, or a stored ``handoff.md``, is invalid."""


class UnknownJob(CureJobError):
    """No ``jobs/<id>/handoff.md`` exists."""


class JobStateError(CureJobError):
    """The operation is not allowed in the job's state."""


class ResourceHeld(CureJobError):
    """Another open job holds a resource, so a launch or a claim is refused."""

    def __init__(self, resource: str, holder: str):
        super().__init__(f"{resource} is held by {holder}")
        self.resource = resource
        self.holder = holder


class SessionGone(CureJobError):
    """The session of a job's latest run is no longer listed, so ``resume`` cannot continue it."""


class ReportError(CureJobError):
    """A ``finish`` value has the wrong form: a ``pr`` that is not a pull request URL, a relative ``retro``."""


class StoreError(CureJobError):
    """The state root cannot be read or written, or ``dispatch.jsonl`` is malformed."""


class PluginError(CureJobError):
    """A file the cure plugin ships is missing."""


class ClaudeError(CureJobError):
    """The ``claude`` binary is missing, timed out, failed or printed unusable output."""


class ClaudeOutcomeUnknown(ClaudeError):
    """The binary was started and did not finish, so a session may exist."""
