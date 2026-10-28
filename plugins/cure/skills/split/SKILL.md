---
name: split
description: Split a finished branch into a chain of parts, each at or under the cap, that build and pass their tests, so each moved part is its own ticket and pull request. Plans the whole chain on scratch branches, tests and reviews every part there, then builds the branch and the stacked branches once, and under `delivery: pr` creates the tickets, pushes the chain and opens the pull requests. Git, tickets and tests run through the `delivery`, `tracker` and `qa` agents. Use when a job's diff passed `split.factor` times its estimate and the PR diff passed the cap `split.limit` × `split.factor` (called by `cure:goal` before the push), or when the user says "split this branch", "split this PR", or "/cure:split".
allowed-tools: Read, Grep, Glob, Bash, Agent
---

# Split

A branch grew past its cap. This skill makes a chain of parts. Part 1 is `<branch>` with the moved
work removed. Parts 2 to n are stacked branches, each on the one before, each with its own ticket and
pull request. Every part is at or under the cap. The skill holds the plan and a ledger; the agents
of section "Executors" run git, the tickets and the tests and return short reports. It asks the user
nothing. It decides a fork by the recommended option and lists the decision in the report.

Plugin root: `${CLAUDE_PLUGIN_ROOT}`. Write its value in place of `<plugin-root>` in every command
below.

## Inputs

| Input | Meaning |
|---|---|
| Repository | Absolute git toplevel. One repository is split per run. Sibling and companion PRs in other repositories are handled as sections "Preflight" and "Plan the chain" say. |
| Branch | The branch to split. |
| Base | The branch the pull request targets (`<base>`), the ref the work was based on (`<base-ref>`: the local `<base>` when `<base>` is a predecessor's branch or the job's Settled says "Base: the PR branch of split part 1"; else `origin/<base>` when it exists; else the local `<base>`), and the base commit the caller recorded (`<base-commit>`). Without a base commit: `git merge-base <base-ref> <branch>`. |
| Estimate | The estimated changed lines of the task. The report compares the diff with it. |
| Cap | `split.limit` × `split.factor`, in changed lines (default 800 × 1.5 = 1200). In a job, the caller passes the value from Settled. Without one: `<plugin-root>/bin/cure-job config get split.limit` and `split.factor`. |
| R | The required move: the PR diff before the split minus the cap, in changed lines. In a job, the caller passes it. By hand: measure the PR diff (below) and subtract the cap. R is the trigger guard only; section "Plan the chain" decides what moves. |
| Ticket | In a job, the handoff `ticket`. By hand, the ticket parsed from the branch name or given by the user. `<orig>` is its id (`<N>` of a GitHub `#N`, or the Jira key). The ticket form picks the tracker: `#N`, `owner/repo#N` or a github.com URL is GitHub, `KEY-N` is Jira. `split.tracker` applies only with no ticket; then the Jira project comes from the task context. `<ticket-repo>` is the repository the ticket names, else the remote; it is the `--repo` of every command on `<orig>`. With no ticket, the rewrite and the link are skipped. |
| Items | The packing units: the job's work items, each with its files and tests (from `git diff --stat`). By hand, the features of the diff that the user names or the diff shows. |
| Rewrite | By hand only: `yes` or `no` (default `no`). `yes` allows a re-cut across commit boundaries and `--force-with-lease` on an unmerged pull request branch, in section "Publish" only. A job never rewrites a published branch. |
| Delivery | `pr` or `commit`, as the caller passes it (the job's handoff `delivery`). Without one, as when run by hand: `<plugin-root>/bin/cure-job config get handoff.delivery` (default `commit`). |

PR diff: the insertions plus deletions of `git diff --shortstat <base-ref>...<branch>`. It reads committed refs only, never the working tree.

Read a missing input from the context: the current branch from `git -C <repo> rev-parse --abbrev-ref HEAD`,
the base from the job's `base` or `gh pr view --repo <owner/repo> --json baseRefName`. Without a repository, a branch or the
items, stop and name the missing input.

| Delivery | Result |
|---|---|
| `pr` | Tickets, stacked branches, push and the pull requests of every part. |
| `commit` | The stacked branches exist locally. No ticket, no push, no pull request, no `gh` command. The report names them. |

## Executors

The session reads no diff, Jira payload or test log. It keeps a ledger: the plan table, the old tip,
the step 2 record, the version paths, the tip of every branch the run creates, the ticket ids and the
saved-body path. It passes the values a brief needs in the brief, because each dispatch starts a new
agent. Each agent returns a short report.

| Work | Agent | Report |
|---|---|---|
| Edit files | `implementer` | Files changed. |
| Branches, commits, bumps, part sizes, tree checks, clone, push, pull requests, roll back | `delivery` | Branch names and tips, part sizes, tree hashes, URLs. |
| Check the tracker, create, copy and link tickets, rewrite the original | `tracker` | Capability, ticket ids, the path of the saved original body, manual steps. |
| Run the tests of a part | `qa` | Counts and the failing names. |
| Review | `reviewer` | Findings. |

A run is in a job when the size check of `skills/goal/rules.md` calls the skill. Before each `qa`
dispatch, the session (or the job's orchestrator) runs `git switch <part branch>`; the dispatch carries the test command, the
expected result and the short-hold claim when the goal claims. Pass paths, not file text. Briefs and
their inputs: `agents/delivery.md` and `agents/tracker.md`.

## Steps

| # | Step |
|---|---|
| 1 | Preflight (section "Preflight"). A failure stops the skill with nothing changed. |
| 2 | Record the old tip (`git -C <repo> rev-parse <branch>`) and the paths that `git -C <repo> status --porcelain` lists. |
| 3 | Plan the chain: cut, build and measure every part on scratch branches `split-tmp/<k>` (section "Plan the chain"). No branch of the user changes in steps 3 to 5. |
| 4 | Test every scratch part, review part 1 and run the fix loop (section "Tests"). |
| 5 | `pr` only: create the tickets (section "Tickets"). Their ids fix the final branch names and messages. |
| 6 | Apply: build `<branch>` and the stacked branches once, with final names (section "Build the chain"). |
| 7 | `pr` only: push the chain, open the pull requests, link the tickets (sections "Publish" and "Tickets"). |
| 8 | `git switch <branch>`, then report (section "Report"). |

Every exit leaves `<branch>` checked out. Stage with explicit paths; never `git add -A` or `git add .`.

## Preflight

Under `delivery: pr` check the tracker before any change, so that no step leaves a ticket or a
branch without the other. The tracker comes from the ticket form (section "Inputs"), else `split.tracker`
(`<plugin-root>/bin/cure-job config get split.tracker`, default `github`). Dispatch `tracker` with the brief `check`: it reports
`github: ok | no-auth | issues-disabled` and `jira: mcp | command | none`. `none`, `no-auth` or `issues-disabled` for the chosen tracker stops the skill.
Under `pr` also dispatch `delivery` with the brief `preflight`: it lists the sibling pull requests and the delivery requirements.

A failed check stops the skill with nothing changed. The report names the check. The skill also stops with nothing changed when `git branch --show-current` is not `<branch>`, or when `git status --porcelain` lists a staged entry, or lists a path that is in `git diff --name-only --no-renames <base-commit> <branch>` or in the files of any item. The skill never
logs in and never reads or stores a token.

## Plan the chain

Cut the whole PR diff (`git diff --numstat <base-ref>...<old-tip>`) into parts by the split rule of
`skills/dispatch/SKILL.md` section "Estimate and split", with part 1 = `<branch>`. Items are the packing units. Each part is a row.

| Column | Content |
|---|---|
| Part | k = 1 to n; part 1 is `<branch>`, part k is a stacked branch named `<slug>` (2-4 words of the part; `<tid>_<slug>` under `pr`). |
| Items | Whole items, tests with their code. |
| Delivery requirements | What the repository's PR skill or `CLAUDE.md` demands per pull request: version bump, companion PRs, CI group tag. `preflight` reports them with the version paths. A companion in another repository is built only when it is the run's repository or listed in `repos`; otherwise it is a manual step in the report. |
| Sibling PRs | Each pull request `preflight` found on `<branch>` in another repository: assigned to a part, or the reason it stays. |
| Planned lines | Items plus the bump lines of the part. |

First the implementer answers Seam checks 2 and 3 for the plan; a "no" stops the skill with nothing changed.
Then, for k = 1 to n: `delivery` `scratch <k>` creates `split-tmp/<k>` and leaves it checked out; the
`implementer` edits it (part 1: the removal of every later part; part k: the cut of each file that parts k and later edit, the last part to edit a file takes it whole);
`delivery` `commit <k>` commits one commit and measures the part, `git diff --shortstat <previous part>...<part>` (the previous part of part 1 is `<base-ref>`). After the last part it checks the tree against the old tip.
The session compares each size with the cap. Every part is measured, not only `<branch>`.

| State | Action |
|---|---|
| Every part at or under the cap | Go to step 4. |
| A part over the cap, first time | Re-cut once: move the last whole item of the part to the next part, or cut one feature by layer. Delete the scratch branches and rebuild them. |
| A part over the cap after the re-cut, or one unit over the cap that cannot be cut (a caller left without its callee, tests that cannot move) | Stop with `<branch>` unchanged. `delivery` deletes the scratch branches. A job adds a `Wn` row that names the overrun and delivers its single branch. |

## Seam

Each part is a seam when checks 1 to 3 hold. Check 4 is the cap check, made in section "Plan the chain".

1. Every part builds and passes its tests. Step 4 proves it.
2. No file that stays in an earlier part calls something only a later part defines.
3. The tests of a feature move with its code.
4. Every part has a PR diff at or under the cap (the measure "PR diff" defined under Inputs, taken from the previous part). A part over the cap after one re-cut stops the split with `<branch>` unchanged.

Checks 2 and 3 need source reading. The orchestrator of a job reads no source, so the brief of the
`implementer` carries them: it answers yes or no for each, with the file names that
fail, before it edits a file. A "no" stops the skill with nothing changed. The answer comes before `scratch 1`, so no scratch branch exists.

## Tests

Run the tests as the repository's CI or its recipe test task runs them (a wrapper, a daemon, an emulator), not only the bare command of `CLAUDE.md`. `qa` gets this as its test-environment brief.
Test `split-tmp/1`, then each later scratch part, in order. The pass on part 1 proves seam check 1.

| Result | Action |
|---|---|
| A part fails | `delivery` `old-tip clone` creates a clone, `qa` runs the same tests there, then `delivery` removes the clone. A failure there too is environment: report it, no roll back, no seam verdict. Otherwise run once more; a second failure rolls back, stops and reports. |
| All parts pass | Dispatch the `reviewer` on `git diff <old-tip> split-tmp/1`. Its brief adds checks 2 and 3 of section "Seam". A failed check is a MUST-FIX. |
| MUST-FIX or SHOULD-CONSIDER on a reference the removal exposes (comment, doc, name) | Fix loop of at most 2 rounds. `delivery` `fix <k>` checks out the part (`open`). The `implementer` edits it. `delivery` `fix <k>` (`amend`) amends the paths into the part's single commit. `delivery` `restack` rebases the later scratch parts onto it. `qa` re-tests the changed parts and `reviewer` checks again. When a finding is still open after the loop, roll back, stop and report. |
| A restack conflict, or a failed tree check after a fix | No roll back for a reference fix. On a conflict, `restack` resolves it inside the rebase and continues; a conflict on any other path aborts the rebase and is reported. After a failed tree check no rebase is in progress, so nothing is aborted. The `implementer` restores the old-tip text of each file the fix touched (`git checkout <old-tip> -- <path>`) in the part that receives the restored file, the part that brings the referenced scope back, so the last part equals the old tip again. `delivery` wraps the restore in `fix <j>` `open` and `amend` for that part j. Then `restack` from the part after j, given the plan rows (the paths each part takes whole or cuts). An aborted restack ends the fix loop and rolls back before the ticket step. A second failure counts as a round of the loop. |
| Any other MUST-FIX or SHOULD-CONSIDER | Roll back, stop and report. |

## Build the chain

`delivery` `apply` makes the user's branches once, from the scratch branches, with the final names and messages. It deletes the scratch branches.

| Latest commit of `<branch>` | Part 1 |
|---|---|
| Unpublished (`git log origin/<branch>..<branch>` lists it; every commit is unpublished when `origin/<branch>` does not exist) | `git commit --amend --no-edit` with the tree of `split-tmp/1`. The removal joins that commit. |
| Published, Rewrite `no` or a job | A new commit "Move <items> to their own branches". No history rewrite, no force push. |
| Published, Rewrite `yes`, pull request unmerged | One squashed commit with the tree of `split-tmp/1`. Pushed in section "Publish". |

Each stacked branch is created from the previous part with the commit of its scratch branch, committed with its final message (`<ticket>: <part as one sentence>` under `pr`, else the sentence; the message names no split).
`apply` then checks that each stacked tree equals its scratch tree, and that the last part equals the old tip. Each version path is checked on its own:
`git diff <old-tip> <last part> -- <version path>` may differ only in the version lines that the PR skill or `CLAUDE.md` names; every other path prints nothing. Otherwise roll back.

## Roll back

A stop after step 2 and before `<branch>` is pushed runs these commands in order, through `delivery`. They restore
`<branch>` to the old tip and leave `<branch>` checked out. They never use `git reset --hard` or
`git switch --discard-changes`, because those discard uncommitted changes the user made before
the run.

1. Discard the uncommitted edits of this run. For each path that `git status --porcelain` lists
   and the step 2 record does not: `git restore --staged --worktree -- <path>` for a tracked path,
   `git clean -f -- <path>` for an untracked one.
2. `git switch <branch>`.
3. `git reset --keep <old-tip>`.
4. For each branch the run created (steps 3 and 6, tips in the ledger): `git branch -D <name>`, only when its tip equals the recorded tip. Otherwise keep it. The report names it.
5. Check: `git branch --show-current` prints `<branch>`, and `git rev-parse <branch>` prints the
   old tip.

A failed command ends the rollback. The report names the command, the checked-out branch and the
tips of `<branch>` and each branch left.

## Tickets

Only under `delivery: pr`, in step 5, after every scratch part passes. `tracker` creates one ticket per stacked part, part 2 first. Part 1 keeps `<orig>`.

| Item | Rule |
|---|---|
| Title, description | The part's scope: what it does, its commands, options, files, formats and acceptance criteria. No "Split from" line, no reference to the original ticket. |
| Fields, links | Copied from `<orig>` as the `tracker` prompt lists. The previous part's ticket blocks this one. |
| Branch name | `<tid>_<slug>`; `<tid>` is `issue-<N>` for a GitHub `#N`, the key for Jira. |

If a create fails, or any stop rolls back after the tickets exist, the report names every ticket already created (ids and URLs).

After the push of `<branch>` succeeds, `tracker` links the tickets (including `<orig>` to part 2) and rewrites `<orig>` to the remaining scope, so a rolled-back split leaves `<orig>` unchanged. Both are skipped with no ticket. A failed link or rewrite is reported and the run continues. The report carries the path of the saved original body.

## Publish

`delivery` runs it with the brief `publish`. Order: push `<branch>`, then each stacked branch, then the pull requests in the same order. Each `git push` is its own Bash call, starting with `git -C <repo> push -u origin <name>`.
Only here, a branch that is already pushed after an amend or a squash is pushed with `--force-with-lease`; a job never does.

| Branch | Pull request |
|---|---|
| `<branch>` | Reuse an `OPEN` pull request (dispatch part 1 may have created it). Otherwise create one against `<base>`. |
| Each stacked branch | Against the previous part, with the repository's PR skill when it names one. Body: 2-4 bullet items, including "Stacked on <previous PR>" and the ticket id. |

After the push `delivery` reads the tree of the last part on `origin` and compares it with the old tip as step 6 does. A failed push of `<branch>` rolls back. A failure after `<branch>` is pushed
switches to `<branch>`, stops and reports what was pushed and opened. It does not roll back and pushes nothing further.
When the original pull request merges and its head branch is deleted, GitHub retargets the stacked one.

## Report

| Item | Value |
|---|---|
| Tickets | The new ticket ids, or none under `delivery: commit`. |
| Parts | Per part: its branch, its items, its changed lines. The estimate and the cap. |
| Pull requests | Under `pr`, the URLs in chain order. |
| Original ticket | `<orig>`, the result of the link and of the rewrite, and the path of its saved body. Manual steps: the field and link copy and the rewrite for Jira without MCP tools, and each companion pull request outside `repos`. |
| Sibling PRs | Each, with its part or the reason it stays. |
| Tree check | The tree hash of the old tip and of the last part, locally and on `origin`. |
| Environment | A test failure also present at the old tip, and the path of a clone that failed to be removed. |
| Decisions | Each fork decided by the recommended option. |
