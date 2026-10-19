# Job run

The session running the skill is the dispatcher. It invokes the skill with a handoff file and a job
directory. A worker session then runs the goal and cannot reach the user.

## Input

- The job directory is the handoff's directory. The job id is that directory's name.
- Read the handoff file as the conversation.
- Read `handoff.delivery`, `handoff.base`, `handoff.branch` and `handoff.resource-risk` with
  `<plugin-root>/bin/cure-job config get <key>` before the question round. Each prints JSON; the
  built-in default applies when `config.json` has no value. Do not ask a fork a value answers; mark
  that decision `(default)` under Settled. Never read `config.json` itself.
- Take the repository's build, implement, review and verify agents and its PR skill from the
  handoff's `## Tools` section.
- Copy each `Resource risk:` line of the handoff's Settled into the goal's Settled verbatim. Copy
  each `handoff.resource-risk` entry whose scope matches into Settled as its `text`, marked
  `(default)`, unless the handoff states a risk for the same resource. A scope `all` matches every
  job. A scope `device: <name>` matches a handoff whose `device` value is `<name>`. Never shorten
  or drop these lines to save characters.
- A handoff with `device: bench` declares bench use. The goal must carry the short-hold claim and
  release (below).

## Base per repository

Applies when the row of the job in `cure-job list --json` has `after`. Without it, `base` comes
from the handoff.

For each repository R in the handoff's `repos`, set `base` as follows. Walk the chain from the
row's `after`. Never use the handoff's `after:`.

| Step | Rule |
|---|---|
| Start | The job named by the row's `after`. |
| Changes R | R is in `repos` of the job's `handoff.md` (the row's `dir`). The row's `resources` also hold claimed repositories, which do not count. |
| Stop, resolved | The first job that changes R. `base` is the branch named in that job's `goal.md`. |
| Next job | The `after` of the current job's row. |
| Stop, unresolved | A passed row has `after-state` `missing` or `invalid`. |
| End of chain | No job changes R: `base` comes from the handoff. |

Ask the user for the base of each repository left unresolved, in the question round. A job on the
chain need not be `done` when the goal is written, but it has a `goal.md`: the dispatcher drafts a
successor's goal only after the predecessor's row has `goal` true. Every job on the chain is `done`
when the successor launches, and the work item 1 base check tests the branch then.

Write the base per repository in the goal's fact check. For a base taken from a predecessor, the
fact check is the one in `rules.md`, not `<base>` equals `origin/<base>`.

## Writing the goal

- Write each done-when command with absolute paths or `git -C <absolute path>`. The worker starts
  in the first repository, so a path relative to the origin session's directory does not resolve.

## Short holds in the goal

The bench is not held from launch: `device: bench` does not add `device:bench` to the job's
resources. The claimant claims it per step. The goal tells the claimant the following:

- Claim `device:bench` before each step that uses the bench, and `build:<absolute path>` before each
  step that runs `bitbake`, `devtool` or `kas`. Release at the end of the step.
- The rules are in `<plugin-root>/skills/goal/worker.md` "Short holds". The goal repeats none of
  them and names the build directory of each build step.
- Verify steps that use the bench carry their own claim and release in the work items.

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
plus any fork `config get` does not answer, except a fork with no user-visible effect: record its
recommended option under Settled as `(recommended)` and do not ask it. Ask them with
`AskUserQuestion`, record the answers under Settled, then write `<job>/goal.md`.

After `needs-input`, add the user's answers under Settled the same way. Then add one line under
Settled: "Run <n>: the questions of the earlier `needs-input` exit are answered above and closed;
continue from `<ledger path>`". Solo: "Run <n>: the questions of the earlier `needs-input` exit are
answered above and closed; earlier work is in the tree".

The line holds for both next steps: a resume of the kept session (`cure-job resume`) and a new run
in a new session (`cure-job launch`) when the old one is gone.

At run time the worker takes the `needs-input:` exit for a question only the user can answer.

## Checks before launch

The dispatcher runs the Repository check before writing `<job>/goal.md`, because the ledger path and the Permissions check depend on the first repository. It runs the other checks after writing it. All run again on every wake before a launch.
A failed check is fixed, or asked about in the dispatcher's question round, before launch.

| Check | How | On failure |
|---|---|---|
| Tools | Run each executable that work item 1's tool check names, with the check's command, for example `devicectl --help`. | Install or fix it, or ask the user. After the user installs it, run the check again. |
| Permissions | For each classifier-gated action the goal needs (for example `git commit --amend`, a force-push, device power), read the permission rules the worker loads. See the list below. | No rule allows the action: ask the user. |
| Repository | Compare the handoff's first `repos` entry with the repositories the Work items edit. | The first repository holds none of the Work's edits: ask the user. See the answers below. |
| Length | Run `wc -c <job>/goal.md`. | None. Report the count with the launch line. |

The worker starts in the handoff's first repository. It loads these permission rules:

- `~/.claude/settings.json`.
- The managed settings file. Linux: `/etc/claude-code/managed-settings.json`. macOS:
  `/Library/Application Support/ClaudeCode/managed-settings.json`.
- `.claude/settings.json` and `.claude/settings.local.json` of the handoff's first repository.
- The arguments given to `cure-job launch` after `--`, such as `--allowedTools` or `--settings`.

An action counts as allowed only when an `allow` rule matches it and no `deny` or `ask` rule
matches it. `Bash(<command prefix>:*)` matches a command by prefix. An MCP tool rule is
`mcp__<server>__<tool>`.

Approval of an action written in `goal.md` does not reach the auto-mode classifier. An approval the
user gives in the dispatcher session does not either, so it does not pass the check. The question
for a failed permission check offers these answers:

| Answer | Effect |
|---|---|
| The user adds an allow rule | The check runs again. |
| Drop the action | `goal.md` is edited through `cure:goal`. The check runs again. |
| Launch anyway | The run is accepted to stop at `needs-input` when the classifier denies the action. |

The question for a failed Repository check offers these answers:

| Answer | Effect |
|---|---|
| Re-dispatch | The dispatcher runs `cure-job close <id>`. It sends the row's `origin` one line with `SendMessage`: the job id and "closed: re-dispatch with <repository> first in `repos`". When the `SendMessage` fails or the row has no `origin`, it prints the line in its own session. The origin session queues a new handoff with that repository first. |
| Start in the first repository anyway | The decision is recorded under Settled in `goal.md`. The check passes on later wakes. |

The dispatcher never adds a permission rule and never passes `--allowedTools` itself.

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
<review cause>, or the diff passes <lines> lines (per repository, `git -C <repo> diff --shortstat <base commit>`, the commit work item 1 recorded), or `git fetch` or
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

The retrospective's changed lines are measured the same way, per repository against its base
commit. A cap against the branch name would count only uncommitted lines when the job commits on
`<base>` itself.

Clean-up work item: write "The failure and `needs-input` exits skip this item." in place of "The
failure path skips this item."

A Solo exit has (a) without `<rounds>` and `<review cause>`, then the report clause as (b) and the
final-message clause as (c).

## Launch line

Report the absolute line, with no `claude --bg` form, and the `wc -c` count of `<job>/goal.md`. The dispatcher runs `cure-job approve <id>` first; a run-1 launch of a job that is not `approved` is refused:

```
<plugin-root>/bin/cure-job launch <id>
```
