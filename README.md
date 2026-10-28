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

*C++ Core Guidelines* — each checks a C++ change against its own sections of the
[C++ Core Guidelines](https://github.com/isocpp/CppCoreGuidelines) and reports findings, each a
`defect` or a `deviation`, and a coverage table with one row per rule. They do not rank: the merge
ranks defects as bugs, and `designer` decides each deviation. All seven follow
`plugins/cure/knowledge/cpp-core-guidelines/procedure.md` and read only their own condensed section
files under `sections/`. None edits code.

A reviewed repository may list accepted deviations in `.claude/cure/cg-deviations.md`, one
`<rule id>: <scope> — <reason>` per line; the format is in `procedure.md`.

| Agent | Sections |
|---|---|
| `cg-interfaces` | I (Interfaces), F (Functions) |
| `cg-classes` | C (Classes and class hierarchies), Enum (Enumerations) |
| `cg-resources` | R (Resource management), E (Error handling) |
| `cg-statements` | ES (Expressions and statements), Con (Constants and immutability), CPL (C-style programming) |
| `cg-generic` | T (Templates and generic programming), SL (The Standard Library) |
| `cg-concurrency` | CP (Concurrency and parallelism) |
| `cg-philosophy` | P (Philosophy), Per (Performance), SF (Source files), A (Architectural ideas) |

*Implementation loop* — dispatched in sequence around a change. Each is project-agnostic and learns
the project's conventions, test command and run command from the repo.

| Agent | Description |
|---|---|
| `implementer` | Writes and edits production code for one work item and saves it to disk. Learns the project's language, layout and conventions from the repo, and implements what the item states and nothing beside it. Does not commit. |
| `test-author` | Writes unit tests for a change, module, or coverage gap and saves them to disk. Matches the project's existing test conventions rather than imposing a framework. Does not commit. |
| `qa` | Runs the test suite, or a named subset, and reports pass/fail with failure detail. It reports only; it never fixes what it finds. |
| `tracker` | Creates a ticket for split-off work, copies the original's fields and links, links the tickets and rewrites the original. Uses Jira MCP tools when it has them, else `split.jira-command`. Returns ids and manual steps. |
| `delivery` | Runs git for `cure:split`: builds and measures the part branches, bumps versions, checks trees, pushes and opens pull requests, through the repository's PR skill when it names one. Returns short reports. |
| `reviewer` | Reviews the working diff, or named files, for correctness bugs and design problems, and reports ranked findings with a concrete failing scenario for each. Loads a C++ or Python pitfall supplement only for the change's language. Writes only the report file the caller names; never edits code. |
| `verifier` | Drives the change end-to-end in the real application to confirm the behaviour works, rather than that the suite passes. Never edits. |
| `skill-author` | Creates and updates Claude Code skills from a description or source material, including the skills in this repository. |

*Dispatcher* — a long-lived background session that turns handoff files into running job sessions. `cure-job launch` starts a Light or Full job session with `--agent cure:orchestrator` and a Solo job session without `--agent`.

| Agent | Description |
|---|---|
| `dispatcher` | Scans the job queue (`cure-job prune`, then `cure-job next --json`: one element per job with its ordered actions) on start and on every wake-up message, runs `cure:goal` for each queued or held handoff, prints a 3-line summary, then runs `cure-job approve` (`--by auto` for a Solo or Light job with no `## Open` item and no failed prelaunch check (tools, permission rules); otherwise `--by user` after the user's answer) and `cure-job launch` for an `approved` job. `launch` refuses a run-1 job that is not `approved`. It alone asks a job's questions. Handles lost, stalled, blocked, invalid and needs-input jobs, and tells the origin session when a job finishes. Has `memory: user`, `model: inherit` and no `Agent` tool. |
| `orchestrator` | The session agent of a Light or Full job run. Its system prompt carries `skills/goal/rules.md` (the "All tiers" and "Light and Full" sections) and `skills/goal/short-holds.md` (the short-hold claim protocol), which context compaction does not drop. The exit protocol is in the job's goal file. `scripts/lint-plugin.py` fails when a copy differs from its file. Tools: `Read`, `Grep`, `Glob`, `Bash`, `Agent`, `Skill`, `SendMessage`; no `Edit` or `Write`, so it edits no code. It writes the ledger, backlog and retrospective with `Bash` heredocs. |

Start the dispatcher once per machine:

```sh
claude --bg --name dispatcher --agent cure:dispatcher --settings '{"crossSessionInbound":"accept","autoCompactWindow":200000,"permissions":{"allow":["Bash(cure-job *)"],"deny":["Bash(claude *)"]}}'
```

| Part | Reason |
|---|---|
| `--agent cure:dispatcher` | Claude Code 2.1.300 loads a plugin agent under its prefixed name. |
| `crossSessionInbound` | Without `accept`, the session ignores messages from other sessions. |
| `autoCompactWindow` | Compacts the main session at 200000 tokens. The key has no effect in the agent's frontmatter, so it is set here. |
| `permissions` | Allows `cure-job` by its bare name (the plugin's `bin/` is on PATH) and denies `claude`; `cure-job launch` starts the job session as a subprocess. The job does not edit `~/.claude/settings.json`. |
| `--name dispatcher` | Handoffs and job sessions address the dispatcher by this name. |
| `"env":{"CURE_JOB_ROOT":"<path>"}` | Passes a non-default state root. It goes inside the `--settings` JSON, because a background session does not inherit the caller's environment. |

| Requirement | Detail |
|---|---|
| Questions | Approval and other questions are answered in the dispatcher session (attach from `claude agents`). A message does not answer them. |
| Workspace trust | Each repository a job runs in must have been opened in Claude Code once to accept the trust prompt. Otherwise `cure-job launch` fails with "Workspace not trusted". |
| Configuration | See [plugins/cure/README.md](plugins/cure/README.md). |

Pin step: open `claude agents` and press ctrl+t on the dispatcher session. The session moves to the
top of the list. The dispatcher is also started automatically by `cure:dispatch` when its wake-up
message fails; the manual command above stays. A stopped dispatcher cannot receive messages, so run
`claude agents` after a reboot and start it again when it is not listed; its start scan finds
every job that finished while it was stopped.

**Skills** — invoked as `/cure:<name>`.

| Skill | Invocation | Description |
|---|---|---|
| `goal` | `/cure:goal` | Writes the brief that `/goal @<file>` runs from: asks every open question in one round first, then an orchestrator-led work list with an agent per step and a closing retrospective that writes evidence-backed change proposals to `~/.claude/retros/`, a review-then-fix split with a severity floor, designer and live-verification gates, a measurable done-when list and the standing rules, then measures the file with `wc -c`. |
| `dispatch` | `/cure:dispatch` | Hands a task from the current session to the dispatcher as a queued job: fills a handoff file from the session's context, writes it with `cure-job new` and sends the dispatcher the job id. When the estimate of a repository, plus the current diff of the target PR, exceeds the cap (`split.limit` × `split.factor`), it splits without asking into the fewest chained part jobs (`after:`), each at or under the cap. |
| `split` | `/cure:split` | Splits a finished branch into a chain of parts, each at or under the cap and each building and passing its tests. It plans the whole chain first, removes the excess from `<branch>` and stacks one branch per part. Under `delivery: pr` it creates a ticket per part (tracker from the ticket form, `split.tracker` with no ticket), pushes the chain and opens the pull requests; under `commit` (the default) it creates only the local stacked branches. The `delivery`, `tracker` and `qa` agents run git, tickets and tests. `cure:goal` calls it when a job's diff passes `split.factor` times its estimate and the PR diff passes the cap. |
| `note` | `/cure:note` | Gives working notes one home per repository, frontmatter that states their own end, and a sweep that deletes the ones a merged PR or committed document has superseded. Also writes design notes (problem, decisions, rejected, open, next steps). |
| `retro` | `/cure:retro` | Turns the retrospectives in `~/.claude/retros/` into GitHub issues: merges equal proposals, checks them against the target file and the existing issues, shows one table for review, creates the accepted issues and deletes each retrospective once all its proposals have a decision. Appends `stats.md` rows for legacy retrospectives that have a Measurements section. |
| `explain` | `/cure:explain` | Explains a technology, design or codebase as a stepwise conversation rather than one dense answer. Builds a tree from the user's questions and answers one node per message. |
| `review-change` | `/cure:review-change` | Runs a multi-agent review as a pipeline: the collector once, then the reviewing agents in parallel against its digest, then one merged report triaged into MUST-FIX, SHOULD-CONSIDER, NITPICK and `enhancement`. A round passes when no MUST-FIX or SHOULD-CONSIDER is open. A re-check mode skips the collector on a small diff. |
| `architecture-doc` | `/cure:architecture-doc` | Writes an architecture document with the user one section at a time, in the layout of `checklist-architecture.md`. Drafts and reviews each section with the `architect` agent. |

**Output style** — `Flat` (`plugins/cure/output-styles/flat.md`), shown as `cure:Flat`. It sets
`force-for-plugin: true`, so it applies whenever `cure` is enabled and overrides the user's
`outputStyle` setting. It keeps Claude Code's coding instructions. The limit reads: "A reply is a
few lines, with no headings and at most one table."; the exceptions are error output, failing tests,
security findings, confirmations for destructive actions, any detail the user explicitly asks for,
and every reply made while a skill that prescribes its own reply format is in use, however the skill
was started.

**Hooks** — `plugins/cure/hooks/hooks.json`, both enforcing the `Flat` rules on identifiers and
soft-offer closers; the reminder also restates the reply-length limit. The output style carries the
length and identifier rules in full. Names go on identifiers the user knows or can open (tickets,
PRs, issues, controls, sections, requirement ids). In a reply, an id the user cannot open and has
not seen (review finding numbers, ledger item numbers, a job's internal step or work-item numbers)
is not cited; the problem is stated in one sentence instead. Artifacts are exempt: a commit message
may carry a bare "work item N" or "step N", and a PR body names the item. A table of fixes has a
Problem column before the Fix column. The problem a change solves is not background; the length
rule does not drop it.

| Event | Script | Effect |
|---|---|---|
| `UserPromptSubmit` | `flat-reminder.sh` | Adds a three-rule reminder (reply length, named references, no soft-offer closer) as hidden context on every prompt. |
| `PreToolUse` | `flat-artifact-check.sh` | Denies `git commit`, `gh pr`/`gh issue` `create`/`edit`/`comment`, and ClickUp create/update/comment calls whose text has an identifier without its name or a soft-offer closer. Code spans and fenced blocks are not checked. |

**Status line** — the terminal status line under the input box.

| File | Description |
|---|---|
| `statusline/statusline.sh` | Renders four groups: rate-limit use (5-hour and 7-day, each with the time until it resets), the context-window bar, cost (the session unlabeled, then cached `ccusage` totals for today as `1d` and this week as `7d`), then the model and the git branch. |

```
5h 1% 5h · 7d 8% 6d | ctx ▓░░░░░░░░░ 6% | $0.76 · 1d $58.78 · 7d $58.78 | Opus 5.5 · main
```

The colours are chosen for a dark background. On a light terminal theme set
`CURE_STATUSLINE_THEME=light` in the environment Claude Code starts from.

Claude Code reads `statusLine` only from a settings file, never from a plugin manifest, so it cannot
be loaded as a plugin component. Point `~/.claude/settings.json` at a shim that resolves the newest
installed copy:

```json
"statusLine": {
  "type": "command",
  "command": "bash /Users/<you>/.claude/statusline-command.sh"
}
```

```sh
# ~/.claude/statusline-command.sh
shopt -s nullglob
dirs=(~/.claude/plugins/cache/zagrichanskiy/cure/*/statusline/statusline.sh)
[ ${#dirs[@]} -eq 0 ] && exit 0
script=$(printf '%s\n' "${dirs[@]}" | sort -V | tail -1)
exec bash "$script"
```

Requires `jq`, `git`, `bc` and `npx` on `PATH`; runs on macOS and Linux. `ccusage` runs `--offline`
against a pinned version, so nothing here reaches the network. Offline prices are the ones bundled
with that version: a model released after the pin costs `$0.00` until `NPX_PKG` in the script is
bumped.

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
| Production | `test-author`, `skill-author` | `sonnet` | `medium` |
| Mechanical | `collector`, `verifier` | `sonnet` | `medium` |
| Rule check | `cg-interfaces`, `cg-classes`, `cg-resources`, `cg-statements`, `cg-generic`, `cg-concurrency`, `cg-philosophy` | `sonnet` | `medium` |
| Mechanical | `qa` | `sonnet` | `low` |
| Mechanical | `tracker`, `delivery` | `sonnet` | `low` |

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
scripts/lint-plugin.py            frontmatter, manifest and hooks lint, run in CI
.github/workflows/validate.yml    runs the lint on every push and pull request
plugins/<name>/
  .claude-plugin/plugin.json      plugin manifest (name, version, metadata)
  agents/<name>.md                one file per agent, auto-discovered
  skills/<name>/SKILL.md          one directory per skill, auto-discovered
  output-styles/<name>.md         one file per output style, auto-discovered
  hooks/hooks.json                hook registrations; scripts beside it, auto-discovered
  statusline/statusline.sh        status line script, wired up through a settings shim
  knowledge/                      reference material the agents read at run time
    design-advisor/lang/          per-language supplements, loaded only for the target's language
    reviewer/lang/                per-language pitfall supplements for the reviewer
    cpp-core-guidelines/          condensed C++ Core Guidelines sections, cg-* procedure
```
