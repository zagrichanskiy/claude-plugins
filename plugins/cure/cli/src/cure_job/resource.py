"""Resource names: a repository path, ``device:bench`` or ``build:<absolute path>``."""
from __future__ import annotations

import enum
import os

DEVICE_BENCH = "device:bench"

_DEVICE_PREFIX = "device:"
_BUILD_PREFIX = "build:"


class Kind(enum.Enum):
    REPO = "repo"
    DEVICE = "device"
    BUILD = "build"


def repo(path: str) -> str:
    """The resource name of a repository path. Symlinks are not resolved."""
    if not os.path.isabs(path):
        raise ValueError(f"{path!r} is not an absolute path")
    return os.path.normpath(path)


def build(path: str) -> str:
    """The resource name of a build directory. Symlinks are resolved: two names never share one directory."""
    if not os.path.isabs(path):
        raise ValueError(f"{path!r} is not an absolute path")
    return _BUILD_PREFIX + os.path.realpath(path)


def kind(name: str) -> Kind:
    if name.startswith(_DEVICE_PREFIX):
        return Kind.DEVICE
    if name.startswith(_BUILD_PREFIX):
        return Kind.BUILD
    return Kind.REPO


def is_short_hold(name: str) -> bool:
    """A resource held for one step of a run, not to the end of the job."""
    return kind(name) in (Kind.DEVICE, Kind.BUILD)


def parse(text: str) -> str:
    if text == DEVICE_BENCH:
        return text
    if text.startswith(_BUILD_PREFIX):
        return build(text[len(_BUILD_PREFIX):])
    return repo(text)
