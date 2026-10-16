"""The clock seam and the one timestamp format the job files use."""
from __future__ import annotations

from datetime import datetime
from typing import Callable

Clock = Callable[[], datetime]

_FORMAT = "%Y-%m-%dT%H:%M:%S%z"


def local_now() -> datetime:
    """The current time: aware, with the fixed system offset of this instant, cut to whole seconds."""
    # A fixed-offset timezone, never a ZoneInfo: two datetimes that share one
    # ZoneInfo subtract by wall clock and are an hour wrong across a DST shift.
    return datetime.now().astimezone().replace(microsecond=0)


def format_local(moment: datetime) -> str:
    """``moment`` with its own offset, e.g. ``2026-10-14T17:42:05+03:00``. Never converts."""
    if moment.utcoffset() is None:
        raise ValueError(f"naive datetime {moment.isoformat()} has no offset")
    return moment.isoformat(timespec="seconds")


def parse_local(text: str) -> datetime:
    # strptime with %z, not fromisoformat: fromisoformat accepts a missing
    # offset and returns a naive datetime, which `derive` cannot subtract.
    return datetime.strptime(text, _FORMAT)
