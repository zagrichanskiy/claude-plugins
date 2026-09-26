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

<Where the work happens and which decisions are already settled. Point at the files that hold the
rest — a recipe, a module, a ticket id and name — rather than restating them.>

## Work

The main session is the orchestrator. It does not read source or edit code. It dispatches agents,
keeps the ledger and checks completeness.

1. <One step, the agent that does it, and the file or recipe it touches.>
2. ...
N. Write `.notes/<slug>-retro.md`: per agent, what it did, findings raised and accepted, cost where
   reported; what was effective; what was not; concrete changes to agents, skills or this format.

## Done when

1. <Measurable, and provable by something this session runs. `pytest` passes in `src/foo`. The
   build exits 0. `ip addr show usb0` reports the address.>
2. ...
N. `.notes/<slug>-retro.md` exists and its summary is in the transcript.

## Rules

- Ask nothing. Every open question was answered before this goal started; decide the rest from the
  code and state the assumption.
- Establish scope with `grep` and `glob` first. Read a whole file only once it matters.
- <Agent plan: which agent does which step, what runs in parallel, which advisor to consult on a
  hard question.>
- Save tokens: pass agents paths and ids, not file content. Ask for findings or results only. The
  orchestrator does not re-read files an agent already read.
- Stage git changes with explicit paths; never `git add -A` or `git add .`.
- Run `test-author` only for a behaviour change that has no test.
- Stop after <N> turns and report what is left.
```

## Writing the done-when list

The evaluator cannot check a claim the transcript does not contain. `The gadget works` fails; `ip
addr show usb0 reports 192.168.140.1/24` passes, because running it puts the answer where the
evaluator can read it.

Each item needs one measurable end state and the check that demonstrates it. Add the constraints
that must survive the work — what must not change, what must keep passing — as their own items;
those are the ones a goal quietly breaks.

Always end the list with a turn bound. Without one a goal that cannot converge runs until something
else stops it.

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
| Review-then-fix split | Round 1 produces a triaged fix list, not fixes; "backlog" names only the `NITPICK` and `enhancement` items, never a `MUST-FIX` or `SHOULD-CONSIDER`. Fixes ship as small PRs per component, each with at most 2 review rounds, the cap counted per PR and not across the whole effort. A `MUST-FIX` or `SHOULD-CONSIDER` still open after round 2 stops that PR; the orchestrator reports it to the user instead of starting a round 3. The fix step commits each round with explicit paths, new files included, before the re-check runs. |
| Consultation | Which advisor answers a hard implementation question: `designer` for class level, `architect` for component level. The answer is recorded before the implementer starts. A class flagged in 2 consecutive review rounds gets a `designer` consult before an implementer touches it again; the round-1 triage and the PR's first review round count as consecutive for this gate. The orchestrator never writes the class-level decision itself. |
| Review loop | Review, fix, re-review stops at the severity floor: done when no `MUST-FIX` or `SHOULD-CONSIDER` finding is open. `NITPICK` and `enhancement`-tagged findings go to a backlog, not into another round; see the `review-change` skill for the triage words. A ledger file holds every finding and its status. State a token budget per agent per round in the goal; `review-change` defaults to 400k tokens per agent per round if the goal states none. |
| Verification | `qa` runs the suite after each fix. Its pass count is a done-when item. Before merge, a live-verification gate also runs: the `verifier` agent's output is the done-when item. An unattended session cannot prove a manual check, so a manual check goes into the PR checklist, never into the done-when list. A green test suite alone does not clear this gate. |
| Retrospective | The last work item and the last done-when item before the turn bound. |

The retrospective records how the agents performed, what was effective, what was not, and what to
change. Its findings feed later changes to the agents, the skills and this format.

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
- Keep rejected options out. The evaluator re-reads this file every turn and a rejected option in it
  reads as work to do. If the rationale is worth keeping, it goes in the ticket or the design
  document.
- Do not start implementing. Write the file, report the path and the command, and stop.
