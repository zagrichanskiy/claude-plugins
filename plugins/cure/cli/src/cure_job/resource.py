"""Resource names: a repository path or ``device:bench``."""
from __future__ import annotations

import os

DEVICE_BENCH = "device:bench"


def repo(path: str) -> str:
    """The resource name of a repository path. Symlinks are not resolved."""
    if not os.path.isabs(path):
        raise ValueError(f"{path!r} is not an absolute path")
    return os.path.normpath(path)


def parse(text: str) -> str:
    return text if text == DEVICE_BENCH else repo(text)
