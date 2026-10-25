# Job run

The caller invokes the skill with a handoff file and a job directory. The skill never asks the user
in this mode. A worker session then runs the goal and cannot reach the user.

## Input

- The job directory is the handoff's directory. The job id is that directory's name.
- Read the handoff file as the conversation.
- Read the `CLAUDE.md` of each repository in `repos`.
- Read `handoff.delivery`, `handoff.branch` and `handoff.resource-risk` with
  `<plugin-root>/bin/cure-job config get <key>` before writing the goal. Each prints JSON; the
  built-in default applies when `${CURE_JOB_CONFIG:-${XDG_CONFIG_HOME:-~/.config}/cure/config.json}` has no value. When the handoff omits `branch`, apply `handoff.branch` (default `new`). A job with `after` and no `branch` in its handoff uses the branch of its predecessor, as `base` does (see "Base per repository"); `handoff.branch` does not apply. `new` gives the job its own branch from `base`; resolve it to the literal name `<ticket>_<slug>` (`<slug>` without a ticket), the same in every repository of the job. `current` is the branch checked out in the first repository of `repos`, the launch repository. Any other value is a literal branch name. Write the resolved literal name in the goal, never `new` or `current`. Branch handling is in `rules.md`. Do not ask a fork a value answers; mark
  that decision `(default)` under Settled. Never read `${CURE_JOB_CONFIG:-${XDG_CONFIG_HOME:-~/.config}/cure/config.json}` itself.
- Base of a job without `after`: the `base` the handoff states. When it states none, the default
  branch of each repository in `repos`, detected per repository with
  `git -C <repo> symbolic-ref --short refs/remotes/origin/HEAD` (strip the `origin/` prefix). When
  that fails, use `gh repo view --json defaultBranchRef -q .defaultBranchRef.name` run in the repository.
  When both fail, write the base as an `## Open` item, as the chain rule does. No configuration key
  holds a base. A job with `after` follows "Base per repository".
- Take the repository's build, implement, review and verify agents and its PR skill from the
  handoff's `## Tools` section.
- Copy each `Resource risk:` line of the handoff's Settled into the goal's Settled verbatim. Copy
  each `handoff.resource-risk` entry whose scope matches into Settled as its `text`, marked
  `(default)`, unless the handoff states a risk for the same resource. A scope `all` matches every
  job. A scope `device: <name>` matches a handoff whose `device` value is `<name>`. A scope `repo: <path>` matches a handoff whose `repos` lists `<path>`. Never shorten
  or drop these lines to save characters.
- A handoff with `device: bench` declares bench use. The goal must carry the short-hold claim and
  release (below).

## Base per repository

Applies when the row of the job in `cure-job list --json` has `after`. Without it, `base` comes
from the handoff or the default branch (see Input).

For each repository R in the handoff's `repos`, set `base` as follows. Walk the chain from the
row's `after`. Never use the handoff's `after:`.

| Step | Rule |
|---|---|
| Start | The job named by the row's `after`. |
| Changes R | R is in `repos` of the job's `handoff.md` (the row's `dir`). The row's `resources` also hold claimed repositories, which do not count. |
| Stop, resolved | The first job that changes R. `base` is the branch named in that job's `goal.md`. |
| Next job | The `after` of the current job's row. |
| Stop, unresolved | A passed row has `after-state` `missing` or `invalid`. |
| End of chain | No job changes R: `base` comes from the handoff or the default branch (see Input). |

Write the base of each repository left unresolved as an `## Open` item. A job on the
chain need not be `done` when the goal is written, but it has a `goal.md`: the caller drafts a
successor's goal only after the predecessor's row has `goal` true. Every job on the chain is `done`
when the successor launches, and the work item 1 base check tests the branch then.

Write the base per repository in the goal's fact check. For a base taken from a predecessor, the
fact check is the one in `rules.md`, not `<base>` equals `origin/<base>`.

## Writing the goal

- Write each done-when command with absolute paths or `git -C <absolute path>`. The worker starts
  in the first repository, so a path relative to the origin session's directory does not resolve.
- A work item that launches interactive or `--bg` `claude` (not `claude -p`) in a directory names
  the directory as a literal absolute path under a trusted ancestor.

## Short holds in the goal

The bench is not held from launch: `device: bench` does not add `device:bench` to the job's
resources. The claimant claims it per step. The goal tells the claimant the following:

- Claim `device:bench` before each step that uses the bench, and `build:<absolute path>` before each
  step that runs `bitbake`, `devtool` or `kas`. Release at the end of the step.
- The rules are in `<plugin-root>/skills/goal/short-holds.md`. The goal repeats none of
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

The skill never asks the user in this mode. It records each fork in `<job>/goal.md`.

- A fork whose options differ in something the user would see is one `- ` item under a heading spelled exactly `## Open`
  in `goal.md`. The item states the situation, the options, the consequence of each and a
  recommendation, on one line.
- The handoff's `## Open` items, a base left unresolved and a fork `config get` does not answer are
  such forks.
- A fork with no user-visible effect: record its recommended option under Settled as
  `(recommended)`. Do not list it under `## Open`.
- When the caller passes answers, each answered item moves under Settled with its answer. When no
  item is left, remove the `## Open` heading.

After `needs-input`, add the user's answers under Settled the same way. Then add one line under
Settled: "Run <n>: the questions of the earlier `needs-input` exit are answered above and closed;
continue from `<ledger path>`". Solo: "Run <n>: the questions of the earlier `needs-input` exit are
answered above and closed; earlier work is in the tree".

The line holds for both next steps: a resume of the kept session and a new run in a new session when
the old one is gone.

When a goal is extended after a `done` run, the new Settled line names the commits (`<base>..HEAD`) as the state. The ledger is deleted. In Light and Full it also names the retrospective when that file still exists. Solo has no retrospective.

At run time the worker takes the `needs-input:` exit for a question only the user can answer.

A job goal's Waiting line reads: "Waiting: never waits; takes the `needs-input:` exit."

## Template text

The worker sees only the goal file. Fill these slots when writing it: `<plugin-root>` with the
plugin root from `SKILL.md`, `<id>` with the job id.

The template's read-first line becomes:

```markdown
Before work item 1, read `<plugin-root>/skills/goal/rules.md` and follow it. Read it again after a
context compaction and before an exit.
```

When the goal claims short holds, the line also names `<plugin-root>/skills/goal/short-holds.md`.

Closing done-when item, after the template's last item:

```markdown
N+1. Reported: `<plugin-root>/bin/cure-job finish <id> --status done` exited 0 and the `notify:` line
   it printed was sent with `SendMessage`, or its error is shown. A `finish` that exits 1 with an error that names pr or
   retro is run again with the value fixed (not counted as a failure); exit 2: fix the arguments;
   any other non-zero exit is run once more.

Met when items 1-N are each demonstrated or listed in the shown `finish --unproven` with a reason
in the final message, and N+1 is demonstrated. Unproven only when the worker cannot obtain the
proof, never when its check ran and failed.
```

Exits, in the template's exits slot. Every tier carries the exit protocol:

```markdown
Every exit runs in this order: (1) `<plugin-root>/bin/cure-job finish <id> --status <status>`
(`<plugin-root>/bin/cure-job finish --help` lists the options; never write `result.md` yourself); (2) `SendMessage`
with the `notify:` line `finish` printed; (3) the final message. The `finish` command, its output
and the `SendMessage` or its error are in the transcript before the final message. The final message
restates each done-when item with its evidence. An item is unproven only when its proof is
unavailable (a device, a login, a manual check), never when its check ran and failed; give a reason
for each. Keep the goal file, the retrospective and the backlog; list the retrospective with
`--retro`. Never touch the job directory.

Also done when (a) <turns> turns have passed, or <rounds> rounds ended on a measured failure, or
<review cause>, or the diff passes <lines> lines (per repository, in <repo>: insertions plus deletions of `git diff --shortstat <base commit>`, plus the lines of untracked files (`git ls-files -z --others --exclude-standard | xargs -0 cat | wc -l`); the base commit is the one work item 1 recorded), or a consult's line estimate for a repository's files plus the lines already changed in it passes <lines> lines, or `git fetch` or
a tool check failed, or `finish` exited non-zero twice (not counting an exit 1 that names `--pr` or `--retro`), or a Settled statement is false or the
title's outcome is unachievable; and (b) the retrospective's summary, naming the cause, is in the
transcript and the `stats.md` row is appended with outcome `failed`; and (c) reported as in N+1 with `--status failed`, unless `finish` failed
twice as counted in (a); and (d) the final message starts with `failed:`.

Also done when a question only the user can answer is open, with no clean-up: the ledger and the
working files stay, the session stays alive, and `finish` runs with `--status needs-input`, one
`--question` per question and one `--kept` per kept file; the final message starts with
`needs-input:`. A resumed run reads Settled: when it holds an answer, the questions of the earlier
`needs-input:` exit are closed and the run continues from the ledger at the work item that stopped.
When it holds none, the final message starts with `no-answer:`, the run calls no `finish`, and the
run exits at once.
```

Cap `<lines>`: when the handoff's Settled has "Estimate: ~N changed lines", `<lines>` is 2 x N rounded up to 100. Without the line, set it as for any goal. Record the estimate under Settled in the goal.

Review cause: Light as in "Agent tier". Full, written whole: "a `MUST-FIX` or `SHOULD-CONSIDER` is
open after review round 3". When the handoff's `delivery` is `commit` (the default), the generated
text carries no pull-request wording.

The `lines` value of the `stats.md` row is measured the same way, per repository against its base
commit, and the row carries the estimate as `est_lines`. A cap against the branch name would count only uncommitted lines when the job commits on
`<base>` itself.

Clean-up work item: write "The failure and `needs-input` exits skip this item." in place of "The
failure path skips this item."

A Solo exit has (a) without `<rounds>` and `<review cause>`, then "(b) the `stats.md` row is appended
with outcome `failed`", the report clause as (c) and the final-message clause as (d).

## Launch line

Report the absolute path of `<job>/goal.md` and its `wc -c` count.
