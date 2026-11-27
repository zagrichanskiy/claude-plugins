"""Resource names: ``device:bench`` or ``build:<absolute path>``, each a short hold, and ``slot:<absolute path>``,
the workspace slot a job holds until it ends."""
from __future__ import annotations

import enum
import os

DEVICE_BENCH = "device:bench"

_DEVICE_PREFIX = "device:"
_BUILD_PREFIX = "build:"
_SLOT_PREFIX = "slot:"


class Kind(enum.Enum):
    DEVICE = "device"
    BUILD = "build"


def build(path: str) -> str:
    """The resource name of a build directory. Symlinks are resolved: two names never share one directory."""
    if not os.path.isabs(path):
        raise ValueError(f"{path!r} is not an absolute path")
    return _BUILD_PREFIX + os.path.realpath(path)


def slot(path: str) -> str:
    """The resource name of a workspace slot, with symlinks resolved as in :func:`build`."""
    return _SLOT_PREFIX + os.path.realpath(path)


def slot_path(name: str) -> str | None:
    """The directory of a slot resource name; ``None`` for a name of another kind."""
    return name[len(_SLOT_PREFIX):] if name.startswith(_SLOT_PREFIX) else None


def kind(name: str) -> Kind | None:
    """``None`` for a name that is no short hold: a slot, or a repository claimed by an earlier version."""
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
