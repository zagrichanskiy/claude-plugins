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

An *unknown* key is ignored just as quietly, so a typo costs the setting rather than the load:
`efort: high` is not a failure, it is an agent at default effort. `scripts/lint-plugin.py` is the
gate — it checks that every agent carries `name:` (matching the file name), `tools:` and
`description:`, that every skill carries `description:` and uses `allowed-tools:`, that no key is
unknown, and that `model:` and `effort:` hold accepted values:

| Key | Accepted values |
|---|---|
| `model` | `opus`, `sonnet`, `haiku`, `fable`, `inherit` |
| `effort` | `low`, `medium`, `high`, `xhigh`, `max` |

Run it before every commit; CI runs it on every pull request and every push to `main`. `claude plugin validate .`
checks the manifests only — it says nothing about agent or skill frontmatter, which is why the lint
exists.

`memory: user` sits on `architect`, `designer` and `security-expert`. The key is accepted by the
CLI; its exact effect on a plugin agent has not been verified here, so it was left where it was
rather than propagated to the other agents.

## Collection is separated from judgement on purpose

Two advisory agents (`architect` and `designer`) reviewing one pull request group independently
consumed 4.4 M weighted input tokens across 249 requests, and six findings were reached twice. The
cause was not the agents; it was that each ran its own collection pass over the same source.

`collector` plus `/cure:review-change` exist to fix that, and three properties are load-bearing:

- **The collector never judges.** A digest that contains a severity or a recommendation becomes the
  finding, and the reviewer that cites it inherits a judgement made by the cheap model.
- **The digest is a map, never evidence.** Every finding cites the source file. A digest may be
  wrong; a review built on one that was never checked is worth nothing.
- **Areas are deliberately not divided between reviewers.** Each agent chooses what to open. An
  assigned-area split would cost less again and would miss exactly the defects that cross a
  boundary, which are the ones worth the review.

The reading footer each agent ends with (`Read: N files in full, M sampled; digest: used | absent.`)
is the only measurement of whether this keeps working. Do not remove it from `core.md` or the agent
files.

## Advisor and reviewer knowledge is loaded by mode and by language, never all

`designer` and `architect` each read `core.md`, their mode's checklist and pattern catalogue, and
only their mode's supplement under `knowledge/design-advisor/lang/` for each language the target is
written in. Nothing language-specific belongs in the shared checklists or pattern catalogues: a C++
review should not carry Python advice in its context on every request, nor the other way round.
`reviewer` follows the same rule with `knowledge/reviewer/lang/<language>.md`. To add a language,
add `lang/<language>-design.md` and `lang/<language>-architecture.md` under `design-advisor/`,
`lang/<language>.md` under `reviewer/`, and a row to the extension tables in `core.md` and
`agents/reviewer.md`.

## Design review output has a required structure, and merges keep it

A review of log-manager dispatched `designer` with a brief that asked for coroutine lifetimes and
bugs, ranked by severity. All four of its must-fix findings came back as behaviour bugs, and the
merged report, ranked globally, reduced its class-level findings to one-line bullets and dropped
the proposed interfaces. Three things now prevent that, and each is load-bearing:

- `core.md` ground rule 5: a bug is listed under *Out of altitude*, never ranked, even when the
  brief asks for bugs.
- The review skeletons in both checklists: the per-type or per-component assessment and the
  pattern assessment are required and come before the findings.
- `review-change` step 4: one section per altitude at full depth, and agreement between agents is
  never a rank boost.

## Independent agents drop findings between rounds

Round 3 of the log-manager review ran on the same commit as round 2. Three round-2 must-fixes came
back from no agent: a use-after-free on SIGTERM, a NAND board given the eMMC storage profile, and a
web endpoint that still read the journal the change had made volatile. The merging session found
all three still present. The reviewer had missed the use-after-free in both rounds, although the
C++ supplement named the pitfall. Each of these guards addresses one miss; keep them:

| Miss | Guard |
|---|---|
| Earlier must-fix not raised again | `review-change` step 4 carry-over table; the merger re-checks before dropping |
| Use-after-free after `co_await` | `reviewer.md` teardown walk; `reviewer/lang/cpp.md` owner-destroyed item |
| Per-machine profile wrong for the board | `checklist-architecture.md` §4, check each selection against the machine file |
| Consumer of the replaced mechanism left behind | `checklist-architecture.md` §2 replacement item; `collector.md` §4 consumer sweep |
| "Nothing else syncs" built on a grep for `fsync` only | `core.md` rule 12 and `reviewer.md`: an absence claim names its search |

The earlier findings are deliberately not given to the agents. That would be a topic brief, which
`review-change` step 3 forbids; the carry-over check belongs to the merge.

## Marketplace names resembling official ones are rejected

`claude plugin marketplace add` refuses a manifest whose `name` looks like an official
Anthropic/Claude marketplace. `claude-plugins` was rejected on that ground; the marketplace is
therefore named `zagrichanskiy` while the repository is `claude-plugins`. The two do not match by
design.

## Bundled files are addressed through `${CLAUDE_PLUGIN_ROOT}`

Agents and skills that read files shipped alongside them (the `design-advisor` checklists) must use
`${CLAUDE_PLUGIN_ROOT}`, never `~/.claude/...` or a path relative to the working directory. The
plugin's install location varies.

## These agents and skills live only here

They were moved out of `~/.claude/` on each machine, and the user-level copies deleted:

| Machine | Backup |
|---|---|
| macOS | `~/.claude/backups/pre-cure-plugin-20260903-222803/` |
| Linux | `~/.claude/backups/pre-cure-plugin-linux-20260903-231956/` |

There is no user-level copy to fall back on, so a broken commit here removes the agent everywhere.

The Linux machine carried an older, self-contained `designer.md` predating the split into
`knowledge/design-advisor/`. It was discarded, not merged — the split version supersedes it.
