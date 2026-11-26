# Goal rules

A goal file names this file in its Work section. Its Rules section names the tier. Follow "All
tiers", then "Light and Full" or "Solo". The exit clauses are in the goal file.

## All tiers

- Work item 1: run `git fetch`, then the fact check the item names. A false Settled statement, a
  failed fetch or a failed tool check is a failure cause. Base moved: base the work on
  `origin/<base>`. Other mismatch: record it, use the corrected value.
- Base from a predecessor job, or Settled "Base: the PR branch of split part 1": compare `<base>`
  with the local branch, not `origin/<base>`, because the predecessor commits locally and pushes
  nothing. In a workspace slot, `cure-job launch` copies the predecessor's local branches into the
  job's slot, so `<base>` is a local branch there. A part 1 branch that exists only on origin has no
  local branch: first run `git branch --track <base> origin/<base>`. When `origin/<base>` exists,
  run `git merge-base --is-ancestor origin/<base> <base>`; a failure is a failure cause. Never base
  the work on `origin/<base>` here: that drops the predecessor's commits. Any other base keeps the
  check above.
- Work item 1 records one base commit per repository, the commit the job started on, in the ledger
  (Solo: the transcript). For a branch that exists on run 1 (locally, else as `origin/<branch>`) it is
  `git -C <repo> rev-parse <branch>` (else `origin/<branch>`). Otherwise it is
  `git -C <repo> rev-parse <base>`, or `origin/<base>` when the base moved and the work is based on
  it. Repositories of one job can have different bases. The size check, the changed-line cap in the
  failure exit, the stats row's `lines` and `cure:split` read this value.
- Item 1 also records, per repository and where the base commit is recorded, a dirty-tree baseline:
  branch, HEAD, `git diff --shortstat` and the paths of `git -C <repo> status --porcelain`. The
  changed-line cap and the stats row's `lines` exclude those paths.
- A goal that pushes: item 1 runs `git -C <repo> log --oneline origin/<branch>..<branch>` when both
  refs exist, else skips the check. Commits of predecessor jobs on the chain are excluded. Each
  remaining commit is recorded where the base commit is. Whether to push it is a question at item 1,
  not at the push.
- Before a goal changes a rule in code that accepts or rejects input (a gate, a filter, a pattern
  list), item 1 runs the changed rule against the workspace it runs against, for example
  `repo forall -c 'git remote get-url origin'`, and records the output. A counter-example the rule
  misclassifies is a question.
- A job session works in its worktrees, `<worktree.root>/<repo name>/<job id>` for each repository of
  the handoff, and starts in the first. When the first repository is inside a `repo` tool workspace,
  the job works in a workspace slot instead, a copy of that workspace with its own checkouts and build
  directories, and starts in the slot copy of the first repository. A goal path that starts with
  `<slot>` is under the slot directory, the path of the `slot:` resource in the job's row of
  `cure-job list --json`. `cure-job launch` creates them and a resume reuses them. Every edit, build,
  `git -C` and done-when command uses the worktree or slot path. The repository path the handoff
  lists is the user's checkout: the job never edits it or switches its branch.
- Branch: the goal names the job's branch as a literal name. A branch exists when it is local or on
  origin. A branch missing on run 1 is not an item 1 mismatch. The step after the fact check (the
  orchestrator's in Light and Full, the session's in Solo) creates it in each repository with
  `git switch -c <branch> <base>`; with `git switch <branch>` when it exists locally (a run after
  `needs-input`); with `git switch -c <branch> --track origin/<branch>` when it exists only on origin.
  Never `git switch -C`: it resets the branch and drops commits. When `git switch` refuses a branch
  checked out in a finished job's worktree under `worktree.root`, run `git -C <that worktree> switch
  --detach` and switch again; in any other worktree (the user's checkout) it is a question at item 1.
- A choice that changes behaviour the user would see is a question, also when the goal file or its
  design source is silent or contradictory on it. Never decide it silently. A fork whose options
  differ in nothing the user would see takes the recommended option, recorded as an assumption. A
  mechanical choice that the code or conventions determine: decide it, scoping with `grep` first.
- Asking: with a `needs-input:` exit in the goal file, take it. Otherwise ask with `AskUserQuestion`
  and wait. Each question states the situation, the options, the consequence of each and a
  recommendation, for a reader who has not followed the run.
- Read with `gh issue view --json <fields>` or `gh pr view --json <fields>`. Edit with `gh api`, for
  example `gh api -X PATCH repos/{owner}/{repo}/pulls/<n> -f body=...`. `gh issue view` and
  `gh pr edit` without these fail on the Projects (classic) deprecation.
- Stage git changes with explicit paths; never `git add -A` or `git add .`.
- A command for the user to run with `!` is a script file, run as `! python3 <absolute path>`. Job
  session (the only one where `$CLAUDE_JOB_DIR` is set): the file is under `$CLAUDE_JOB_DIR/tmp`.
  Direct run: under `<repo>/.notes/tmp/`. Never give an inline `sed` with escapes.
- A tool call or an agent that gets an auto-mode "no verdict": ask the user to leave auto mode for the
  goal. The question starts with the fixed prefix `auto-mode no verdict:`. Never route the work
  through a copy, a patch or a shell write.
- Last step of every tier, Solo included: append one row to `~/.claude/retros/stats.md` with this
  command and its values filled in. A failed goal appends a row. A `needs-input` exit does not.
  Unknown value is `-`; approximate value is `~45`. `|` and `'` are stripped from every value (the
  command quotes each value in single quotes). `outcome` is `met` or `failed`.

  ```sh
  mkdir -p ~/.claude/retros
  (set -C; printf '%s\n' '| date | repo | slug | tier | outcome | est_lines | lines | turns | agent_tokens | rounds | title |' '|---|---|---|---|---|---|---|---|---|---|---|' > ~/.claude/retros/stats.md) 2>/dev/null
  grep -qF '| <date> | <repo> | <slug> |' ~/.claude/retros/stats.md || printf '%s\n' '| <date> | <repo> | <slug> | <tier> | <outcome> | <est_lines> | <lines> | <turns> | <agent_tokens> | <rounds> | <title> |' >> ~/.claude/retros/stats.md
  ```

- The row's `lines` is the changed-line cap count of the failure exit (untracked files included),
  largest repository. `agent_tokens` is the sum of the subagent token reports. `rounds` is the review
  rounds.
- Done when: `grep -cF '| <date> | <repo> | <slug> |' ~/.claude/retros/stats.md` prints `1`.

## Light and Full

- The main session orchestrates: it dispatches agents, keeps the ledger, checks completeness. It reads
  no source and edits no code.
- The orchestrator creates the branch and makes every commit, with explicit paths. It never asks
  `implementer`, `test-author` or `skill-author` to do either.
- An agent returns its questions in its report. The orchestrator puts a work item's questions in one
  round. Record a mechanical choice in the ledger as an assumption.
- An agent report that names a file it left untouched for a finding is a gap. Dispatch that edit
  before the commit.
- An empty or placeholder report is not a result. Verify the work from `git diff --stat` and the
  item's checks, and record the verification in the ledger.
- Mark a review finding fixed in the ledger only after `qa` confirms the fix.
- Record the turn count in the ledger after each work item.
- `git rm` run by a subagent stages the deletion, so the explicit-path `git add` of the removed path
  fails. Leave that path out of `git add`.
- Pass agents paths and ids. Ask for findings only.
- After a `designer` or `architect` consult, per repository, add the lines already changed (counted
  as the failure exit states) to the consult's line estimate for that repository's files. Compare
  each sum with `<lines>` before dispatching a writing agent. A sum over `<lines>` takes the failure
  exit.
- Size check: at the size-check work item, read `<plugin-root>/skills/goal/size-check.md` and follow
  it. Read it again after a compaction before the item ends.
- Review fixes: once the PR exists, squash each fix into the job's latest commit
  (`git commit --amend --no-edit` with explicit paths). No separate fix commit. After amending a
  pushed commit, the next push is `git push --force-with-lease`. Every `MUST-FIX` and
  `SHOULD-CONSIDER` is still fixed.
- Full: run `test-author` only for a behaviour change that has no test.
- Review round: one reviewer pass, the same unit for every tier. The goal states N, the round limit
  (N = `reviews.<tier>`). Round 1 reviews the diff. Rounds 2..N re-check only the previous round's
  fixes and raise no new topic. The orchestrator commits each round's fixes, and `qa` re-runs, before
  the next round. A `MUST-FIX` or `SHOULD-CONSIDER` open after round N takes the failure exit; no
  round N+1 starts. A work item with a fresh-reader check adds its passes to each round (`fresh-reader.md`).
  Every `NITPICK` and `enhancement` is fixed with the round's fixes. Those of the last round are
  fixed in one fix pass that `qa` and lint verify, with no further round. An item outside the
  ticket's files that would take the change past `<lines>` is a question to the user, asked as
  "Asking" states (`needs-input:` in a job, `AskUserQuestion` in a direct run), never a written note.
- Prose review: each round also dispatches the prose reviewer that the goal's Tools section names,
  on the prose of the diff: added or changed code comments, documents, the commit message and the PR
  text. Before round 1 the orchestrator drafts the commit message and the PR text under `.notes/` and
  passes their paths with the diff. Fixes to them follow the same round rules. The orchestrator makes
  or amends the commit with the reviewed message (`git commit -F <draft>`) and passes the reviewed PR
  text to the PR step (the PR skill or `gh pr create`). The prose reviewer's findings join the round
  like a reviewer's. In Full, the orchestrator passes the prose reviewer from the goal's Tools section
  when it runs `review-change`, which dispatches it. A goal whose Tools section names no prose
  reviewer has no prose review step.
- Prose severity: a finding that makes the text fail its reader (wrong, misleading, or forbidden by
  the repository's rules, such as a comment that narrates the implementation) is `MUST-FIX`. Content
  the reader does not need is `SHOULD-CONSIDER`. A finding on form only is `NITPICK`. A claim the
  reviewer cannot verify goes to the implementer to check; when it cannot be checked, it is a question.
- Fresh-reader check: a work item that names it follows `<plugin-root>/skills/goal/fresh-reader.md`.
  Read it again after a compaction before the item ends.
- When a failure cause holds: stop, write the retrospective with the cause and what is left, print its
  summary, append the `stats.md` row with outcome `failed`, keep the ledger, take the failure exit.
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
