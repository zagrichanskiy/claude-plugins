"""Event lines: one compact JSON object each; unknown events are skipped, bad lines are errors."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from cure_job.events import (Claim, Closed, DraftEnded, DraftMode, DraftStarted, Launched, SessionsRemoved, decode,
                             encode)

AT = datetime(2026, 10, 13, 17, 42, 5, tzinfo=timezone.utc)


def test_launched_line_shape():
    event = Launched(1, "261013-1742-video-core-fps-clamp", AT)
    assert encode(event) == ('{"event":"launched","run":1,"session":"261013-1742-video-core-fps-clamp",'
                             '"at":"2026-10-13T17:42:05+00:00"}')


def test_claim_line_shape():
    assert encode(Claim("device:bench")) == '{"event":"claim","resource":"device:bench"}'


def test_closed_line_shape():
    assert encode(Closed("superseded")) == '{"event":"closed","reason":"superseded"}'


def test_draft_line_shapes():
    assert encode(DraftStarted(1, "draft-x-1", DraftMode.APPLY, AT)) == (
        '{"event":"draft-started","n":1,"session":"draft-x-1","mode":"apply","at":"2026-10-13T17:42:05+00:00"}')
    assert encode(DraftEnded(1, 2, ("a", "b", "c"), AT)) == (
        '{"event":"draft-ended","n":1,"open":2,"summary":["a","b","c"],"at":"2026-10-13T17:42:05+00:00"}')


@pytest.mark.parametrize("event", [Launched(2, "x-r2", AT), Claim("/work/a"), Closed(""), SessionsRemoved(AT),
                                   DraftStarted(3, "draft-x-3", DraftMode.WRITE, AT),
                                   DraftEnded(3, 0, ("a", "b", "c"), AT)])
def test_decode_inverts_encode(event):
    assert decode(encode(event)) == event


def test_encode_has_no_newline():
    assert "\n" not in encode(Closed("a\nb"))


def test_decode_unknown_event_is_none():
    assert decode('{"event":"paused"}') is None


def test_decode_ignores_unknown_keys():
    assert decode('{"event":"claim","resource":"/a","extra":1}') == Claim("/a")


@pytest.mark.parametrize("line", [
    "not json",
    "[1,2]",
    '"text"',
    '{"event":"claim"}',
    '{"event":"claim","resource":3}',
    '{"event":"closed"}',
    '{"event":"launched","run":"1","session":"s","at":"2026-10-13T17:42:05Z"}',
    '{"event":"launched","run":1,"session":"s"}',
    '{"event":"launched","run":1,"session":"s","at":"yesterday"}',
    '{"event":"origin","at":"2026-10-13T17:42:05Z"}',
    '{"event":"origin","address":"main"}',
    '{"event":"origin","address":"main","at":"yesterday"}',
    '{"event":"reported","at":"2026-10-13T17:42:05Z"}',
    '{"event":"reported","run":1}',
    '{"event":"reported","run":"1","at":"2026-10-13T17:42:05Z"}',
    '{"event":"draft-started","n":1,"session":"s","mode":"edit","at":"2026-10-13T17:42:05Z"}',
    '{"event":"draft-ended","n":1,"open":true,"summary":[],"at":"2026-10-13T17:42:05Z"}',
    '{"event":"draft-ended","n":1,"open":0,"summary":"a","at":"2026-10-13T17:42:05Z"}',
])
def test_decode_rejects_bad_lines_with_value_error(line):
    with pytest.raises(ValueError):
        decode(line)
