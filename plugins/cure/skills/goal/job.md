# Job run

The caller invokes the skill with a handoff file and a job directory. The skill never asks the user
in this mode.

## Input

- The job directory is the handoff's directory. The job id is that directory's name.
- Read the handoff file as the conversation.
- Read the `CLAUDE.md` files and the `.claude/` of each repository in `repos`. The `CLAUDE.md` files
  are the repository's own and each ancestor directory's up to `$HOME`.
- Read `handoff.delivery`, `handoff.branch`, `handoff.resource-risk`, `split.limit`, `split.factor` and `worktree.root`
  with `cure-job config get <key>` before writing the goal. Each prints JSON. Never read
  `${CURE_JOB_CONFIG:-${XDG_CONFIG_HOME:-~/.config}/cure/config.json}` itself. Do not ask a fork a
  value answers; mark that decision `(default)` under Settled.
- Branch: when the handoff omits `branch`, apply `handoff.branch` (default `new`). A job with `after`
  and no `branch` uses its predecessor's branch, as `base` does (see "Base per repository");
  `handoff.branch` does not apply. The exception is a handoff whose Settled has `Stacked on <id>:
  overlapping files`: `handoff.branch` applies. `new` gives the job its own branch from `base`: write
  the literal name `<ticket>_<slug>` (`<slug>` without a ticket; a GitHub ticket `#N` is `issue-<N>`),
  the same in every repository. `current` works as `new`, from the base the next bullet sets. Any
  other value is a literal name. Write the resolved name in the goal, never `new` or `current`.
- Base of a job without `after`: the `base` the handoff states. Otherwise, under `current`, the branch
  checked out in the user's checkout of each repository. Otherwise the default branch of each
  repository in `repos`: `git -C <repo> symbolic-ref --short refs/remotes/origin/HEAD` (strip the
  `origin/` prefix), else `gh repo view --json defaultBranchRef -q .defaultBranchRef.name` run in the
  repository. When both fail, write the base as an `## Open` item. A job with `after` follows "Base
  per repository".
- Take the repository's build, implement, review and verify agents, its prose reviewer and its PR
  skill from the handoff's `## Tools` section. When the handoff names no prose reviewer, look for one
  in those `CLAUDE.md` files and `.claude/`.
- Copy each `Resource risk:` line of the handoff's Settled into the goal's Settled verbatim. Copy
  each `handoff.resource-risk` entry whose scope matches into Settled as its `text`, marked
  `(default)`, unless the handoff states a risk for the same resource. A scope `all` matches every
  job. A scope `device: <name>` matches a handoff whose `device` value is `<name>`. A scope `repo: <path>` matches a handoff whose `repos` lists `<path>`. Never shorten
  or drop these lines to save characters.
- Copy the handoff's Settled line "Base: the PR branch of split part 1" into the goal's Settled verbatim. `rules.md` keys the base check on it.
- A handoff with `device: bench` declares bench use. The goal must carry the short-hold claim and
  release (below).

## Base per repository

When the job's row in `cure-job list --json` has `after`, read
`<plugin-root>/skills/goal/base-chain.md` and follow it. Without `after`, see Input.

## Writing the goal

- The job works in one worktree per repository, `<worktree.root>/<repo name>/<job id>`, where
  `<repo name>` is the basename of `git -C <repo> rev-parse --show-toplevel`. Write each path of the
  goal and each done-when command with the worktree path, expanded to an absolute path without `~`,
  or `git -C <worktree>`, never the repository path the handoff lists. The worker starts in the worktree of the first repository.
- When the handoff's first repository is inside a `repo` tool workspace (the nearest ancestor that
  holds `.repo/`), the job works in a workspace slot instead, which `cure-job launch` picks. Write
  each path under that workspace as `<slot>/<path relative to the workspace root>`, with the literal
  `<slot>`, in each path, done-when command, `git -C` and build claim (`build:<slot>/<build dir>`).
  The worker starts in the slot copy of the first repository.
- A work item that launches interactive or `--bg` `claude` (not `claude -p`) in a directory names
  the directory as a literal absolute path under a trusted ancestor.

## Short holds in the goal

`device: bench` does not add `device:bench` to the job's resources. The goal tells the claimant:

- Claim `device:bench` before each step that uses the bench, and `build:<absolute path>` before each
  step that runs `bitbake`, `devtool` or `kas`. Release at the end of the step.
- The rules are in `<plugin-root>/skills/goal/short-holds.md`. The goal repeats none of them and
  names the build directory of each build step.
- Verify steps that use the bench carry their own claim and release in the work items.

## Where it goes

| File | Path |
|---|---|
| Goal | `<job>/goal.md`. The `.notes/` exclusion is skipped for it. |
| Ledger | `.notes/ledger-<slug>.md` in the worktree or slot copy of the handoff's first repository |

A Solo goal has no ledger. Apply the `.notes/` exclusion for the ledger, as the `note` skill
describes. The goal never deletes the job directory.

## Questions

Record each fork in `<job>/goal.md`.

- A fork whose options differ in something the user would see is one `- ` item under a heading spelled exactly `## Open`
  in `goal.md`. The item states the situation, the options, the consequence of each and a
  recommendation, for a reader who has not followed the run, on one line.
- The handoff's `## Open` items, a base left unresolved and a fork `config get` does not answer are
  such forks.
- A fork that a policy in `${XDG_CONFIG_HOME:-~/.config}/cure/question-policies.md` covers: record
  the policy's `Do` under Settled as `(policy)`. Do not list it under `## Open`.
- A fork with no user-visible effect: record its recommended option under Settled as
  `(recommended)`. Do not list it under `## Open`.
- When the caller passes answers, each answered item moves under Settled with its answer. When no
  item is left, remove the `## Open` heading.

After `needs-input`, add the user's answers under Settled the same way. Then add one line under
Settled: "Run <n>: the questions of the earlier `needs-input` exit are answered above and closed;
continue from `<ledger path>`". Solo: "Run <n>: the questions of the earlier `needs-input` exit are
answered above and closed; earlier work is in the tree".

The line holds for a resume of the kept session and for a new run in a new session.

When a goal is extended after a `done` run, the new Settled line names the commits (`<base>..HEAD`) as the state. The ledger is deleted. In Light and Full it also names the retrospective when that file still exists. Solo has no retrospective.

At run time the worker takes the `needs-input:` exit for a question only the user can answer.

A job goal's Waiting line reads: "Waiting: never waits; takes the `needs-input:` exit."

## Template text

Fill `<plugin-root>` with the plugin root from `SKILL.md` and `<id>` with the job id.

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
restates each done-when item with its evidence (after a split, an item a moved work item owns has the branch of its part as its evidence, as `size-check.md` states). An item is unproven only when its proof is
unavailable (a device, a login, a manual check), never when its check ran and failed; give a reason
for each. Keep the goal file and the retrospective; list the retrospective with
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

Cap `<lines>`: when the handoff's Settled has "Estimate: ~N changed lines", `<lines>` is 2 x N (the largest N, when the job has several Estimate lines) rounded up to 100. Without the line, set it as for any goal. Record the estimate under Settled in the goal. Record the effective `delivery` under Settled too; the size check passes it to `cure:split`.

Review cause: `delegation.md` "Agent tier", except Full, written whole: "a `MUST-FIX` or
`SHOULD-CONSIDER` is open after review round <limit>" (limit = `reviews.Full`). When the handoff's
`delivery` is `commit` (the default), the generated text carries no pull-request wording.

The `lines` value of the `stats.md` row is measured the same way, per repository against its base
commit, and the row carries the estimate as `est_lines`.

Clean-up work item: write "The failure and `needs-input` exits skip this item." in place of "The
failure path skips this item."

A Solo exit has (a) without `<rounds>` and `<review cause>`, then "(b) the `stats.md` row is appended
with outcome `failed`", the report clause as (c) and the final-message clause as (d).

## Launch line

Report the absolute path of `<job>/goal.md` and its `wc -c` count.
