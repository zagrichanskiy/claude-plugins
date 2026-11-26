"""Resource names: ``device:bench`` or ``build:<absolute path>``, each a short hold."""
from __future__ import annotations

import enum
import os

DEVICE_BENCH = "device:bench"

_DEVICE_PREFIX = "device:"
_BUILD_PREFIX = "build:"


class Kind(enum.Enum):
    DEVICE = "device"
    BUILD = "build"


def build(path: str) -> str:
    """The resource name of a build directory. Symlinks are resolved: two names never share one directory."""
    if not os.path.isabs(path):
        raise ValueError(f"{path!r} is not an absolute path")
    return _BUILD_PREFIX + os.path.realpath(path)


def kind(name: str) -> Kind | None:
    """``None`` for a name of no current kind, such as a repository claimed by an earlier version."""
    if name.startswith(_DEVICE_PREFIX):
        return Kind.DEVICE
    if name.startswith(_BUILD_PREFIX):
        return Kind.BUILD
    return None


def is_short_hold(name: str) -> bool:
    """A resource held for one step of a run, not to the end of the job."""
    return kind(name) is not None


def parse(text: str) -> str:
    if text == DEVICE_BENCH:
        return text
    if text.startswith(_BUILD_PREFIX):
        return build(text[len(_BUILD_PREFIX):])
    raise ValueError(f"{text!r} is not a short hold")
