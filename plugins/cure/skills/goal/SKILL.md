---
description: Write the goal file that `/goal @<file>` runs from — a self-contained brief a fresh session can execute unattended. Asks every open question in one round first, then writes the orchestrator-led work items with an agent per step and a closing retrospective, the measurable done-when list and the standing rules. Use when the user says "write a goal", "create a goal md", "capture this as a goal", or "/cure:goal", typically after settling a design in conversation.
allowed-tools: Read, Write, Edit, Grep, Glob, Bash, AskUserQuestion
---

# Goal

`/goal <condition>` is a built-in command. It sets a completion condition, and a small fast model
re-reads it after every turn: not yet met starts another turn, met or impossible clears it. The
evaluator runs no tools and reads no files — it judges only what the session has already put in the
transcript.

This skill writes the file behind `/goal @<file>`. The file is the condition, not a design document.
Everything in it is read by the evaluator on every turn and must be something the session's own
output can demonstrate.

## The question round comes first

**Ask every open question before writing the file, in one `AskUserQuestion` call.** This is the
point of the whole skill. The user answers once, then leaves; a goal that stops on turn six to ask
which subnet to use has wasted the time it was meant to save.

Before asking, settle everything you can yourself — read the code, the recipe, the ticket. What
survives is a real fork: two readings that produce different work. For each, give the options you
would actually recommend between, with the consequence of each spelled out.

Then, and only then, write the file.

## Where it goes

`.notes/goal-<slug>.md` in the repository the work happens in, `.notes/` excluded through
`$(git rev-parse --git-dir)/info/exclude` as the `note` skill describes.

A goal file is a working file. Its end is the merge of the work it describes. Say so in the report,
and delete it when that lands.

## What goes in it

**The goal file carries the context. The ticket stays thin.** A fresh session opens with `/goal
@<file>` and nothing else, so whatever it needs to act must be in the file or reachable from it.

**Keep it under 4000 characters** — the limit on a `/goal` condition. Reference rather than restate:
the repository's `CLAUDE.md` already covers conventions, layout and working style, and the code and
recipes say what they contain. Name the file to read; do not summarise it. What the file must hold
outright is what reading the repository will not tell you — the decisions taken in conversation and
the reasoning that would otherwise be re-litigated.

## Anatomy

```markdown
# <What is true when this is done>

## Context

<Where the work happens. "Settled:" then the decisions and facts, as a list.>

## Work

The main session orchestrates: it dispatches agents, keeps the ledger, checks completeness. It
reads no source and edits no code.

1. Run `git fetch`; check that `main` equals `origin/main`. Check ticket, branch, named files and
   each tool Done-when runs (`gh auth status`). A false Settled statement, a failed fetch or a failed
   tool check is a failure cause. Base moved: base the work on `origin/main`. Other mismatch: record
   it, use the corrected value.
2. <One step, its agent, its files.>
N-1. Write the retrospective to `~/.claude/retros/<date>-<repo>-<slug>.md`; print its summary.
N. Delete `<ledger path>` and `<each working file>`. Keep the goal file, the retrospective,
   `.notes/<slug>-backlog.md`. The failure path skips this item.

## Done when

1. <Measured by a command this session runs.>
N-1. The retrospective exists with a "Proposed changes" table; its summary is in the transcript.
N. `ls <ledger path> <working files>` reports "No such file" for each.

Also done when (a) <turns> turns have passed, or <rounds> rounds ended on a measured failure, or a
`MUST-FIX` or `SHOULD-CONSIDER` is open after a PR's review round 2, or the diff passes <lines>
lines (`git diff --shortstat <base>`), or `git fetch` or a tool check failed, or a Settled
statement is false or the title's outcome is unachievable; and (b) the retrospective's summary,
naming the cause, is in the transcript; and (c) the final message starts with `failed:`.

## Rules

- Ask nothing. Decide from the code; state the assumption. Scope with `grep` first.
- <Agent plan: who does which step, what runs in parallel, which advisor to consult.>
- Pass agents paths and ids. Ask for findings only.
- When a failure cause holds: stop, write the retrospective with the cause and what is left, print
  its summary, keep the ledger, end with a message starting `failed:`.
- Stage git changes with explicit paths; never `git add -A` or `git add .`.
- Run `test-author` only for a behaviour change that has no test.
```

## Writing the done-when list

The evaluator cannot check a claim the transcript does not contain. `The gadget works` fails; `ip
addr show usb0 reports 192.168.140.1/24` passes, because running it puts the answer where the
evaluator can read it.

Each item needs one measurable end state and the check that demonstrates it. Add the constraints
that must survive the work — what must not change, what must keep passing — as their own items;
those are the ones a goal quietly breaks.

Rules for the items:

- Every outcome named in the title has an item that measures it. An outcome with no item passes
  unproven. An outcome is measured with its qualifiers: "one PR against `main`" needs an item that
  compares both the count and the base, not the count alone.
- An outcome stated as a value (a version, a count) is compared with that value, not only printed.
- Each command states its preconditions (a venv, a tool, a login, a running service), or a work item
  sets them up, or work item 1 checks them. Work item 1 checks every executable a done-when command
  starts with, except one that a work item builds or installs, one check each (`gh auth status`,
  `claude --version`, `python3 --version`), not only these examples.
- An item that measures replies to a fixed prompt set never asks about state the run changes, such
  as the branch's commits.
- An item that measures a model's replies to a fixed prompt set states samples per prompt and the
  pass threshold, for example 3 runs, all pass.
- Write the repository's base branch in the fact check. For base `main` the file says `main` equals
  `origin/main`.

Always end with the failure exit shown in the template. The `/goal` Stop hook blocks every stop
that is not a met condition, so a cap that only says "stop" blocks every stop after it. The exit is
a conjunction: a failure cause holds, the retrospective's summary naming the cause is in the
transcript, and the final message starts with `failed:`. The evaluator reads the transcript only,
so the summary is printed, not just written to a file.

The clean-up work item and its done-when item are copied from the template with only the path slots
filled. Never shorten or merge them to meet the length limit. Write the ledger path in full in both,
even when Context names it, and write out each deleted working file. Every file or directory a work
item creates outside version control (a temporary copy, a run directory, a worktree, a fixture) is
written as a path in that work item. The same path is in the clean-up item and in its done-when
`ls`. The work item says the goal file and the retrospective are kept. Save characters in
Context or the work steps.

A Settled statement is a decision or fact the goal rests on. A false one fails the run. A
mismatch in ticket, branch or base commit is recorded and corrected.

## Name the tools, not the intention

A goal file is written for one repository, so it names that repository's own agents, skills and
commands. `verify it works` gets satisfied by reasoning about the code; `prove it on the device with
<the project's hardware agent>` does not. The same holds for the build command, the review agent,
and the skill that opens the pull requests.

Take the names from the session's own agent and skill list, and prefer the project's plugin over a
general one wherever both offer something. A general plugin's reviewer named for work a project
agent covers proposes a tool the project does not use.

## Delegate, then reflect

Every goal has this structure. The user runs goals unattended and pays for the orchestrator's
context on every turn.

| Part | What the goal file states |
|---|---|
| Orchestrator | The main session dispatches, tracks and checks. It does not read source or edit code. |
| Agent per step | Each work item names its agent. Items with disjoint files run in parallel. |
| Review-then-fix split | Round 1 produces a triaged fix list, not fixes; "backlog" names only the `NITPICK` and `enhancement` items, never a `MUST-FIX` or `SHOULD-CONSIDER`. Fixes ship as small PRs per component, each with at most 2 review rounds, the cap counted per PR and not across the whole effort, and a round ended by a measured failure counts apart from a round spent on review findings. A measured-failure round is one that ended on a failed test or check, not on review findings. The round cap is a failure exit in the template. A `MUST-FIX` or `SHOULD-CONSIDER` still open after a PR's round 2 takes the failure exit; no round 3 starts. The fix step commits each round with explicit paths, new files included, before the re-check runs. |
| Consultation | Which advisor answers a hard implementation question: `designer` for class level, `architect` for component level. The answer is recorded before the implementer starts. A class flagged in 2 consecutive review rounds gets a `designer` consult before an implementer touches it again; the round-1 triage and the PR's first review round count as consecutive for this gate. The orchestrator never writes the class-level decision itself. |
| Review loop | Review, fix, re-review stops at the severity floor: done when no `MUST-FIX` or `SHOULD-CONSIDER` finding is open. `NITPICK` and `enhancement`-tagged findings go to a backlog, not into another round; see the `review-change` skill for the triage words. A ledger file holds every finding and its status. State a token budget per agent per round in the goal; `review-change` defaults to 400k tokens per agent per round if the goal states none. |
| Verification | `qa` runs the suite after each fix. Its pass count is a done-when item. Before merge, a live-verification gate also runs: the `verifier` agent's output is the done-when item. An unattended session cannot prove a manual check, so a manual check goes into the PR checklist, never into the done-when list. A green test suite alone does not clear this gate. |
| Retrospective | The second-last work item and the done-when item before the clean-up item. |

## The retrospective

It lives in `~/.claude/retros/`, not in `.notes/`. A working note is deleted when its work merges,
and a retrospective there is deleted with it before anyone acts on it.

It holds, in this order:

| Section | Content |
|---|---|
| Outcome | "met", or "failed: <cause>, what is left". |
| Measurements | Turns used of the cap. Per agent: dispatches, tokens where reported, review rounds, measured-failure rounds, findings per severity, findings accepted. Changed lines against the cap. |
| Where it went wrong | Each event with its evidence: the turn, agent, finding id or command. Rework, stale facts in the goal file, a stop, a permission prompt, a round that found only `NITPICK`. |
| Proposed changes | One row per change: target file (agent, skill, knowledge file, project `CLAUDE.md`, or this format), the change, the evidence row it rests on, the expected effect. |

A proposal with no evidence row is not made. The session writes proposals only; it never edits a
plugin or a skill. The user applies them in the plugin repository.

## Sizing a goal

Bound a goal by deliverables, not by lines: one reviewable concern, one PR, and a done-when list the
user can re-run. The changed-line cap in the failure exit is a stop signal, not the scope. A goal that
reaches it takes the failure exit instead of growing.

Size a goal from earlier retrospectives. The "Measurements" table of a similar goal gives turns,
tokens and lines.

## Running it

Report the exact line to paste:

```
/goal @.notes/goal-<slug>.md
```

Two things worth saying once when handing it over:

- Pair it with auto mode, or every unapproved tool call stops the goal for a permission prompt.
- A rate limit does not clear a goal — Claude Code waits and continues. An exhausted credit balance,
  an auth failure, an unrecoverable context overflow and an unavailable model do clear it, with a
  warning; `/goal` again resumes.

## Notes

- One goal, one file. A brief covering two unrelated outcomes converges on neither.
- Carry every work item inline, by id and text. Do not point at another note by `file:line`. Notes
  are deleted and edited, and the reference goes stale without an error.
- Write the goal just before it runs. A goal written days ahead carries facts that have drifted.
  Work item 1 catches some of them, not all.
- Keep rejected options out. The evaluator re-reads this file every turn and a rejected option in it
  reads as work to do. If the rationale is worth keeping, it goes in the ticket or the design
  document.
- Do not start implementing. Write the file, report the path and the command, and stop.
