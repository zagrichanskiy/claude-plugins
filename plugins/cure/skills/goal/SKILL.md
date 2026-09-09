---
description: Write the goal file that `/goal @<file>` runs from — a self-contained brief a fresh session can execute unattended. Asks every open question in one round first, then writes the work items, the measurable done-when list and the standing rules. Use when the user says "write a goal", "create a goal md", "capture this as a goal", or "/cure:goal", typically after settling a design in conversation.
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

1. <One step. Name the file or recipe it touches.>
2. ...

## Done when

1. <Measurable, and provable by something this session runs. `pytest` passes in `src/foo`. The
   build exits 0. `ip addr show usb0` reports the address.>
2. ...

## Rules

- Ask nothing. Every open question was answered before this goal started; decide the rest from the
  code and state the assumption.
- Establish scope with `grep` and `glob` first. Read a whole file only once it matters.
- <Agent plan, when the work suits one — see below.>
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

## The agent line

When the work splits into parts that do not depend on each other, name the agents and the order in
the Rules section rather than leaving it to the run. Plan it in the file; do not make the executing
session invent a fan-out mid-goal.

When the work is one sequence, leave the line out. An agent per step costs more than it saves.

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
