"""Job id format: ``<yymmdd>-<hhmm>-<repo>-<slug>`` in UTC, 60 characters at most, ``-N`` on collision."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from cure_job import job_id

CREATED = datetime(2026, 10, 13, 17, 42, 5, tzinfo=timezone.utc)


def test_slugify_lowercases_and_collapses_runs_of_other_characters():
    assert job_id.slugify("FPS  Clamp__Fix!") == "fps-clamp-fix"


def test_slugify_strips_leading_and_trailing_separators():
    assert job_id.slugify("--Video Core--") == "video-core"


def test_slugify_may_return_empty():
    assert job_id.slugify("!!!") == ""


def test_make_id_has_documented_format():
    assert job_id.make_id(CREATED, "video-core", "fps clamp") == "261013-1742-video-core-fps-clamp"


def test_make_id_slugifies_repo_and_slug():
    assert job_id.make_id(CREATED, "Video_Core", "A/B") == "261013-1742-video-core-a-b"


@pytest.mark.parametrize("repo, slug", [("", "x"), ("x", ""), ("!!", "x"), ("x", "??")])
def test_make_id_rejects_empty_slug(repo, slug):
    with pytest.raises(ValueError):
        job_id.make_id(CREATED, repo, slug)


def test_make_id_is_cut_at_the_limit():
    result = job_id.make_id(CREATED, "repo", "a" * 100)
    assert len(result) == job_id.MAX_LENGTH == 60


def test_make_id_of_exactly_the_limit_is_untouched():
    prefix = "261013-1742-repo-"
    slug = "a" * (60 - len(prefix))
    assert job_id.make_id(CREATED, "repo", slug) == prefix + slug


def test_make_id_strips_a_trailing_dash_left_by_the_cut():
    prefix = "261013-1742-repo-"
    slug = "a" * (60 - len(prefix) - 1) + "-bbb"
    result = job_id.make_id(CREATED, "repo", slug)
    assert len(result) == 59
    assert not result.endswith("-")


def test_with_suffix_appends_the_number():
    assert job_id.with_suffix("261013-1742-repo-x", 2) == "261013-1742-repo-x-2"


def test_with_suffix_cuts_the_base_so_the_result_still_fits():
    base = job_id.make_id(CREATED, "repo", "a" * 100)
    result = job_id.with_suffix(base, 12)
    assert len(result) <= 60
    assert result.endswith("-12")
    assert job_id.is_valid(result)


def test_with_suffix_strips_a_dash_before_the_suffix():
    base = "261013-1742-repo-" + "a" * 39 + "-" + "b"
    result = job_id.with_suffix(base, 2)
    assert "--" not in result


def test_max_suffix_is_99():
    assert job_id.MAX_SUFFIX == 99


@pytest.mark.parametrize("text", ["261013-1742-repo-x", "261013-1742-a", "261013-1742-a-b-c-2"])
def test_is_valid_accepts_well_formed_ids(text):
    assert job_id.is_valid(text)


@pytest.mark.parametrize("text", [
    "", "261013-1742", "261013-1742-", "26101-1742-x", "261013-174-x", "261013-1742-X",
    "261013-1742-a_b", "261013-1742-a--b", "../261013-1742-x", "261013-1742-x/", "261013-1742-x\n",
    "x261013-1742-x",
])
def test_is_valid_rejects_malformed_ids(text):
    assert not job_id.is_valid(text)


def test_is_valid_enforces_the_length_limit():
    assert job_id.is_valid("261013-1742-" + "a" * 48)
    assert not job_id.is_valid("261013-1742-" + "a" * 49)


def test_session_name_of_first_run_is_the_id():
    assert job_id.session_name("261013-1742-repo-x", 1) == "261013-1742-repo-x"


def test_session_name_of_later_run_has_run_suffix():
    assert job_id.session_name("261013-1742-repo-x", 3) == "261013-1742-repo-x-r3"


@pytest.mark.parametrize("ticket, expected", [
    ("zagrichanskiy/claude-plugins#126", "issue-126-claude-plugins-report-pass"),
    ("#126", "issue-126-claude-plugins-report-pass"),
    ("ABC-123", "abc-123-claude-plugins-report-pass"),
    ("https://github.com/zagrichanskiy/claude-plugins/issues/126", "issue-126-claude-plugins-report-pass"),
])
def test_make_id_with_a_ticket_drops_the_time_prefix(ticket, expected):
    result = job_id.make_id(CREATED, "claude-plugins", "Report pass", ticket)
    assert result == expected
    assert job_id.is_valid(result)


@pytest.mark.parametrize("ticket", [None, "", "a login bug", "https://example.com/browse",
                                    "https://app.clickup.com/t/86abc123"])
def test_make_id_without_a_readable_ticket_keeps_the_time_prefix(ticket):
    assert job_id.make_id(CREATED, "repo", "x", ticket) == "261013-1742-repo-x"


def test_make_id_keeps_the_time_prefix_when_the_ticket_leaves_no_room():
    assert job_id.make_id(CREATED, "repo", "x", "ABC-" + "1" * 60) == "261013-1742-repo-x"


@pytest.mark.parametrize("text", ["issue-126-claude-plugins-report-pass", "abc-123-meta-x", "abc-123-meta-x-2"])
def test_is_valid_accepts_ticket_ids(text):
    assert job_id.is_valid(text)


@pytest.mark.parametrize("text", ["abc-123-meta", "abc-meta-x", "7abc-123-meta-x", "Abc-123-meta-x", "abc-123--x-y"])
def test_is_valid_rejects_malformed_ticket_ids(text):
    assert not job_id.is_valid(text)


def test_a_job_id_with_a_kept_ledger_is_taken(tmp_path):
    from cure_job.store import JobStore
    store = JobStore(tmp_path / "cure")
    base = job_id.make_id(CREATED, "repo", "x", "ABC-1")
    store.kept_ledger_path(base).parent.mkdir(parents=True)
    store.kept_ledger_path(base).write_text("{}\n", encoding="utf-8")
    assert store.create(base, lambda _: "---\nrepos: [/r]\ndevice: none\n---\n") == base + "-2"


@pytest.mark.parametrize("ticket, prefix", [(None, "261013-1742-"), ("ABC-1", "abc-1-")])
def test_make_id_cut_inside_a_long_repo_keeps_the_slug(ticket, prefix):
    result = job_id.make_id(CREATED, "meta-" * 12, "fix", ticket)
    assert result.startswith(prefix + "meta-meta") and result.endswith("-fix")
    assert len(result) <= 60 and job_id.is_valid(result)


def test_make_id_cut_of_a_long_repo_and_slug_keeps_half_the_room_for_the_slug():
    result = job_id.make_id(CREATED, "r" * 60, "s" * 60)
    assert result == "261013-1742-" + "r" * 24 + "-" + "s" * 23


def test_a_removed_job_id_stays_taken(tmp_path):
    from cure_job.store import JobStore
    store = JobStore(tmp_path / "cure")
    base = job_id.make_id(CREATED, "repo", "x", "ABC-1")
    store.create(base, lambda _: "---\nrepos: [/r]\ndevice: none\n---\n")
    store.remove(base)
    assert store.kept_ledger_path(base).read_text(encoding="utf-8") == ""
    assert store.create(base, lambda _: "---\nrepos: [/r]\ndevice: none\n---\n") == base + "-2"
