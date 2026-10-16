"""Reader and writer for the frontmatter subset that ``handoff.md`` and ``result.md`` use.

The standard library has no YAML parser. The subset is: scalars, inline lists
(``key: [a, b]``), block lists (``- item`` lines) and indented continuation
lines of a scalar.
"""
from __future__ import annotations

import re
from typing import Mapping, Union

Value = Union[str, list[str]]

_FENCE = "---"
_KEY = re.compile(r"([A-Za-z][A-Za-z0-9_-]*):(?:[ \t]+(.*))?")
_QUOTES = ("'", '"')
# A value the writer leaves unquoted: no quote, bracket, "#", whitespace or comma.
# A leading "/" keeps absolute paths bare.
_BARE = re.compile(r"[A-Za-z0-9/][A-Za-z0-9._/@:+-]*")

# What the lines after a key may add to its value.
_NO_KEY, _EMPTY, _SCALAR, _ITEMS, _INLINE = range(5)


class FrontmatterError(ValueError):
    """The text has no frontmatter block, or a line in it is outside the subset."""


def parse(text: str) -> dict[str, Value]:
    lines = text.splitlines()
    end = _closing_fence(lines)
    entries: dict[str, Value] = {}
    key = ""
    mode = _NO_KEY
    for number, line in enumerate(lines[1:end], start=2):
        bare = line.strip()
        if _is_skipped(bare):
            continue
        indented = line[0] in " \t"
        if _is_item(bare) and mode in (_EMPTY, _ITEMS):
            if mode == _EMPTY:
                entries[key] = []
                mode = _ITEMS
            entries[key].append(_unquote(bare[1:].strip()))
        elif indented and mode == _SCALAR:
            entries[key] = f"{entries[key]} {bare}"
        elif indented and mode == _EMPTY:
            entries[key] = bare
            mode = _SCALAR
        else:
            match = None if indented else _KEY.fullmatch(line.rstrip())
            if match is None:
                raise FrontmatterError(f"line {number}: not a frontmatter entry: {bare}")
            key = match.group(1)
            entries[key], mode = _value((match.group(2) or "").strip())
    return entries


def as_list(value: Value | None) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, str):
        return [value]
    return list(value)


def set_scalars(text: str, values: Mapping[str, str]) -> str:
    """Return ``text`` with each key set to ``key: value``, directly under the opening fence.

    An existing entry for a key is removed with its continuation lines. Every
    other line is returned unchanged.
    """
    lines = text.splitlines(keepends=True)
    end = _closing_fence(lines)
    newline = lines[0][len(lines[0].rstrip("\r\n")):]
    kept = []
    dropping = False
    for line in lines[1:end]:
        bare = line.strip()
        if _is_skipped(bare):
            kept.append(line)
            continue
        if line[0] not in " \t" and not _is_item(bare):
            match = _KEY.fullmatch(line.rstrip())
            dropping = match is not None and match.group(1) in values
        if not dropping:
            kept.append(line)
    stamped = [f"{key}: {value}{newline}" for key, value in values.items()]
    return "".join([lines[0], *stamped, *kept, *lines[end:]])


def is_writable(text: str) -> bool:
    """True when ``render`` can write ``text`` so that ``parse`` reads it back unchanged."""
    # splitlines, not "\n" alone: parse splits on every separator it knows.
    return bool(text) and text == text.strip() and text.splitlines() == [text]


def render(entries: Mapping[str, Value]) -> str:
    """A frontmatter block holding ``entries``. ``parse(render(entries)) == entries``."""
    lines = [_FENCE]
    for key, value in entries.items():
        if not _KEY.fullmatch(f"{key}:"):
            raise FrontmatterError(f"invalid key {key!r}")
        if isinstance(value, str):
            lines.append(f"{key}: {_render_value(key, value)}")
        elif not value:
            lines.append(f"{key}: []")
        else:
            # Block lists, never inline: "," would split an inline item.
            lines.append(f"{key}:")
            lines.extend(f"  - {_render_value(key, item)}" for item in value)
    lines.append(_FENCE)
    return "\n".join(lines) + "\n"


def _render_value(key: str, text: str) -> str:
    if not is_writable(text):
        raise FrontmatterError(f"{key}: {text!r} is empty, padded or more than one line")
    # parse removes exactly one pair of surrounding quotes, and adds no escapes.
    return text if _BARE.fullmatch(text) else f'"{text}"'


def _closing_fence(lines: list[str]) -> int:
    """Index of the line that ends the block."""
    if not lines or lines[0].rstrip() != _FENCE:
        raise FrontmatterError(f"line 1 is not {_FENCE}")
    for index in range(1, len(lines)):
        if lines[index].rstrip() == _FENCE:
            return index
    raise FrontmatterError(f"the frontmatter block has no closing {_FENCE}")


def _is_skipped(bare: str) -> bool:
    return not bare or bare.startswith("#")


def _is_item(bare: str) -> bool:
    return bare == "-" or bare.startswith("- ")


def _value(text: str) -> tuple[Value, int]:
    if not text:
        return "", _EMPTY
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        return ([_unquote(item.strip()) for item in inner.split(",")] if inner else []), _INLINE
    return _unquote(text), _SCALAR


def _unquote(text: str) -> str:
    if len(text) >= 2 and text[0] == text[-1] and text[0] in _QUOTES:
        return text[1:-1]
    return text
