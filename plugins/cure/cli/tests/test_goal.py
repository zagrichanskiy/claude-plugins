"""``goal.tier``: the tier named in the Rules section of a goal file."""
from __future__ import annotations

import pytest

from cure_job.goal import tier


def goal(*rules: str, before: str = "") -> str:
    return f"# Goal\n\n{before}## Rules\n\n" + "\n".join(rules) + "\n\n## Done when\n\n- x\n"


@pytest.mark.parametrize("line, expected", [
    ("- Tier: Light.", "Light"),
    ("Tier: Full", "Full"),
    ("- Tier: Solo", "Solo"),
])
def test_tier_reads_the_word_with_or_without_a_dash(line, expected):
    assert tier(goal(line)) == expected


def test_tier_ignores_a_line_outside_the_rules_section():
    text = "# Goal\n\nTier: Full\n\n## Rules\n\n- other\n\n## Done when\n\n- Tier: Light\n"
    assert tier(text) is None


def test_tier_is_none_without_a_rules_section():
    assert tier("# Goal\n\n- Tier: Full\n") is None


def test_tier_is_none_for_an_unknown_word():
    assert tier(goal("- Tier: Huge.")) is None


def test_tier_is_none_for_a_lowercase_word():
    assert tier(goal("- Tier: light")) is None


def test_tier_takes_the_first_tier_line():
    assert tier(goal("- Tier: Light.", "- Tier: Full.")) == "Light"


def test_tier_does_not_skip_an_unknown_first_line():
    assert tier(goal("- Tier: Huge.", "- Tier: Full.")) is None
