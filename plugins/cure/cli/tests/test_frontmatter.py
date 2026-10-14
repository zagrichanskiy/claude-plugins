"""Frontmatter subset: scalars, inline lists, block lists, continuation lines, and ``set_scalars``."""
from __future__ import annotations

import pytest

from cure_job.frontmatter import FrontmatterError, as_list, parse, set_scalars


def test_parse_reads_scalars():
    assert parse("---\ndevice: none\nname: x y\n---\nbody") == {"device": "none", "name": "x y"}


def test_parse_removes_one_pair_of_quotes():
    assert parse("---\na: 'x'\n---\n")["a"] == "x"
    assert parse("---\nb: \"y\"\n---\n")["b"] == "y"
    assert parse("---\nc: ''z''\n---\n")["c"] == "'z'"


def test_parse_reads_inline_list():
    assert parse("---\nrepos: [/a, '/b' , \"/c\"]\n---\n")["repos"] == ["/a", "/b", "/c"]


def test_parse_reads_empty_inline_list():
    assert parse("---\nrepos: []\n---\n")["repos"] == []


def test_parse_reads_block_list_indented_or_not():
    assert parse("---\nrepos:\n  - /a\n  - /b\n---\n")["repos"] == ["/a", "/b"]
    assert parse("---\nrepos:\n- /a\n- /b\n---\n")["repos"] == ["/a", "/b"]


def test_parse_key_without_items_is_empty_string():
    assert parse("---\nrepos:\ndevice: none\n---\n") == {"repos": "", "device": "none"}


def test_parse_joins_continuation_lines_with_one_space():
    assert parse("---\nsummary: first\n  second\n  third\n---\n")["summary"] == "first second third"


def test_parse_skips_blank_and_comment_lines():
    assert parse("---\n\n# comment\n  # indented comment\na: 1\n---\n") == {"a": "1"}


def test_parse_ignores_text_after_the_block():
    assert parse("---\na: 1\n---\nb: 2\n") == {"a": "1"}


@pytest.mark.parametrize("text", ["", "a: 1\n", "\n---\na: 1\n---\n", "---\na: 1\n"])
def test_parse_without_a_complete_block_raises(text):
    with pytest.raises(FrontmatterError):
        parse(text)


def test_parse_rejects_unparseable_column_zero_line_naming_the_line_number():
    with pytest.raises(FrontmatterError, match="3"):
        parse("---\na: 1\nnot a pair\n---\n")


def test_frontmatter_error_is_a_value_error():
    assert issubclass(FrontmatterError, ValueError)


def test_as_list_maps_none_and_empty_string_to_empty_list():
    assert as_list(None) == []
    assert as_list("") == []


def test_as_list_wraps_a_string():
    assert as_list("x") == ["x"]


def test_as_list_keeps_a_list():
    assert as_list(["a", "b"]) == ["a", "b"]


def test_set_scalars_inserts_new_keys_under_the_opening_marker():
    text = "---\ndevice: none\n---\nbody\n"
    assert set_scalars(text, {"id": "x"}) == "---\nid: x\ndevice: none\n---\nbody\n"


def test_set_scalars_replaces_an_existing_entry_with_its_continuation_lines():
    text = "---\nid: old\n  continued\ndevice: none\n---\n"
    result = set_scalars(text, {"id": "new"})
    assert parse(result) == {"id": "new", "device": "none"}
    assert "old" not in result and "continued" not in result


def test_set_scalars_replaces_an_existing_list_entry():
    text = "---\ncreated:\n  - a\n  - b\nrepos: [/a]\n---\n"
    result = set_scalars(text, {"created": "2026"})
    assert parse(result) == {"created": "2026", "repos": ["/a"]}


def test_set_scalars_leaves_other_lines_unchanged():
    text = "---\n# keep me\nrepos: [/a]\n---\n\n# Body\ntext\n"
    result = set_scalars(text, {"id": "x"})
    assert "# keep me\nrepos: [/a]\n---\n\n# Body\ntext\n" in result
