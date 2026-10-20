"""``scripts/lint-plugin.py``: the ``autoCompactWindow`` range and sync-block checks, imported by path."""
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


def sync_problems(lint, tmp_path, agent_text):
    lint.ROOT = tmp_path
    (tmp_path / "source.md").write_text("Source text.\n")
    agent = tmp_path / "agent.md"
    agent.write_text(agent_text)
    lint.check_sync_blocks(tmp_path, agent)
    return lint.problems


def test_sync_accepts_a_block_equal_to_its_source(lint, tmp_path):
    assert sync_problems(lint, tmp_path, "<!-- sync: source.md -->\nSource text.\n<!-- /sync -->\n") == []


@pytest.mark.parametrize("text, expected", [
    ("<!-- sync: source.md-->\nSource text.\n<!-- /sync -->\n", "does not open a well-formed block"),
    ("<!-- sync: source.md -->\nSource text.\n", "does not open a well-formed block"),
    ("<!-- sync: source.md -->\n<!-- /sync -->\n", "sync block is empty"),
], ids=["no-space-before-close", "missing-closing-marker", "empty-block"])
def test_sync_rejects_a_malformed_block(lint, tmp_path, text, expected):
    found = sync_problems(lint, tmp_path, text)
    assert any(expected in problem for problem in found), found


def test_sync_rejects_a_missing_closing_marker_between_two_blocks(lint, tmp_path):
    text = ("<!-- sync: source.md -->\nSource text.\n"
            "<!-- sync: source.md -->\nSource text.\n<!-- /sync -->\n")
    found = sync_problems(lint, tmp_path, text)
    assert any("does not open a well-formed block" in problem for problem in found), found


def test_sync_rejects_a_stray_closing_marker(lint, tmp_path):
    text = "<!-- sync: source.md -->\nSource text.\n<!-- /sync -->\n<!-- /sync -->\n"
    found = sync_problems(lint, tmp_path, text)
    assert any("2 closing sync marker(s) for 1" in problem for problem in found), found
