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

*Collection* — runs before the agents that judge, so that they do not each read the same tree.

| Agent | Description |
|---|---|
| `collector` | Reads a change once and writes a source digest: inventory, public interfaces, wiring, configuration keys, documentation claims, tests, and a shortlist of files worth reading verbatim. Extracts only; it never judges and writes no file but the digest. |

*Advisors and reviewers* — they read, judge and write documents; none of them edits code.

| Agent | Description |
|---|---|
| `architect` | System-level architecture advice, review and documents for networked embedded systems: component boundaries, resource budgets, staging, risk, and the use or misuse of architectural patterns. Advises and writes documents; never edits implementation code. |
| `designer` | The same three modes at module/class/interface level: class decomposition, interface contracts and completeness, and the use or misuse of design patterns. Loads a C++ or Python supplement only for the target's language. |
| `security-expert` | Security architecture and protocol review for networked embedded systems: trust boundaries, authenticated key exchange, replay protection, key lifecycle for field-deployed devices. |
| `ui-reviewer` | Visual-design review of web UI: typography, spacing, colour, contrast, hierarchy, density, responsive behaviour. Reviews; never edits. |
| `ux-reviewer` | Interaction and accessibility review: task flow, discoverability, feedback, error and empty states, keyboard and screen-reader support. Reviews; never edits. |
| `knowledge-librarian` | Maintains a personal `~/knowledge` note library — one concept per file, wikilinked — and delivers changes as a pull request. |

`architect` and `designer` share `plugins/cure/knowledge/design-advisor/`. Each reads `core.md`,
its own mode's checklist and pattern catalogue, and — once the target is known — only its own
mode's supplement for each language the target is written in:

| File | `designer` | `architect` |
|---|---|---|
| `core.md` | always | always |
| `checklist-design.md`, `patterns-design.md` | always | never |
| `checklist-architecture.md`, `patterns-architecture.md` | never | always |
| `lang/cpp-design.md`, `lang/python-design.md` | per target language | never |
| `lang/cpp-architecture.md`, `lang/python-architecture.md` | never | per target language |

`reviewer` loads the pitfall supplements in `plugins/cure/knowledge/reviewer/lang/` (`cpp.md`,
`python.md`) the same way: only for the languages the change is written in.

*Implementation loop* — dispatched in sequence around a change. Each is project-agnostic and learns
the project's conventions, test command and run command from the repo.

| Agent | Description |
|---|---|
| `implementer` | Writes and edits production code for one work item and saves it to disk. Learns the project's language, layout and conventions from the repo, and implements what the item states and nothing beside it. Does not commit. |
| `test-author` | Writes unit tests for a change, module, or coverage gap and saves them to disk. Matches the project's existing test conventions rather than imposing a framework. Does not commit. |
| `qa` | Runs the test suite, or a named subset, and reports pass/fail with failure detail. It reports only; it never fixes what it finds. |
| `reviewer` | Reviews the working diff, or named files, for correctness bugs and design problems, and reports ranked findings with a concrete failing scenario for each. Loads a C++ or Python pitfall supplement only for the change's language. Writes only the report file the caller names; never edits code. |
| `verifier` | Drives the change end-to-end in the real application to confirm the behaviour works, rather than that the suite passes. Never edits. |
| `skill-author` | Creates and updates Claude Code skills from a description or source material, including the skills in this repository. |

**Skills** — invoked as `/cure:<name>`.

| Skill | Invocation | Description |
|---|---|---|
| `goal` | `/cure:goal` | Writes the brief that `/goal @<file>` runs from: asks every open question in one round first, then an orchestrator-led work list with an agent per step and a closing retrospective, a review-then-fix split with a severity floor, designer and live-verification gates, a measurable done-when list and the standing rules, under 4000 characters. |
| `capture-idea` | `/cure:capture-idea` | Captures an idea or design just discussed in a session as a structured goal file under `~/.claude/ideas/`, in a form a fresh session can pick up cold. |
| `note` | `/cure:note` | Gives working notes one home per repository, frontmatter that states their own end, and a sweep that deletes the ones a merged PR or committed document has superseded. |
| `explain` | `/cure:explain` | Explains a technology, design or codebase as a stepwise conversation rather than one dense answer. Builds a tree from the user's questions and answers one node per message. |
| `review-change` | `/cure:review-change` | Runs a multi-agent review as a pipeline: the collector once, then the reviewing agents in parallel against its digest, then one merged report triaged into MUST-FIX, SHOULD-CONSIDER, NITPICK and `enhancement`. A round passes when no MUST-FIX or SHOULD-CONSIDER is open. A re-check mode skips the collector on a small diff. |

## Reviewing a change

Two advisory agents reviewing one pull request group independently cost 4.4 M weighted input tokens
across 249 requests, and six of their findings were the same finding reached twice. The cost was
structural: each ran its own collection pass over the same source before judging anything.

`/cure:review-change` separates the two. `collector` reads the target once and writes a digest;
the reviewing agents read the digest first and then choose, each for itself, which files to open.
No agent is assigned an area and none is forbidden a file — dividing the source would trade a cost
problem for a coverage problem, and the defects worth finding are the ones that cross an area.
Every agent ends its reply with a reading footer, so the cost of the next review is visible rather
than inferred.

## Models and effort

Every agent states its own `model` and `effort`, by role:

| Role | Agents | Model | Effort |
|---|---|---|---|
| Judgement | `architect`, `designer`, `security-expert`, `reviewer`, `ui-reviewer`, `ux-reviewer` | `opus` | `high` |
| Production | `implementer` | `opus` | `medium` |
| Production | `test-author`, `skill-author`, `knowledge-librarian` | `sonnet` | `medium` |
| Mechanical | `collector`, `verifier` | `sonnet` | `medium` |
| Mechanical | `qa` | `sonnet` | `low` |

## Adding a plugin

1. Create `plugins/<name>/.claude-plugin/plugin.json` with at least a `name`.
2. Add an entry to `plugins` in `.claude-plugin/marketplace.json` with `source: "./plugins/<name>"`.
3. Run `claude plugin validate .`

## Adding an agent or skill

1. Agents: one `.md` file in `plugins/<plugin>/agents/`. Skills: `plugins/<plugin>/skills/<name>/SKILL.md`.
   Both are auto-discovered; no manifest entry is needed.
2. Bump `version` in that plugin's `plugin.json` — **required**, see [CLAUDE.md](CLAUDE.md).
3. Run `python3 scripts/lint-plugin.py`, then `claude plugin validate .`

## Structure

```
.claude-plugin/marketplace.json   marketplace manifest (name, owner, plugin list)
scripts/lint-plugin.py            frontmatter and manifest lint, run in CI
.github/workflows/validate.yml    runs the lint on every push and pull request
plugins/<name>/
  .claude-plugin/plugin.json      plugin manifest (name, version, metadata)
  agents/<name>.md                one file per agent, auto-discovered
  skills/<name>/SKILL.md          one directory per skill, auto-discovered
  knowledge/                      reference material the agents read at run time
    design-advisor/lang/          per-language supplements, loaded only for the target's language
    reviewer/lang/                per-language pitfall supplements for the reviewer
```
