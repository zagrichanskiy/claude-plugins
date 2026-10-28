# Goal rules

A goal file names this file in its Work section. Its Rules section names the tier. Follow "All
tiers", then "Light and Full" or "Solo". The exit clauses are in the goal file; this file does not
add one.

## All tiers

- Work item 1: run `git fetch`, then the fact check the item names. A false Settled statement, a
  failed fetch or a failed tool check is a failure cause. Base moved: base the work on
  `origin/<base>`. Other mismatch: record it, use the corrected value.
- Base taken from a predecessor job, or a Settled line "Base: the PR branch of split part 1": work item 1 compares `<base>` with the local branch, not with
  `origin/<base>`, because the predecessor commits locally and pushes nothing. A split part 1 branch that exists only on
  origin has no local branch: first run `git branch --track <base> origin/<base>`. When `origin/<base>`
  exists, it runs `git merge-base --is-ancestor origin/<base> <base>`. A failure is a failure
  cause. Never base the work on `origin/<base>` in this case: that drops the predecessor's commits.
  Any other base keeps the check above.
- Work item 1 records one base commit per repository, the commit the job started on: in the ledger,
  or in the transcript for Solo. For a branch that exists on run 1 (locally, else as
  `origin/<branch>`), it is `git -C <repo> rev-parse <branch>` (else `origin/<branch>`). Otherwise it
  is `git -C <repo> rev-parse <base>`, or `git -C <repo> rev-parse origin/<base>` when the base moved
  and the work is based on `origin/<base>`. The repositories of one job can have different bases.
  The size check, the changed-line cap in the failure exit, the stats row's `lines` and `cure:split`
  read this value.
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
- Branch: the goal names the job's branch as a literal name. A branch exists when it is local or on origin. A branch that does not exist on run 1 is
  not a mismatch of work item 1. The step after the fact check creates the branch from `<base>` in each
  repository with `git switch -c <branch> <base>`, or runs `git switch <branch>` when it exists locally (a run
  after `needs-input`), or `git switch -c <branch> --track origin/<branch>` when it exists only on
  origin. Never use `git switch -C`: it resets the branch and drops earlier commits. In
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
- Size check: after the last review round and the final commit, before the push, measure the diff
  per repository (as the failure exit states, from the base commit, the commit the job started on), against the repository's Estimate line in Settled ("Estimate: ~N changed
  lines", with "in <repo>" when the job has several). Skip the check when Settled has no estimate. The PR diff is the insertions plus deletions of `git diff --shortstat <base-ref>...<branch>`. `<base-ref>` is the local `<base>` when `<base>` is a predecessor's branch or Settled says "Base: the PR branch of split part 1"; else `origin/<base>` when it exists; else the local `<base>`. It reads committed refs only, never the working tree. When the diff of any repository passes `split.factor` ×
  its estimate: add a `Wn` row (why the diff grew) and a proposal (the fix to the rule or skill) to
  the job's retrospective file; the retrospective work item completes that file. Call `cure:split`
  only when the job has one repository, `<plugin-root>/bin/cure-job list --json` shows no job
  whose `after` is this job, and the PR diff passes the cap
  (`split.limit`; read it from the Settled line "Split cap", else from `<plugin-root>/bin/cure-job config get split.limit`); otherwise the `Wn` row names the unmet
  condition, the retrospective is written and the job delivers its single branch. The goal computes R = PR diff − cap. When R is larger than the job's own diff (insertions plus deletions of `git diff --shortstat <base commit>..HEAD`), the work items cannot reach R: the job skips `cure:split`, adds a `Wn` row that names this reason and delivers its single branch. The call passes the repository, the branch, the base ref, the base commit work item 1 recorded, the estimate, the delivery, the cap, R and the job's work items (each with its files and tests). `cure:split` cuts the PR diff into as many parts as the cap needs. Record the tip of `<branch>` before the call. The job does not stop at `split.factor` ×: it finishes its work first. The check asks the
  user nothing. What follows depends on `delivery`:
  - `pr`: the push and the pull requests are those of `cure:split`. When `cure:split` stops before
    it pushes `<branch>`, it has rolled `<branch>` back to the recorded tip (its section "Roll
    back"). The job checks that `git -C <repo> branch --show-current` prints `<branch>` and that
    `git -C <repo> rev-parse <branch>` prints the recorded tip. Then it pushes and opens its single
    PR as planned. A failed check or a failed rollback takes the failure exit, and the job pushes
    nothing. The report names any ticket `cure:split` created before it stopped. When `cure:split` pushed `<branch>` and then failed, the job takes the failure exit with
    `--pr` for each pull request opened, pushes nothing further, and names the work as left on the local stacked branches. The retrospective records why the split stopped. The report names any ticket
    `cure:split` already created.
  - `commit`: `cure:split` creates the stacked branches locally, with no ticket and no push, and the
    report names them. When it stops, the job runs the same two checks, then delivers its
    single branch. A failed check takes the failure exit.
  - `cure:split` stops at its check 4 (a part of the chain is still over the cap after one re-cut): it has changed no branch. The job adds a `Wn` row that names the overrun in changed lines and delivers its single branch.
  - After a successful split, the job re-runs each done-when check that a moved work item owns on the branch of the part that the split report
    maps the item to (`qa` for a test run). Such an item counts as delivered when the check passes there, and the final
    message names that branch as its evidence. A check on `<branch>` that fails only because the work
    moved is not a failure cause.
- Review fixes: once the PR exists, squash each fix into the job's latest commit
  (`git commit --amend --no-edit` with explicit paths). No separate fix commit. Amending a commit
  already pushed makes the next push `git push --force-with-lease`. The severity floor
  is unchanged: every `MUST-FIX` and `SHOULD-CONSIDER` is still fixed.
- Full: run `test-author` only for a behaviour change that has no test.
- Review round: one reviewer pass, the same unit for every tier. The goal states N, the round limit (N = `reviews.<tier>`). Round 1 reviews the diff. Rounds 2..N re-check only the fixes of the previous round and raise no new topic. The orchestrator commits each round's fixes, and `qa` re-runs, before the next round. A `MUST-FIX` or `SHOULD-CONSIDER` open after round N takes the failure exit; no round N+1 starts.
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
