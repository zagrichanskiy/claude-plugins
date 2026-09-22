#!/usr/bin/env python3
"""Lint the marketplace, its plugins, their agents and their skills.

Claude Code skips an agent or a skill whose frontmatter is malformed, and it does so silently:
no error, no warning, the agent simply never appears. This script is the gate that turns that
silence into a failed check. It parses only top-level frontmatter keys, so it needs no YAML
library.
"""

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

MODELS = {"opus", "sonnet", "haiku", "fable", "inherit"}
EFFORTS = {"low", "medium", "high", "xhigh", "max"}

AGENT_KEYS = {
    "name", "description", "tools", "model", "effort", "color", "memory",
    "disable-model-invocation", "isolation",
}
SKILL_KEYS = {
    "name", "description", "allowed-tools", "model", "argument-hint", "arguments",
    "disable-model-invocation", "user-invocable", "version", "license", "metadata",
}

KEY = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*):(.*)$")

problems = []


def fail(path, message):
    problems.append(f"{path.relative_to(ROOT)}: {message}")


def frontmatter(path):
    """Return {key: value} of the top-level frontmatter keys, or None if there is none."""
    lines = path.read_text().split("\n")
    if not lines or lines[0].strip() != "---":
        return None
    try:
        end = lines.index("---", 1)
    except ValueError:
        return None
    keys = {}
    for line in lines[1:end]:
        if not line or line[0].isspace() or line.lstrip().startswith("#"):
            continue
        match = KEY.match(line)
        if match:
            keys[match.group(1)] = match.group(2).strip()
    return keys


def check_enum(path, keys, key, allowed):
    value = keys.get(key)
    if value is None:
        return
    value = value.strip("\"'")
    if value and value not in allowed:
        fail(path, f"{key}: {value!r} is not one of {sorted(allowed)}")


def check_trailing_newline(path):
    data = path.read_bytes()
    if data and not data.endswith(b"\n"):
        fail(path, "file does not end with a newline")


def check_agent(path):
    keys = frontmatter(path)
    if keys is None:
        fail(path, "no frontmatter block")
        return
    if "name" not in keys:
        fail(path, "missing name: — the agent is skipped at load with no error")
    elif keys["name"] != path.stem:
        fail(path, f"name: {keys['name']!r} does not match the file name {path.stem!r}")
    if "tools" not in keys:
        fail(path, "missing tools: — the agent is skipped at load with no error")
    if "allowed-tools" in keys:
        fail(path, "allowed-tools: is the skill key; an agent uses tools:")
    if "description" not in keys:
        fail(path, "missing description: — the agent is never dispatched automatically")
    for key in sorted(set(keys) - AGENT_KEYS):
        fail(path, f"unknown frontmatter key {key!r}; it is ignored silently")
    check_enum(path, keys, "model", MODELS)
    check_enum(path, keys, "effort", EFFORTS)


def check_skill(path):
    keys = frontmatter(path)
    if keys is None:
        fail(path, "no frontmatter block")
        return
    if "description" not in keys:
        fail(path, "missing description: — the skill is never invoked automatically")
    if "tools" in keys:
        fail(path, "tools: is the agent key; a skill uses allowed-tools:")
    name = keys.get("name")
    if name and name != path.parent.name:
        fail(path, f"name: {name!r} does not match the directory {path.parent.name!r}")
    for key in sorted(set(keys) - SKILL_KEYS):
        fail(path, f"unknown frontmatter key {key!r}; it is ignored silently")
    check_enum(path, keys, "model", MODELS)


def bundled_dirs(plugin_root):
    """Directories a plugin ships beside its agents and skills, read at run time."""
    skip = {"agents", "skills", "commands", "hooks", ".claude-plugin"}
    return [d.name for d in plugin_root.iterdir() if d.is_dir() and d.name not in skip]


def check_bundled_paths(path, dirs):
    """A bundled file is addressed through ${CLAUDE_PLUGIN_ROOT}; the install location varies.

    A path under the user's home (`~/knowledge/`) is a different thing and is left alone.
    """
    patterns = [(name, re.compile(rf"(?<![~\w/.]){re.escape(name)}/")) for name in dirs]
    for number, line in enumerate(path.read_text().split("\n"), 1):
        if "~/.claude/plugins" in line:
            fail(path, f"line {number}: addresses the plugin cache directly; "
                       "use ${CLAUDE_PLUGIN_ROOT}")
        if "${CLAUDE_PLUGIN_ROOT}" in line:
            continue
        for name, pattern in patterns:
            if pattern.search(line):
                fail(path, f"line {number}: references the bundled {name}/ directory without "
                           "${CLAUDE_PLUGIN_ROOT}")


def main():
    manifest_path = ROOT / ".claude-plugin" / "marketplace.json"
    manifest = json.loads(manifest_path.read_text())
    for key in ("name", "owner", "plugins"):
        if key not in manifest:
            fail(manifest_path, f"missing {key!r}")

    for entry in manifest.get("plugins", []):
        source = ROOT / entry["source"]
        if not source.is_dir():
            fail(manifest_path, f"source {entry['source']!r} does not exist")
            continue
        plugin_json = source / ".claude-plugin" / "plugin.json"
        if not plugin_json.is_file():
            fail(source, "no .claude-plugin/plugin.json")
            continue
        plugin = json.loads(plugin_json.read_text())
        if plugin.get("name") != entry["name"]:
            fail(plugin_json, f"name {plugin.get('name')!r} does not match the marketplace "
                              f"entry {entry['name']!r}")
        if not plugin.get("version"):
            fail(plugin_json, "missing version: an edit without a bump keeps serving the old "
                              "cached copy")

    for path in sorted(ROOT.glob("plugins/*/agents/*.md")):
        check_agent(path)
    for path in sorted(ROOT.glob("plugins/*/skills/*/SKILL.md")):
        check_skill(path)
    for plugin_root in sorted(ROOT.glob("plugins/*")):
        if not plugin_root.is_dir():
            continue
        dirs = bundled_dirs(plugin_root)
        if not dirs:
            continue
        for path in sorted(plugin_root.rglob("*.md")):
            check_bundled_paths(path, dirs)
    for path in sorted(ROOT.rglob("*")):
        if path.is_file() and path.suffix in {".md", ".json", ".sh", ".py", ".yml"} \
                and ".git/" not in str(path):
            check_trailing_newline(path)

    if problems:
        print(f"{len(problems)} problem(s):\n")
        for problem in problems:
            print(f"  {problem}")
        return 1
    print("lint passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
