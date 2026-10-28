---
name: split
description: Split a finished branch at a feature seam so each part is its own ticket and pull request. Removes the excess from the unpublished commits, commits it on a new branch stacked on the original branch, tests both branches, and under `delivery: pr` creates a ticket, pushes both and opens both pull requests. Use when a job's diff passed 1.5 times its estimate (called by `cure:goal` before the push), or when the user says "split this branch", "split this PR", or "/cure:split".
allowed-tools: Read, Grep, Glob, Bash, Edit, Agent
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
| Repository | Absolute git toplevel. |
| Branch | The branch to split. |
| Base | The branch the pull request targets. |
| Estimate | The estimated changed lines of the task. The report compares the diff with it. |
| Excess | A description of the feature to move: the behaviour, the files and the tests that belong to it. |
| Delivery | `pr` or `commit`. Default: `<plugin-root>/bin/cure-job config get handoff.delivery`. |

Read a missing input from the context: the current branch from `git -C <repo> rev-parse --abbrev-ref HEAD`,
the base from the job's `base` or `gh pr view --json baseRefName`. Without a repository, a branch or an
excess description, stop and name the missing input.

| Delivery | Result |
|---|---|
| `pr` | Ticket, stacked branch, push and both pull requests. |
| `commit` | The stacked branch exists locally. No ticket, no push, no pull request. The report names the branch. |

## Steps

| # | Step |
|---|---|
| 1 | Preflight (section "Preflight"). A failure stops the skill with nothing changed. |
| 2 | Record the old tip: `git -C <repo> rev-parse <branch>`. |
| 3 | Check the seam and remove the excess from `<branch>` (sections "Seam" and "Remove the excess"). |
| 4 | Create the stacked branch and commit the excess on it (section "Stacked branch"). |
| 5 | Run the tests on both branches (section "Tests"). |
| 6 | `pr` only: create the ticket (section "Ticket"). |
| 7 | `pr` only: push both branches and open both pull requests (section "Push and pull requests"). |
| 8 | Report (section "Report"). |

Every command runs as `git -C <repo>`. Stage with explicit paths; never `git add -A` or `git add .`.

## Preflight

Under `delivery: pr` check the tracker before any change, so that no step leaves a ticket or a
branch without the other. Read it: `<plugin-root>/bin/cure-job config get split.tracker`. It prints JSON.

| Tracker | Check |
|---|---|
| `github` (default) | `gh auth status` succeeds, and `gh repo view <owner/repo> --json hasIssuesEnabled` is true. `<owner/repo>` comes from the remote of the repository. |
| `jira` | A Bash command that creates a Jira ticket exists in the session. In a job the orchestrator has no MCP tool, so a job requires such a Bash command. |

A failed check stops the skill with nothing changed. The report names the check. The skill never
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

1. List the files of the excess: `git diff --stat <base>...<branch>` and the excess description.
2. Dispatch the `implementer` agent. In a job the orchestrator has no Edit tool, so this step
   always goes through the agent. Brief it with the repository, the branch, the file list, the
   excess description, checks 2 to 4 of section "Seam", and the rule "remove the excess, keep the
   remaining feature building and tested, do not commit". Pass paths, not file text. A file the
   excess deleted comes back with `git checkout $(git merge-base <base> <branch>) -- <path>`.
3. Commit the removal on `<branch>`. Check whether its latest commit is published:
   `git log origin/<branch>..<branch>` (all commits are unpublished when `origin/<branch>` does not exist).

| Latest commit | Command |
|---|---|
| Unpublished (the log lists it) | `git commit --amend --no-edit` with the changed paths staged. The removal joins that commit. |
| Published | A new commit "Move <excess> to its own branch". No history rewrite, no force push. |

## Stacked branch

1. `git switch -c <stacked> <branch>`. The name is `<slug>`, the excess in 2-4 words. Step 6 renames it
   to `<ticket>_<slug>` when a ticket exists.
2. Make each excess path equal to the old tip. A path that exists at the old tip:
   `git checkout <old-tip> -- <path>`. A path the excess deleted: `git rm <path>`. When the
   checkout cannot restore a path, the `implementer` agent does it with the rule "make these
   paths equal to the old tip, do not commit".
3. Commit: "<excess as one sentence>". The message names no split.

The tree of `<stacked>` equals the old tip. Check: `git diff <old-tip> <stacked>` prints nothing.

## Tests

Take the test command from the `CLAUDE.md` of the repository. Run `git switch <branch>` and the
tests, then `git switch <stacked>` and the tests. The pass on `<branch>` proves seam check 1.

| Result | Action |
|---|---|
| `<branch>` fails | The seam is wrong. Run `git switch <branch>`. On an unpublished latest commit run `git reset --hard <old-tip>`; on a published one run `git revert --no-edit HEAD`. Then `git branch -D <stacked>`. Stop and report. |
| `<stacked>` fails | `git switch <stacked>`, fix it in the excess commit with `git commit --amend --no-edit`. Run both again. |
| Both pass | Continue. |

## Ticket

Only under `delivery: pr`, after both test runs pass.

| Tracker | Action |
|---|---|
| `github` (default) | `gh issue create --repo <owner/repo> --title "<excess as one sentence>" --body "<scope and parent ticket>"`. The ticket id is `#N` from the URL it prints. |
| `jira` | Create the ticket with the Bash Jira command. Take the project from the task context, such as the ticket of `<branch>`. The ticket id is the key it returns. |

Then `git branch -m <stacked> <ticket>_<slug>` and, on that branch, reword the commit with
`git commit --amend -m "<ticket>: <excess as one sentence>"`. If the create fails, stop and report;
no ticket exists, and the local branches stay for a rerun.

## Push and pull requests

Run each `git push` as its own Bash call, starting with `git -C <repo> push -u origin <name>`.

| Branch | Pull request |
|---|---|
| `<branch>` | `gh pr create --base <base> --head <branch>`. Title and body as for the original task. |
| `<stacked>` | `gh pr create --base <branch> --head <stacked>`. Title from the excess sentence. Body: 2-4 bullet items, including "Stacked on <PR of branch>" and the ticket id. |

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
