"""Providers — the domain layer.

A provider holds no argparse knowledge and prints nothing. It is tested with a
store on a temporary directory, a fake ``claude`` and a fake clock.
"""
from .jobs import JobsProvider

__all__ = ["JobsProvider"]
