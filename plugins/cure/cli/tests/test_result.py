"""``parse_result`` never raises; a malformed ``result.md`` becomes ``needs-input`` with a ``problem``."""
from __future__ import annotations

import pytest

from cure_job.result import ResultStatus, parse_result


@pytest.mark.parametrize("text, status", [
    ("---\nstatus: done\n---\n", ResultStatus.DONE),
    ("---\nstatus: failed\n---\n", ResultStatus.FAILED),
    ("---\nstatus: needs-input\n---\n", ResultStatus.NEEDS_INPUT),
])
def test_known_status_is_read_without_problem(text, status):
    result = parse_result(text)
    assert result.status is status
    assert result.problem is None
    assert result.unproven == ()


def test_unproven_list_is_read():
    result = parse_result("---\nstatus: done\nunproven:\n  - flaky\n  - slow\n---\n")
    assert result.unproven == ("flaky", "slow")


def test_unproven_inline_list_is_read():
    assert parse_result("---\nstatus: done\nunproven: [a, b]\n---\n").unproven == ("a", "b")


def test_pr_list_is_read():
    result = parse_result("---\nstatus: done\npr:\n  - https://example.com/a/pull/1\n  - https://example.com/b/pull/2\n---\n")
    assert result.prs == ("https://example.com/a/pull/1", "https://example.com/b/pull/2")


def test_scalar_pr_is_read_as_one_element_list():
    assert parse_result("---\nstatus: done\npr: https://example.com/a/pull/1\n---\n").prs == (
        "https://example.com/a/pull/1",)


@pytest.mark.parametrize("text", [
    "",
    "just prose",
    "---\nunproven: []\n---\n",
    "---\nstatus: finished\n---\n",
    "---\nstatus: done\n",
    "---\nnot a pair\n---\n",
])
def test_malformed_result_is_needs_input_with_a_problem(text):
    result = parse_result(text)
    assert result.status is ResultStatus.NEEDS_INPUT
    assert result.unproven == ()
    assert result.problem
