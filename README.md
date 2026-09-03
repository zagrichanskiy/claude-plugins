# claude-plugins

A personal [Claude Code](https://claude.com/claude-code) plugin marketplace.

## Install (user-wide)

In an interactive Claude Code session:

```
/plugin marketplace add git@github.com:zagrichanskiy/claude-plugins.git
/plugin install cure@zagrichanskiy
```

Or non-interactively:

```sh
claude plugin marketplace add git@github.com:zagrichanskiy/claude-plugins.git
claude plugin install cure@zagrichanskiy
```

Restart Claude Code afterwards — agents and skills load at startup.

## Update

```
/plugin marketplace update zagrichanskiy
/plugin update cure@zagrichanskiy
```

## Plugins

### `cure`

Design and architecture advisors, review agents, an implementation loop, and working-note
discipline.

**Agents** — invoked by name, or dispatched automatically when a request matches their description.

*Advisors and reviewers* — they read, judge and write documents; none of them edits code.

| Agent | Description |
|---|---|
| `architect` | System-level architecture advice, review and documents for networked embedded systems: component boundaries, resource budgets, staging, risk. Advises and writes documents; never edits implementation code. |
| `designer` | The same three modes at module/class/interface level: how a component is factored internally. Language-agnostic, with Python and asyncio awareness. |
| `security-expert` | Security architecture and protocol review for networked embedded systems: trust boundaries, authenticated key exchange, replay protection, key lifecycle for field-deployed devices. |
| `doc-reviewer` | Reviews how a technical document reads — misplaced content, prose where a table belongs, design-discussion residue, padding, duplication. Judges readability, not technical correctness. |
| `ui-reviewer` | Visual-design review of web UI: typography, spacing, colour, contrast, hierarchy, density, responsive behaviour. Reviews; never edits. |
| `ux-reviewer` | Interaction and accessibility review: task flow, discoverability, feedback, error and empty states, keyboard and screen-reader support. Reviews; never edits. |
| `knowledge-librarian` | Maintains a personal `~/knowledge` note library — one concept per file, wikilinked — and delivers changes as a pull request. |

`architect` and `designer` share the checklists in `plugins/cure/knowledge/design-advisor/`; each
reads `core.md` plus the one checklist for its own mode.

*Implementation loop* — dispatched in sequence around a change. Each is project-agnostic and learns
the project's conventions, test command and run command from the repo.

| Agent | Description |
|---|---|
| `test-author` | Writes unit tests for a change, module, or coverage gap and saves them to disk. Matches the project's existing test conventions rather than imposing a framework. Does not commit. |
| `qa` | Runs the test suite, or a named subset, and reports pass/fail with failure detail. The quality gate: it never fixes what it finds. |
| `reviewer` | Reviews the working diff, or named files, for correctness bugs and design problems, and reports ranked findings with a concrete failing scenario for each. Never edits. |
| `verifier` | Drives the change end-to-end in the real application to confirm the behaviour works, rather than that the suite passes. Never edits. |
| `docs-sync` | Updates the documentation a change made stale — API docs, READMEs, convention files — and writes it to disk. Does not commit. |
| `skill-author` | Creates and updates Claude Code skills from a description or source material, including the skills in this repository. |

**Skills** — invoked as `/cure:<name>`.

| Skill | Invocation | Description |
|---|---|---|
| `capture-idea` | `/cure:capture-idea` | Captures an idea or design just discussed in a session as a structured goal file under `~/.claude/ideas/`, in a form a fresh session can pick up cold. |
| `note` | `/cure:note` | Gives working notes one home per repository, frontmatter that states their own end, and a sweep that deletes the ones a merged PR or committed document has superseded. |
| `explain` | `/cure:explain` | Explains a technology, design or codebase as a stepwise conversation rather than one dense answer. Builds a tree from the user's questions and answers one node per message. |
| `stop-slop` | `/cure:stop-slop` | Removes AI writing patterns from prose. Vendored from [hardikpandya/stop-slop](https://github.com/hardikpandya/stop-slop) (MIT) — see [`VENDORED.md`](plugins/cure/skills/stop-slop/VENDORED.md). |

## Adding a plugin

1. Create `plugins/<name>/.claude-plugin/plugin.json` with at least a `name`.
2. Add an entry to `plugins` in `.claude-plugin/marketplace.json` with `source: "./plugins/<name>"`.
3. Run `claude plugin validate .`

## Adding an agent or skill

1. Agents: one `.md` file in `plugins/<plugin>/agents/`. Skills: `plugins/<plugin>/skills/<name>/SKILL.md`.
   Both are auto-discovered; no manifest entry is needed.
2. Bump `version` in that plugin's `plugin.json` — **required**, see [CLAUDE.md](CLAUDE.md).
3. Run `claude plugin validate .`

## Structure

```
.claude-plugin/marketplace.json   marketplace manifest (name, owner, plugin list)
plugins/<name>/
  .claude-plugin/plugin.json      plugin manifest (name, version, metadata)
  agents/<name>.md                one file per agent, auto-discovered
  skills/<name>/SKILL.md          one directory per skill, auto-discovered
  knowledge/                      reference material the agents read at run time
```
