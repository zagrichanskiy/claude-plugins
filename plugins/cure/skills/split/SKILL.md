---
name: split
description: Split a finished branch at a feature seam so each part is its own ticket and pull request. Removes the excess from the unpublished commits, commits it on a new branch stacked on the original branch, tests both branches, and under `delivery: pr` creates a ticket, pushes both and opens both pull requests. Use when a job's diff passed 1.5 times its estimate (called by `cure:goal` before the push), or when the user says "split this branch", "split this PR", or "/cure:split".
allowed-tools: Read, Grep, Glob, Bash, Agent
---

# Split

A branch grew past its estimate. This skill moves the excess feature to its own ticket, branch and
pull request. It asks the user nothing. It decides a fork by the recommended option and lists the
decision in the report.

Plugin root: `${CLAUDE_PLUGIN_ROOT}`. Write its value in place of `<plugin-root>` in every command
below.

## Inputs

| Input | Meaning |
|---|---|
| Repository | Absolute git toplevel. One repository per run. |
| Branch | The branch to split. |
| Base | The branch the pull request targets, and the base commit the caller recorded (`<base-commit>`). Without a base commit: `git merge-base origin/<base> <branch>`. |
| Estimate | The estimated changed lines of the task. The report compares the diff with it. |
| Excess | A description of the feature to move: the behaviour, the files and the tests that belong to it. |
| Delivery | `pr` or `commit`, as the caller passes it (the job's handoff `delivery`). Without one, as when run by hand: `<plugin-root>/bin/cure-job config get handoff.delivery` (default `commit`). |

Read a missing input from the context: the current branch from `git -C <repo> rev-parse --abbrev-ref HEAD`,
the base from the job's `base` or `gh pr view --repo <owner/repo> --json baseRefName`. Without a repository, a branch or an
excess description, stop and name the missing input.

| Delivery | Result |
|---|---|
| `pr` | Ticket, stacked branch, push and both pull requests. |
| `commit` | The stacked branch exists locally. No ticket, no push, no pull request. The report names the branch. |

## Executors

A run is in a job when the size check of `skills/goal/rules.md` calls the skill. The orchestrator of a
job has no Edit tool and no MCP tool, and runs `git`, `gh` and `cure-job` only. These steps run as follows.

| Step | In a job | By hand |
|---|---|---|
| Edit files | `implementer` | `implementer` |
| Run the tests of a branch | The orchestrator runs `git switch <name>`, then dispatches `qa` with the test command and the expected result. The dispatch carries the short-hold claim when the goal claims. | The session |
| Create a Jira ticket | The command in `split.jira-command`: `<plugin-root>/bin/cure-job config get split.jira-command` prints it as JSON. | The session's Jira command or MCP tool |

## Steps

| # | Step |
|---|---|
| 1 | Preflight (section "Preflight"). A failure stops the skill with nothing changed. |
| 2 | Record the old tip (`git -C <repo> rev-parse <branch>`) and the paths that `git -C <repo> status --porcelain` lists. |
| 3 | Check the seam and remove the excess from `<branch>` (sections "Seam" and "Remove the excess"). |
| 4 | Create the stacked branch and commit the excess on it (section "Stacked branch"). |
| 5 | Run the tests on both branches and review the removal (section "Tests"). |
| 6 | `pr` only: create the ticket (section "Ticket"). |
| 7 | `pr` only: push both branches and open both pull requests (section "Push and pull requests"). |
| 8 | `git switch <branch>`, then report (section "Report"). |

Every exit leaves `<branch>` checked out.

Every command runs as `git -C <repo>`. Stage with explicit paths; never `git add -A` or `git add .`.

## Preflight

Under `delivery: pr` check the tracker before any change, so that no step leaves a ticket or a
branch without the other. Read it: `<plugin-root>/bin/cure-job config get split.tracker`. It prints JSON.

| Tracker | Check |
|---|---|
| `github` (default) | `gh auth status` succeeds, and `gh repo view <owner/repo> --json hasIssuesEnabled` is true. `<owner/repo>` comes from the remote of the repository. |
| `jira` | In a job, `split.jira-command` is not empty. By hand, the session has a Jira command or MCP tool. |

A failed check stops the skill with nothing changed. The report names the check. The skill also stops with nothing changed when `git branch --show-current` is not `<branch>`, or when `git status --porcelain` lists a staged entry, or lists a path that is in `git diff --name-only --no-renames <base-commit> <branch>` or in the excess file list. The skill never
logs in and never reads or stores a token.

## Seam

The excess is a seam when all of these hold:

1. `<branch>` without the excess builds and passes its tests. Step 5 proves it.
2. No file that stays calls something only the excess defines.
3. The tests of the excess move with its code.
4. One sentence describes the excess as one feature.

Checks 2 to 4 need source reading. The orchestrator of a job reads no source, so the brief of the
`implementer` agent in step 3 carries them: it answers yes or no for each, with the file names that
fail, before it edits a file. A "no" stops the skill with nothing changed.

A file that both parts edit stays on `<branch>` with the lines the remaining part needs. The stacked
branch takes the file whole from the old tip.

## Remove the excess

1. List the files of the excess: `git diff --stat <base-commit> <branch>` and the excess description.
2. Dispatch the `implementer` agent. In a job the orchestrator has no Edit tool, so this step
   always goes through the agent. Brief it with the repository, the branch, the file list, the
   excess description, checks 2 to 4 of section "Seam", and the rule "remove the excess, keep the
   remaining feature building and tested, do not commit". Pass paths, not file text. A file the
   excess deleted comes back with `git checkout <base-commit> -- <path>`.
3. Commit the removal on `<branch>`. Check whether its latest commit is published:
   `git log origin/<branch>..<branch>` (all commits are unpublished when `origin/<branch>` does not exist).

| Latest commit | Command |
|---|---|
| Unpublished (the log lists it) | `git commit --amend --no-edit` with the changed paths staged. The removal joins that commit. |
| Published | A new commit "Move <excess> to its own branch". No history rewrite, no force push. |

## Stacked branch

1. `git switch -c <stacked> <branch>`. The name is `<slug>`, the excess in 2-4 words. Step 6 renames it
   to `<tid>_<slug>` when a ticket exists (`<tid>` is defined in section "Ticket"). When the name exists, `git switch -c` fails: roll back.
   Step 4 of the rollback then does not run, because this skill did not create that branch.
2. Make every path of `git diff --name-only --no-renames <branch> <old-tip>` equal to the old tip. A path that exists at the old tip:
   `git checkout <old-tip> -- <path>`. A path the excess deleted: `git rm <path>`. When the
   checkout cannot restore a path, the `implementer` agent does it with the rule "make these
   paths equal to the old tip, do not commit".
3. Commit: "<excess as one sentence>". The message names no split.

The tree of `<stacked>` equals the old tip. Check: `git diff <old-tip> <stacked>` prints nothing; otherwise roll back.

## Tests

Take the test command from the `CLAUDE.md` of the repository. Run the tests of `<branch>`, then
those of `<stacked>`, as section "Executors" says. The pass on `<branch>` proves seam check 1.

| Result | Action |
|---|---|
| `<branch>` fails | The seam is wrong. Roll back (section "Roll back"). Stop and report. |
| `<stacked>` fails | Run its tests once more. When they fail again, roll back, stop and report. The skill amends nothing. |
| Both pass | Dispatch the `reviewer` agent on `git diff <old-tip> <branch>`. Its brief adds checks 2 to 4 of section "Seam": no file that stays calls something only `<stacked>` defines, the tests of the excess moved, and `<stacked>` holds one feature. A failed check is a MUST-FIX. A MUST-FIX or SHOULD-CONSIDER rolls back, stops and reports. Otherwise continue. |

## Roll back

A stop after step 2 and before `<branch>` is pushed runs these commands in order. They restore
`<branch>` to the old tip and leave `<branch>` checked out. They never use `git reset --hard` or
`git switch --discard-changes`, because those discard uncommitted changes the user made before
the run.

1. Discard the uncommitted edits of this run. For each path that `git status --porcelain` lists
   and the step 2 record does not: `git restore --staged --worktree -- <path>` for a tracked path,
   `git clean -f -- <path>` for an untracked one.
2. `git switch <branch>`.
3. `git reset --keep <old-tip>`.
4. When step 4 created `<stacked>`: `git branch -D <stacked>` under its current name, only when
   `git diff <old-tip> <stacked>` prints nothing. Otherwise keep it. The report names it.
5. Check: `git branch --show-current` prints `<branch>`, and `git rev-parse <branch>` prints the
   old tip.

A failed command ends the rollback. The report names the command, the checked-out branch and the
tips of `<branch>` and `<stacked>`.

## Ticket

Only under `delivery: pr`, after both test runs pass.

| Tracker | Action |
|---|---|
| `github` (default) | `gh issue create --repo <owner/repo> --title "<excess as one sentence>" --body "<scope and parent ticket>"`. The ticket id is `#N` from the URL it prints. |
| `jira` | Create the ticket as section "Executors" says. In a job, replace `<title>`, `<body>` and, when the template has it, `<project>` in `split.jira-command` with the shell-quoted values. `<project>` is the project key of the ticket of `<branch>` (the part of the key before the dash). By hand, take the project from the task context. The ticket id is the key it returns. |

`<tid>` is the branch form of the ticket id: `issue-<N>` for a GitHub `#N`, the key for Jira.
Then `git branch -m <stacked> <tid>_<slug>` and, on that branch, reword the commit with
`git commit --amend -m "<ticket>: <excess as one sentence>"`. If the create, the rename or the
reword fails, roll back, stop and report. The report names a ticket already created.

## Push and pull requests

`<owner/repo>` comes from the remote of the repository. Pass it as `--repo` to every `gh` command. Order: push `<branch>`, push `<stacked>`, open the pull request of `<branch>`, open that of `<stacked>`. Run each `git push` as its own Bash call, starting with `git -C <repo> push -u origin <name>`. When a review fix amended a commit of `<branch>` that is already pushed, push it with `git -C <repo> push --force-with-lease origin <branch>`.

| Branch | Pull request |
|---|---|
| `<branch>` | `gh pr view <branch> --repo <owner/repo> --json url,state`. Reuse the pull request it finds only when its state is `OPEN` (dispatch part 1 may have created it). Otherwise: `gh pr create --repo <owner/repo> --base <base> --head <branch>`, title and body as for the original task. |
| `<stacked>` | `gh pr create --repo <owner/repo> --base <branch> --head <stacked>`. Title from the excess sentence. Body: 2-4 bullet items, including "Stacked on <PR of branch>" and the ticket id. |

A failed push of `<branch>` rolls back. A failure after `<branch>` is pushed runs
`git switch <branch>`, stops and reports what was pushed and opened. It does not roll back and pushes nothing further.

Use the PR skill the repository names in place of `gh pr create` when it names one. When the original
pull request merges and its head branch is deleted, GitHub retargets the stacked one.

## Report

| Item | Value |
|---|---|
| Ticket | The new ticket id, or none under `delivery: commit`. |
| Stacked branch | Its name. |
| Pull requests | Under `pr`, the two URLs, original first. |
| Lines | Changed lines of each branch, and the estimate. |
| Decisions | Each fork decided by the recommended option. |
