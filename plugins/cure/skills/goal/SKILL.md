---
description: Write the goal file that `/goal @<file>` runs from, a self-contained brief a fresh session can execute unattended, either for a direct run in the current session or for a job run from a handoff file. Use when the user says "write a goal", "create a goal md", "capture this as a goal", or "/cure:goal", or when a caller passes a handoff path or a job directory.
allowed-tools: Read, Write, Edit, Grep, Glob, Bash, AskUserQuestion
---

# Goal

`/goal <condition>` is a built-in command. A small model re-reads the condition after every turn. It
runs no tools and reads no files: it judges only what the transcript holds. This skill writes the
file behind `/goal @<file>`. Everything in it must be something the session's own output can
demonstrate.

## Mode

| Given | Mode | Read exactly one file |
|---|---|---|
| A handoff path or a job directory | Job run: a worker session runs the goal and ends through `done`, `failed:` or `needs-input:` | `${CLAUDE_PLUGIN_ROOT}/skills/goal/job.md` |
| Neither | Direct run: the user runs the goal in a session | `${CLAUDE_PLUGIN_ROOT}/skills/goal/direct.md` |

Read the mode file before the question round. Only this file has
`${CLAUDE_PLUGIN_ROOT}` expanded: write its value into every `<plugin-root>` slot of the template and
of the mode file's text.

Read `${CLAUDE_PLUGIN_ROOT}/skills/goal/delegation.md` before choosing the tier and the agents, and
`${CLAUDE_PLUGIN_ROOT}/skills/goal/sizing.md` when Settled has an estimate or the goal has a test-author step.
Read `${CLAUDE_PLUGIN_ROOT}/skills/goal/done-when.md` before writing the Done when list, Settled, the
exits and the clean-up items.

## The question round

Ask every open question before writing the file, in one round, as the mode file says.

- Settle first what you can: read the code, the recipe, the ticket. What survives is a real fork: two
  readings that produce different work.
- A question is a choice that changes behaviour the user would see, or a place where the source
  (conversation, handoff, design document) is silent or contradictory on such a choice. Never decide
  it silently.
- A mechanical choice that the code or conventions determine is decided and recorded as an
  assumption. A fork whose options differ in nothing the user would see takes the recommended option,
  recorded as the mode file says.
- Each question carries the situation, the options you would recommend between (each an action the
  session or its tools can take; in job mode `cure-job` is one), the consequence of each and a
  recommendation.
- Print the chosen tier and its reason in the round. With no question, print the tier alone. The user
  can override it.
- When a docs review may find two files that state one rule differently, one question asks for an
  ownership policy: the file whose topic the rule is, or an ordered list of files. The answer goes
  under Settled.

Then write the file where the mode file says.

## What goes in it

- The file carries the context; the ticket stays thin. A fresh session has only `/goal @<file>`.
- Reference the repository's `CLAUDE.md`, code and recipes by file name; do not summarise them. Hold
  outright the decisions taken in conversation and the reasoning that would be re-litigated.
- Keep the file short: it is the condition, not a design document.
- Measure the file with `wc -c <file>` after writing and report the count.
- Carry every work item inline, by id and text; never point at a note by `file:line`.
- Keep rejected options out of the file.

## Anatomy

```markdown
# <What is true when this is done>

## Context

<Where the work happens. Settled: the decisions and facts.>

<Job mode only, after Settled: `## Open`, one `- ` item per fork (see `job.md` "Questions").>

## Tools

- Prose reviewer: <the prose reviewer the repository names (`delegation.md` "Name the tools"), or
  "none: the repository names no prose reviewer; no round has a prose review step">.

## Work

Before work item 1, read `<plugin-root>/skills/goal/rules.md` and follow it. Read it again after a
context compaction and before an exit.

1. Fact check: `<base>` equals `origin/<base>` (for a base taken from a predecessor or marked
   "Base: the PR branch of split part 1", the check of `rules.md`); <ticket, branch, named files>;
   <each tool Done-when runs>; <each Settled fact marked verify>. Print `date --iso-8601=seconds`
   as `<start>`.
2. <One step, its agent, its files.>
K-1. (Light and Full, when Settled has an estimate) <the size-check item text of `sizing.md`>
K.   <The push and the pull request, when the job pushes. K is the item before the retrospective.>
N-2. (Light and Full) Write the retrospective to `~/.claude/retros/<date>-<repo>-<slug>.md`; print
     its summary.
N-1. Append the `stats.md` row with the command of `rules.md`. `<date> | <repo> | <slug>` is filled
     in here.
N. Delete `<ledger path>` and `<each working file>`. Keep the goal file and the retrospective.
   The failure path skips this item.

## Done when

1. <Measured by a command this session runs.>
N-2. (Light and Full) The retrospective has "Outcome", "Where it went wrong" and "Proposed changes" sections; its summary is printed.
N-1. `grep -cF '| <date> | <repo> | <slug> |' ~/.claude/retros/stats.md` prints `1`.
N. `ls <ledger path> <working files>` reports "No such file" for each.
N+1. `ls -l --time-style=full-iso <repo>/.notes/*backlog*.md` shows no file with an mtime after
     `<start>`. It is the last item; number it after the last item the tier keeps.

<Mode file: the closing done-when item, if any.>

<Exits: the mode file's text. It holds the failure exit, with <review cause> from delegation.md.>

## Rules

- Tier: <Solo, Light or Full>. <Agent plan: steps, agents, parallel work, advisor.>
- Stops: this goal overrides the user's "run one step and stop" rule; it stops only at its exits.
- Permission mode: <the mode the user chose in the leave-auto-mode question; omit otherwise>.
- Waiting: <job mode: the mode file's Waiting line. Direct mode: takes the `waiting:` exit of direct.md>.
```

Write the Permission mode line only when the user chose a mode in the
leave-auto-mode question (job runs: the caller passes the mode).

## The retrospective

Light and Full goals write one, with sections Outcome, Where it went wrong, Proposed changes, in that
order. Solo writes none. Read `${CLAUDE_PLUGIN_ROOT}/skills/goal/sizing.md` "The retrospective" before writing the retrospective work item.

## Sizing a goal

Bound a goal by deliverables: one reviewable concern, one PR. Estimate test lines apart from code:
tests of a state-machine change at 2x its code, validator tests per key, a legacy parser separately.
The rest is in `sizing.md` "Sizing a goal".

## Running it

Report the launch line the mode file gives. A job run of tier Light or Full starts with
`--agent cure:orchestrator`; a Solo job run and a direct run start as plain sessions. Do not start
implementing: write the file, report the path and the command, and stop.
