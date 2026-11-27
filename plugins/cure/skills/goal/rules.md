# Goal rules

A goal file names this file in its Work section. Its Rules section names the tier. Follow "All
tiers", then "Light and Full" or "Solo". The exit clauses are in the goal file.

## All tiers

- Work item 1: run `git fetch`, then the fact check the item names. A failed fetch or a failed tool
  check is a failure cause. Base moved: base the work on `origin/<base>`. Other mismatch in ticket,
  branch or base commit that Settled does not state: record it, use the corrected value.
- Work item 1 checks every Settled fact (a decision is not checked) against the branch the work
  runs on (the job worktree or slot when the job has one, else the launch checkout). It records each
  command and its output in the ledger (Solo: the transcript):
  - a fact copied from a note: check it against the source the note cites, not the note;
  - paths and symbols: `git ls-tree <base> <path>` or `git show <base>:<path>`;
  - refs: `git rev-parse --verify <ref>`; checkout branches:
    `git -C <checkout the statement names> branch --show-current`;
  - PR state and base: `gh pr view`;
  - device facts: `MACHINE` from `/etc/build` and the value read on the device;
  - the test command runs once on the base.
- Work item 1 runs each done-when check on the base. It must fail there. A check marked "holds on the
  base" in the goal keeps the mark on its ledger line (Solo: the transcript). An unmarked check that
  passes on the base is a question before any change.
- A Settled fact found false is a question before any change: the `needs-input:` exit in a job,
  otherwise as "Asking" states.
- Base from a predecessor job, or Settled "Base: the PR branch of split part 1": compare `<base>`
  with the local branch, not `origin/<base>`, because the predecessor commits locally and pushes
  nothing. In a workspace slot, `cure-job launch` copies the predecessor's local branches into the
  job's slot, so `<base>` is a local branch there. A part 1 branch that exists only on origin has no
  local branch: first have `delivery` (Solo: the session) run the `track` brief,
  `git branch --track <base> origin/<base>`. When `origin/<base>` exists,
  run `git merge-base --is-ancestor origin/<base> <base>`; a failure is a failure cause. Never base
  the work on `origin/<base>` here: that drops the predecessor's commits. Any other base keeps the
  check above.
- Work item 1 records one base commit per repository, the commit the job started on, in the ledger
  (Solo: the transcript). For a branch that exists on run 1 (locally, else as `origin/<branch>`) it is
  `git -C <repo> rev-parse <branch>` (else `origin/<branch>`). Otherwise it is
  `git -C <repo> rev-parse <base>`, or `origin/<base>` when the base moved and the work is based on
  it. Repositories of one job can have different bases. The size check, the changed-line cap in the
  failure exit and `cure:split` read this value.
- Item 1 also records, per repository and where the base commit is recorded, a dirty-tree baseline:
  branch, HEAD, `git diff --shortstat` and the paths of `git -C <repo> status --porcelain`. The
  changed-line cap excludes those paths.
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
  origin. A branch missing on run 1 is not an item 1 mismatch. The step after the fact check
  (`delivery` with the `branch` brief in Light and Full, the session in Solo) creates it in each
  repository with `git switch -c <branch> <base>`; with `git switch <branch>` when it exists
  locally (a run after `needs-input`); with `git switch -c <branch> --track origin/<branch>` when
  it exists only on origin. Never `git switch -C`: it resets the branch and drops commits. When
  `git switch` refuses a branch checked out in a finished job's worktree under `worktree.root`,
  `delivery` (Solo: the session) runs `git -C <that worktree> switch --detach` and switches
  again. The brief passes `worktree.root` and the finished jobs' worktree paths. In any other
  worktree (the user's checkout) it is a question at item 1.
- A choice that changes behaviour the user would see is a question, also when the goal file or its
  design source is silent or contradictory on it. Never decide it silently. A fork whose options
  differ in nothing the user would see takes the recommended option, recorded as an assumption. A
  mechanical choice that the code or conventions determine: decide it, scoping with `grep` first.
- Asking: with a `needs-input:` exit in the goal file, take it. Otherwise ask with `AskUserQuestion`
  and wait. Each question states the situation, the options, the consequence of each and a
  recommendation, for a reader who has not followed the run.
- Read with `gh issue view --json <fields>` or `gh pr view --json <fields>`. Edit with `gh api`, for
  example `gh api -X PATCH repos/{owner}/{repo}/pulls/<n> -F body=@<file>`; in Light and Full
  `delivery` runs it with the `pr-edit` brief. Only a pull request is edited this way. An issue,
  its body included, is written by `tracker` (`field` brief). `gh issue view` and
  `gh pr edit` without these fail on the Projects (classic) deprecation.
- Stage git changes with explicit paths; never `git add -A` or `git add .`.
- A command for the user to run with `!` is a script file, run as `! python3 <absolute path>`. Job
  session (the only one where `$CLAUDE_JOB_DIR` is set): the file is under `$CLAUDE_JOB_DIR/tmp`.
  Direct run: under `<repo>/.notes/tmp/`. Never give an inline `sed` with escapes.
- A tool call or an agent that gets an auto-mode "no verdict": ask the user to leave auto mode for the
  goal. The question starts with the fixed prefix `auto-mode no verdict:`. Never route the work
  through a copy, a patch or a shell write.

## Light and Full

- The main session orchestrates: it dispatches agents, keeps the ledger, checks completeness. It reads
  no source and edits no code.
- The orchestrator dispatches `delivery` for every git write and pull request: branch creation, commit,
  amend, push and PR, with explicit paths. It keeps read-only git (for example `status`, `diff`,
  `log`, `show`, `rev-parse`, `merge-base`, `ls-tree`, `fetch`) and `gh` reads. It never asks
  `implementer`, `test-author` or `skill-author` to write to git.
- The orchestrator dispatches `tracker` for every tracker read, write and transition, on GitHub
  issues too, and for each tracker step of the PR skill. No other agent of a job has a tracker tool.
- Ticket status, each step a `tracker` `transition` brief carrying the generic status name. A run
  whose goal names no ticket skips these steps.
  - Before the first change: In progress, assigned to the tracker's signed-in user.
  - After the `tracker` `field` write that links the PRs, or, when that write is not run, after the
    run's push with every PR linked, in every run: In review, assignee unchanged.
  - When a run starts on a branch that already has an open PR of its ticket: In progress, assigned
    to the signed-in user.
  - A transition whose status `tracker` reports as `skipped: no status named` is recorded in the
    ledger and the run continues.
  - A ticket already in the target status, or already assigned to that user, is left as it is.
  - A failed transition, or a question from one, does not fail the job and goes to no question
    round. The ledger and the final message name it.
- An agent returns its questions in its report. The orchestrator puts a work item's questions in one
  round. Record a mechanical choice in the ledger as an assumption.
- An agent report that names a file it left untouched for a finding is a gap. Dispatch that edit
  before the commit.
- An empty or placeholder report is not a result. Verify the work from `git diff --stat` and the
  item's checks, and record the verification in the ledger.
- Mark a review finding fixed in the ledger only after `qa` confirms the fix.
- Record the turn count in the ledger after each work item.
- Pass `delivery` every deleted path with the commit brief. Leave a path out only when `git status`
  shows its deletion already staged.
- Pass agents paths and ids. Ask for findings only.
- After every writing agent, count the changed lines per repository as the failure exit states (it
  includes untracked files and uses the base commit item 1 recorded for that repository), and
  record each count in the ledger. Each brief to a writing agent states its line budget: the work
  item's share of the estimate, capped at `<lines>` minus the lines already changed in that
  repository. An agent that would exceed its budget stops and reports. The test-author's budget is
  the test estimate of `sizing.md`.
- After a `designer` or `architect` consult, per repository, add the lines already changed (counted
  as the failure exit states) to the consult's raw line estimate for that repository's files. Compare
  each sum with `<lines>` before dispatching a writing agent. A sum over `<lines>` takes the failure
  exit.
- Size check: at the size-check work item, read `<plugin-root>/skills/goal/size-check.md` and follow
  it. Read it again after a compaction before the item ends.
- Review fixes: once the PR exists, squash each fix into the job's latest commit
  (the orchestrator has `delivery` run the `amend` brief with explicit paths). No separate fix
  commit. After amending a pushed commit, the next push uses the `push` brief with
  `--force-with-lease`. Every `MUST-FIX` and `SHOULD-CONSIDER` is still fixed.
- Full: run `test-author` only for a behaviour change that has no test.
- Review round: one reviewer pass, the same unit for every tier. The goal states N, the round limit
  (N = `reviews.<tier>`). Round 1 reviews the diff. Rounds 2..N, the fresh reader included, re-check
  only the previous round's fixes and findings. A new finding is one that is neither a finding of
  the previous round nor on a line that round's fixes changed. It is raised only when it is a
  behaviour defect (a bug), and the job fixes it. The orchestrator drops any other new finding of
  rounds 2..N; there is no backlog. Every reviewer brief of rounds 2..N, the Light reviewer's
  included, carries the line
  `Round: re-check; raise a new finding only when it is a behaviour defect`.
  `delivery` commits each round's fixes, and `qa` re-runs, before the next round. A `MUST-FIX`
  or `SHOULD-CONSIDER` open after round N takes the failure exit; no round N+1 starts. A work item
  with a fresh-reader check adds its passes to each round (`fresh-reader.md`).
  Every `NITPICK` and `enhancement` is fixed with the round's fixes. Those of the last round are
  fixed in one fix pass that `qa` and lint verify, with no further round. An item outside the
  ticket's files that would take the change past `<lines>` is a question to the user, asked as
  "Asking" states (`needs-input:` in a job, `AskUserQuestion` in a direct run), never a written note.
- Review brief: every review brief except the fresh reader's lists the Settled decisions as decided
  and tells the reviewer not to raise them.
- Fix brief: it carries the finding and its scenario, not the reviewer's text, and a grep of the
  changed fact's key terms over the document set and its siblings. The fixer changes only the words
  the finding names and their copies among the grep hits (a hit that states the same fact), reports
  any other hit, and checks the result against the code.
- Prose review: each round also dispatches the prose reviewer that the goal's Tools section names,
  on the prose of the diff: added or changed code comments, documents, the commit message and the PR
  text. Before round 1 the orchestrator drafts the commit message and the PR text under `.notes/` and
  passes their paths with the diff. Fixes to them follow the same round rules. `delivery` makes
  or amends the commit with the reviewed message (`commit -F <draft>`) and passes the reviewed PR
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
  summary, keep the ledger, take the failure exit.
- The retrospective is `~/.claude/retros/<date>-<repo>-<slug>.md` with these sections, in this order,
  and no others: Outcome (`met`, or `failed: <cause>, what is left`); "Where it went wrong" (one row
  per event, `W1…Wn`, each with its evidence); Proposed changes. No measurements: `cure-job finish`
  records a job's measurements (`cure-job stats`); a direct run records none. Proposed changes table
  header: `| Target | Change | Evidence (Wn) | Expected effect |`.
  A proposal with no `Wn` evidence is not made. Target forms: `<plugin>:<path>` (a file in a plugin,
  for example `cure:skills/goal/rules.md`), `repo:<path>` (a file in the goal's own repository),
  `user:CLAUDE.md` (the user's global instructions).

## Solo

- The session does the task itself. It starts no subagent, holds no review round, writes no
  retrospective, and runs the done-when checks.
- Questions are the session's own (asked or exited per mode). Assumptions are recorded in the final
  message.
- When a failure cause holds: stop, keep the working files, take the failure exit.
