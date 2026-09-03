# CLAUDE.md

See [README.md](README.md) for what this repository contains and how to install it. This file
records only what reading the files will not tell you.

## Editing a plugin has no effect until its version is bumped

Installed plugins are cached at `~/.claude/plugins/cache/<marketplace>/<plugin>/<version>/`, keyed
by the `version` in `plugin.json` — not by file mtime. Editing anything under `plugins/<name>/`
leaves the installed copy serving the old snapshot.

After any content change: bump `version`, then

```sh
claude plugin marketplace update zagrichanskiy
claude plugin update cure@zagrichanskiy
```

and restart Claude Code.

## An agent with the wrong frontmatter keys fails silently

An agent file needs `name:` and `tools:`. Omit `name:`, or write `allowed-tools:` (the *skill* key)
instead of `tools:`, and the agent is skipped at load with no error — it simply never appears in the
agent list. Three agents in `cure` were broken this way before being moved here.

## Marketplace names resembling official ones are rejected

`claude plugin marketplace add` refuses a manifest whose `name` looks like an official
Anthropic/Claude marketplace. `claude-plugins` was rejected on that ground; the marketplace is
therefore named `zagrichanskiy` while the repository is `claude-plugins`. The two do not match by
design.

## Bundled files are addressed through `${CLAUDE_PLUGIN_ROOT}`

Agents and skills that read files shipped alongside them (the `design-advisor` checklists) must use
`${CLAUDE_PLUGIN_ROOT}`, never `~/.claude/...` or a path relative to the working directory. The
plugin's install location varies.

## `skills/stop-slop` is vendored, not ours

Do not edit it in place — changes are lost on the next re-vendor and drift from upstream silently.
Fix things upstream, or re-copy per [`VENDORED.md`](plugins/cure/skills/stop-slop/VENDORED.md).

## These agents and skills live only here

They were moved out of `~/.claude/` on each machine, and the user-level copies deleted:

| Machine | Backup |
|---|---|
| macOS | `~/.claude/backups/pre-cure-plugin-20260903-222803/` |
| Linux | `~/.claude/backups/pre-cure-plugin-linux-20260903-231956/` |

There is no user-level copy to fall back on, so a broken commit here removes the agent everywhere.

The Linux machine carried an older, self-contained `designer.md` predating the split into
`knowledge/design-advisor/`. It was discarded, not merged — the split version supersedes it.
