"""``parse_handoff`` validates only ``repos`` and ``device``; ``stamp`` writes ``id`` and ``created``."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from cure_job.errors import CureJobError, HandoffError
from cure_job.frontmatter import parse
from cure_job.handoff import Device, parse_handoff, stamp


def test_parses_repos_and_device():
    handoff = parse_handoff("---\nrepos:\n  - /work/a\n  - /work/b\ndevice: bench\n---\n")
    assert handoff.repos == ("/work/a", "/work/b")
    assert handoff.device is Device.BENCH


def test_launch_dir_is_the_first_repo():
    assert parse_handoff("---\nrepos: [/work/a, /work/b]\ndevice: none\n---\n").launch_dir == "/work/a"


def test_resources_hold_only_repos_when_device_is_bench():
    handoff = parse_handoff("---\nrepos: [/work/a]\ndevice: bench\n---\n")
    assert handoff.device is Device.BENCH
    assert handoff.resources == frozenset({"/work/a"})


def test_resources_have_no_bench_when_device_is_none():
    assert parse_handoff("---\nrepos: [/work/a]\ndevice: none\n---\n").resources == frozenset({"/work/a"})


def test_repos_are_normalised_and_deduplicated_keeping_order():
    handoff = parse_handoff("---\nrepos: [/work/b, /work/a/../a, /work/b/, /work/a]\ndevice: none\n---\n")
    assert handoff.repos == ("/work/b", "/work/a")


def test_single_scalar_repo_is_accepted():
    assert parse_handoff("---\nrepos: /work/a\ndevice: none\n---\n").repos == ("/work/a",)


def test_other_fields_and_sections_are_not_checked():
    parse_handoff("---\nrepos: [/a]\ndevice: none\nanything: goes\n---\n# Whatever\n")


@pytest.mark.parametrize("text", [
    "no frontmatter",
    "---\ndevice: none\n---\n",
    "---\nrepos: []\ndevice: none\n---\n",
    "---\nrepos:\ndevice: none\n---\n",
    "---\nrepos: [relative/path]\ndevice: none\n---\n",
    "---\nrepos: [/a]\n---\n",
    "---\nrepos: [/a]\ndevice: robot\n---\n",
    "---\nrepos: [/a]\ndevice: Bench\n---\n",
    "---\nrepos: [/a]\ndevice: none\n",
])
def test_invalid_handoff_raises_handoff_error(text):
    with pytest.raises(HandoffError):
        parse_handoff(text)


def test_handoff_error_is_a_cure_job_error():
    assert issubclass(HandoffError, CureJobError)


def test_stamp_sets_id_and_created_and_replaces_existing_values():
    created = datetime(2026, 10, 13, 17, 42, 5, tzinfo=timezone.utc)
    text = "---\nid: stale\ncreated: stale\nrepos: [/a]\ndevice: none\n---\nbody\n"
    stamped = stamp(text, "261013-1742-a-x", created)
    fields = parse(stamped)
    assert fields["id"] == "261013-1742-a-x"
    assert fields["created"] == "2026-10-13T17:42:05+00:00"
    assert fields["repos"] == ["/a"]
    assert stamped.endswith("---\nbody\n")


def test_origin_given_as_a_list_is_refused():
    with pytest.raises(HandoffError, match="origin is a list; expected one session name"):
        parse_handoff("---\nrepos: [/work/a]\ndevice: none\norigin:\n  - one\n  - two\n---\n")


def test_origin_given_as_a_flow_list_is_refused():
    with pytest.raises(HandoffError, match="origin is a list"):
        parse_handoff("---\nrepos: [/work/a]\ndevice: none\norigin: [one, two]\n---\n")


def test_origin_scalar_is_kept_and_absent_origin_is_none():
    assert parse_handoff("---\nrepos: [/work/a]\ndevice: none\norigin: main-session\n---\n").origin == "main-session"
    assert parse_handoff("---\nrepos: [/work/a]\ndevice: none\n---\n").origin is None
