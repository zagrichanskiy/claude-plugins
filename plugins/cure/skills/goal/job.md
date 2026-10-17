# Job run

The session running the skill is the dispatcher. It invokes the skill with a handoff file and a job
directory. A worker session then runs the goal and cannot reach the user.

## Input

- The job directory is the handoff's directory. The job id is that directory's name.
- Read the handoff file as the conversation.
- Read `defaults.md` under `${CURE_JOB_ROOT:-~/.claude/cure}` before the question round. A missing
  file means no defaults. Do not ask a fork it answers; mark that decision `(default)` under
  Settled.
- Take the repository's build, review and verify agents and its PR skill from the handoff's
  `## Tools` section.

## Where it goes

| File | Path |
|---|---|
| Goal | `<job>/goal.md`. The `.notes/` exclusion is skipped for it. |
| Ledger | `.notes/ledger-<slug>.md` in the handoff's first repository |
| Backlog | `.notes/<slug>-backlog.md` in the same repository |

A Solo goal has no ledger and no backlog.

Apply the `.notes/` exclusion for the ledger and the backlog, as the `note` skill describes. The job
directory belongs to the CLI: the goal never deletes it.

## Questions

The dispatcher asks the user in the question round. The questions are the handoff's `## Open` items
plus any fork `defaults.md` does not answer. Ask them with `AskUserQuestion`, record the answers
under Settled, then write `<job>/goal.md`. Each question carries its own context: the situation,
the options, the consequence of each, and a recommendation.

After `needs-input`, add the user's answers under Settled the same way. Then add one line under
Settled: "Run <n>: the questions of the earlier `needs-input` exit are answered above and closed;
continue from `<ledger path>`". Solo: "Run <n>: the questions of the earlier `needs-input` exit are
answered above and closed; earlier work is in the tree".

The line holds for both next steps: a resume of the kept session (`cure-job resume`) and a new run
in a new session (`cure-job launch`) when the old one is gone.

At run time the worker takes the `needs-input:` exit for a question only the user can answer.

## Template text

The worker sees only the goal file. Fill these slots when writing it: `<plugin-root>` with the
plugin root from `SKILL.md`, `<id>` with the job id, `<dispatcher>` with the name of the session
running the skill. If the session cannot determine its name, ask the user for it in the question round.

The template's read-first line becomes:

```markdown
Before work item 1, read `<plugin-root>/skills/goal/rules.md` and
`<plugin-root>/skills/goal/worker.md` and follow them. Read them again after a context compaction
and before an exit.
```

Closing done-when item, after the template's last item:

```markdown
N+1. Reported: `finish <id> --status done` exited 0 and the `job <id>` `SendMessage` to
   `<dispatcher>`, or its error, are shown. A `finish` that exits non-zero is run once more.

Met when items 1-N are each demonstrated or listed in the shown `finish --unproven` with a reason
in the final message, and N+1 is demonstrated. Unproven only when the worker cannot obtain the
proof, never when its check ran and failed.
```

Exits, in the template's exits slot:

```markdown
Also done when (a) <turns> turns have passed, or <rounds> rounds ended on a measured failure, or
<review cause>, or the diff passes <lines> lines (`git diff --shortstat <base>`), or `git fetch` or
a tool check failed, or `finish` exited non-zero twice, or a Settled statement is false or the
title's outcome is unachievable; and (b) the retrospective's summary, naming the cause, is in the
transcript; and (c) reported as in N+1 with `--status failed`, unless `finish` exited non-zero
twice; and (d) the final message starts with `failed:`.

Also done when a question only the user can answer is open, reported as in N+1 with `--status
needs-input`, and the final message starts with `needs-input:`.
```

Review cause: Light as in "Agent tier". Full, written whole: "a `MUST-FIX` or `SHOULD-CONSIDER` is
open after review round 3". When the handoff's `delivery` is `commit` (the default), the generated
text carries no pull-request wording.

Clean-up work item: write "The failure and `needs-input` exits skip this item." in place of "The
failure path skips this item."

A Solo exit has (a) without `<rounds>` and `<review cause>`, then the report clause as (b) and the
final-message clause as (c).

## Launch line

Report the absolute line, with no `claude --bg` form:

```
<plugin-root>/bin/cure-job launch <id>
```
