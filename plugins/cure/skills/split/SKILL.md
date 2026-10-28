---
name: split
description: Split a finished branch at a feature seam so each part is its own ticket and pull request. Creates a ticket for the excess, removes the excess from the unpublished commits, commits it on a new branch stacked on the original branch, tests both branches, pushes both and opens both pull requests. Use when a job's diff passed 1.5 times its estimate (called by `cure:goal` before the push), or when the user says "split this branch", "split this PR", or "/cure:split".
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
| Branch | The branch to split. Its commits are unpublished, except in a split the user asked for on a published PR. |
| Base | The branch the pull request targets. |
| Estimate | The estimated changed lines of the task. The report compares the diff with it. |
| Excess | A description of the feature to move: the behaviour, the files and the tests that belong to it. |

Read a missing input from the context: the current branch from `git -C <repo> rev-parse --abbrev-ref HEAD`,
the base from the job's `base` or `gh pr view --json baseRefName`. Without a repository, a branch or an
excess description, stop and name the missing input.

## Steps

| # | Step |
|---|---|
| 1 | Check the seam (section "Seam"). No seam: stop and report why. |
| 2 | Create the ticket (section "Ticket"). |
| 3 | Record the old tip: `git -C <repo> rev-parse <branch>`. |
| 4 | Remove the excess from `<branch>` (section "Remove the excess"). |
| 5 | Create the stacked branch and commit the excess on it (section "Stacked branch"). |
| 6 | Run the tests on both branches (section "Tests"). |
| 7 | Push both branches and open both pull requests (section "Push and pull requests"). |
| 8 | Report (section "Report"). |

Every command runs as `git -C <repo>`. Stage with explicit paths; never `git add -A` or `git add .`.

## Seam

The excess is a seam when all of these hold:

1. `<branch>` without the excess builds and passes its tests.
2. No file that stays calls something only the excess defines.
3. The tests of the excess move with its code.
4. One sentence describes the excess as one feature.

A file that both parts edit stays on `<branch>` with the lines the remaining part needs. The stacked
branch takes the file whole from the old tip.

## Ticket

Read the tracker: `<plugin-root>/bin/cure-job config get split.tracker`. It prints JSON.

| Tracker | Action |
|---|---|
| `github` (default) | `gh issue create --repo <owner/repo> --title "<excess as one sentence>" --body "<scope and parent ticket>"`. `<owner/repo>` comes from the remote of the repository. The ticket id is `#N` from the URL it prints. |
| `jira` | Create the ticket with the Jira command or MCP tool of the session. Take the project from the task context, such as the ticket of `<branch>`. The ticket id is the key it returns. |

When `gh auth status` fails, or the session has no Jira tool, stop and report. The skill never logs
in and never reads or stores a token.

## Remove the excess

1. List the files of the excess: `git diff --stat <base>...<branch>` and the excess description.
2. Dispatch the `implementer` agent. In a job the orchestrator has no Edit tool, so this step
   always goes through the agent. Brief it with the repository, the branch, the file list, the
   excess description and the rule "remove the excess, keep the remaining feature building and
   tested, do not commit". Pass paths, not file text.
3. Commit the removal on `<branch>`:

| Commits of `<branch>` | Command |
|---|---|
| Unpublished | `git commit --amend --no-edit` with the changed paths staged. The removal joins the latest commit. |
| Published (user asked) | A new commit "Move <excess> to <ticket>". No history rewrite, no force push. |

## Stacked branch

1. `git switch -c <stacked> <branch>`. The name is `<ticket>_<slug>`, or `<slug>` when the tracker
   gives no id. `<slug>` is the excess in 2-4 words.
2. Restore each excess path from the old tip: `git checkout <old-tip> -- <paths>`. When
   the checkout cannot restore a path, the `implementer` agent re-adds it with the rule "make these
   paths equal to the old tip, do not commit".
3. Commit: "<ticket>: <excess as one sentence>".

The tree of `<stacked>` equals the old tip. Check: `git diff <old-tip> <stacked>` prints nothing.

## Tests

Take the test command from the `CLAUDE.md` of the repository. Run it on `<branch>`, then on
`<stacked>`.

| Result | Action |
|---|---|
| `<branch>` fails | The seam is wrong. On an unpublished branch run `git reset --hard <old-tip>`, delete `<stacked>`, stop and report. |
| `<stacked>` fails | Fix it on `<stacked>` in the excess commit with `git commit --amend --no-edit`. Run both again. |
| Both pass | Continue. |

## Push and pull requests

Run each `git push` as its own Bash call, starting with `git -C <repo> push -u origin <name>`.

| Branch | Pull request |
|---|---|
| `<branch>` | Base `<base>`. Title and body as for the original task. |
| `<stacked>` | Base `<branch>`. Title from the excess sentence. Body: 2-4 bullet items, including "Stacked on <PR of branch>" and the ticket id. |

Open each with `gh pr create --base <base> --head <branch>`, or the PR skill the repository names.
After the original pull request merges, retarget the stacked one:
`gh api -X PATCH repos/<owner>/<repo>/pulls/<n> -f base=<base>`.

## Report

| Item | Value |
|---|---|
| Ticket | The new ticket id. |
| Stacked branch | Its name. |
| Pull requests | The two URLs, original first. |
| Lines | Changed lines of each branch, and the estimate. |
| Decisions | Each fork decided by the recommended option. |
