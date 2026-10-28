# Goal rules

A goal file names this file in its Work section. Its Rules section names the tier. Follow "All
tiers", then "Light and Full" or "Solo". The exit clauses are in the goal file; this file does not
add one.

## All tiers

- Work item 1: run `git fetch`, then the fact check the item names. A false Settled statement, a
  failed fetch or a failed tool check is a failure cause. Base moved: base the work on
  `origin/<base>`. Other mismatch: record it, use the corrected value.
- Base taken from a predecessor job: work item 1 compares `<base>` with the local branch, not with
  `origin/<base>`, because the predecessor commits locally and pushes nothing. When `origin/<base>`
  exists, it runs `git merge-base --is-ancestor origin/<base> <base>`. A failure is a failure
  cause. Never base the work on `origin/<base>` in this case: that drops the predecessor's commits.
  Any other base keeps the check above.
- Work item 1 records `git -C <repo> rev-parse <base>` for each repository as that repository's base
  commit, or `git -C <repo> rev-parse origin/<base>` when the base moved and the work is based on
  `origin/<base>`: in the ledger, or in the transcript for Solo. The repositories of one job can have
  different bases.
- Work item 1 also records, per repository, a dirty-tree baseline: branch, HEAD,
  `git diff --shortstat` and the paths that `git -C <repo> status --porcelain` lists. It records them
  where the base commit is recorded. The changed-line cap in the failure exit and the stats row's
  `lines` exclude those paths.
- A goal that pushes: work item 1 runs `git -C <repo> log --oneline origin/<branch>..<branch>` when
  both refs exist, and skips the check otherwise. Commits of predecessor jobs on the chain are
  excluded. Each remaining commit is recorded where the base commit is recorded. Whether to push it is
  a question at work item 1, not at the push.
- Before a goal changes a rule in the code that accepts or rejects input (a gate, a filter, a pattern
  list), work item 1 runs the changed rule against the workspace it runs against, for example
  `repo forall -c 'git remote get-url origin'`, and records the output. A counter-example the changed
  rule misclassifies is a question.
- Branch: the goal names the job's branch as a literal name. A branch that does not exist on run 1 is
  not a mismatch of work item 1. The step after the fact check creates the branch from `<base>` in each
  repository with `git switch -c <branch> <base>`, or runs `git switch <branch>` when it exists (a run
  after `needs-input`). Never use `git switch -C`: it resets the branch and drops earlier commits. In
  Light and Full this step is the orchestrator's, in Solo the session's.
- A choice that changes behaviour the user would see is a question, also when the goal file or its
  design source is silent or contradictory on it. Never decide it silently.
- A fork whose options differ in nothing the user would see is not a question: take the recommended
  option and record it as an assumption.
- Asking: when the goal file has a `needs-input:` exit, take it. Otherwise ask with
  `AskUserQuestion` and wait.
- Each question states the situation, the options, the consequence of each and a recommendation,
  for a reader who has not followed the run.
- A mechanical choice that the code or conventions determine: decide it. Scope with `grep` first.
- Read with `gh issue view --json <fields>` or `gh pr view --json <fields>`. Edit with `gh api`, for
  example `gh api -X PATCH repos/{owner}/{repo}/pulls/<n> -f body=...`. `gh issue view` and
  `gh pr edit` without these fail on the Projects (classic) deprecation.
- Stage git changes with explicit paths; never `git add -A` or `git add .`.
- A command for the user to run with `!` is a script file, run as `! python3 <absolute path>`. In a
  background (job) session the file is under `$CLAUDE_JOB_DIR/tmp`, the only session where that
  variable is set. In a direct run the file is under `<repo>/.notes/tmp/`. Never give an inline `sed`
  with escapes.
- A tool call or an agent that gets an auto-mode "no verdict": ask the user to leave auto mode for
  the goal. The question starts with the fixed prefix `auto-mode no verdict:`. Never route the work
  through a copy, a patch or a shell write.
- Last step of every tier, Solo included: append one row to `~/.claude/retros/stats.md`, with this
  command and its values filled in. A failed goal appends a row. A `needs-input` exit does not.
  Unknown value is `-`; approximate value is `~45`. `|` and `'` are stripped from every value (the
  command quotes each value in single quotes). `outcome` is `met` or `failed`.

  ```sh
  mkdir -p ~/.claude/retros
  (set -C; printf '%s\n' '| date | repo | slug | tier | outcome | est_lines | lines | turns | agent_tokens | rounds | title |' '|---|---|---|---|---|---|---|---|---|---|---|' > ~/.claude/retros/stats.md) 2>/dev/null
  grep -qF '| <date> | <repo> | <slug> |' ~/.claude/retros/stats.md || printf '%s\n' '| <date> | <repo> | <slug> | <tier> | <outcome> | <est_lines> | <lines> | <turns> | <agent_tokens> | <rounds> | <title> |' >> ~/.claude/retros/stats.md
  ```

- The row's `lines` is the count of the failure exit's changed-line cap (untracked files included),
  largest repository. `agent_tokens` is the sum of the subagent token reports. `rounds` is the review rounds.
- Done when: `grep -cF '| <date> | <repo> | <slug> |' ~/.claude/retros/stats.md` prints `1`.

## Light and Full

- The main session orchestrates: it dispatches agents, keeps the ledger, checks completeness. It
  reads no source and edits no code.
- The orchestrator creates the branch and makes every commit, with explicit paths. It never asks
  `implementer`, `test-author` or `skill-author` to do either.
- An agent returns its questions in its report. The orchestrator puts a work item's questions in one
  round.
- Record a mechanical choice in the ledger as an assumption.
- An agent report that names a file it left untouched for a finding is a gap. Dispatch that edit before the commit.
- An empty or placeholder report is not a result. Verify the work from `git diff --stat` and the item's checks, and record the verification in the ledger.
- Mark a review finding fixed in the ledger only after `qa` confirms the fix.
- Record the turn count in the ledger after each work item.
- `git rm` run by a subagent stages the deletion, so the orchestrator's explicit-path `git add` of the removed path fails. Leave that path out of `git add`.
- Pass agents paths and ids. Ask for findings only.
- After a `designer` or `architect` consult, add the lines already changed, counted as the failure exit states, to the consult's line estimate. Run this per repository: the estimate for that repository's files plus the lines already changed in it. Compare each sum with `<lines>` before dispatching a writing agent. A sum over `<lines>` takes the failure exit.
- Full: run `test-author` only for a behaviour change that has no test.
- Light goal with one review round: the round includes one reviewer re-check of the fixes. It starts no second round. A `MUST-FIX` or `SHOULD-CONSIDER` that the re-check reports takes the failure exit; no further fix loop runs. A Light goal with two review rounds keeps its round-2 re-check as round 2.
- When a failure cause holds: stop, write the retrospective with the cause and what is left, print
  its summary, append the `stats.md` row with outcome `failed`, keep the ledger, take the failure
  exit.
- The retrospective is `~/.claude/retros/<date>-<repo>-<slug>.md` with these sections, in this order,
  and no others: Outcome (`met`, or `failed: <cause>, what is left`); "Where it went wrong" (one row
  per event, `W1…Wn`, each with its evidence); Proposed changes. No measurements: the `stats.md` row
  holds them. Proposed changes table header: `| Target | Change | Evidence (Wn) | Expected effect |`.
  A proposal with no `Wn` evidence is not made. Target forms: `<plugin>:<path>` (a file in a plugin,
  for example `cure:skills/goal/rules.md`), `repo:<path>` (a file in the goal's own repository),
  `user:CLAUDE.md` (the user's global instructions).

## Solo

- The session does the task itself. It starts no subagent, holds no review round, writes no
  retrospective, and runs the done-when checks.
- Questions are the session's own (asked or exited per mode). Assumptions are recorded in the final
  message.
- When a failure cause holds: stop, keep the working files, append the `stats.md` row with outcome
  `failed`, take the failure exit.
