"""``scripts/lint-plugin.py``: the ``autoCompactWindow`` range check. The script is imported by path."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "lint-plugin.py"


@pytest.fixture
def lint():
    spec = importlib.util.spec_from_file_location("lint_plugin_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def problems_for(lint, keys):
    lint.check_int_range(lint.ROOT / "agent.md", keys, "autoCompactWindow", lint.AUTO_COMPACT_WINDOW)
    return lint.problems


def test_bounds_are_one_hundred_thousand_to_one_million(lint):
    assert lint.AUTO_COMPACT_WINDOW == (100000, 1000000)


@pytest.mark.parametrize("value", ["100000", "200000", "1000000"])
def test_accepts_an_integer_inside_the_range(lint, value):
    assert problems_for(lint, {"autoCompactWindow": value}) == []


def test_accepts_an_absent_key(lint):
    assert problems_for(lint, {}) == []


@pytest.mark.parametrize("value", ["99999", "1000001", '"200000"', "'200000'", "2e5", "", "-100000", "200000.0",
                                   "200 000", "abc"])
def test_rejects_a_value_outside_the_range_or_not_a_bare_integer(lint, value):
    found = problems_for(lint, {"autoCompactWindow": value})
    assert len(found) == 1
    assert "autoCompactWindow" in found[0]
    assert "from 100000 to 1000000" in found[0]
