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
