---
name: split
description: Split a finished branch into a chain of parts, each at or under the cap, that build and pass their tests, so each moved part is its own ticket and pull request. Use when a job's diff passed `split.factor` times its estimate and the PR diff passed the cap `split.limit` (called by `cure:goal` before the push), or when the user says "split this branch", "split this PR", or "/cure:split".
allowed-tools: Read, Grep, Glob, Bash, Agent
---

# Split

Part 1 is `<branch>` with the moved work removed. Parts 2 to n are stacked branches, each on the one before, each with its own ticket and pull request, all at or under the cap. Ask the user nothing: decide a fork by the recommended option and report it.

Plugin root: `${CLAUDE_PLUGIN_ROOT}`. Write its value in place of `<plugin-root>` in commands.

## Inputs

Read `<plugin-root>/skills/split/inputs.md`. It defines Repository, Branch, Base (`<base>`, `<base-ref>`, `<base-commit>`), Estimate, Cap, R, Ticket (`<orig>`, `<ticket-repo>`), Items, Rewrite, Delivery and the PR diff. Without a repository, a branch or the items, stop and name the missing input.

Under `delivery: commit` create the stacked branches locally only: no ticket, push, pull request or `gh` command. The report names them.

## Executors

`implementer` edits files; `delivery` runs git, bumps, part sizes, tree checks, clone, push, pull requests and roll back; `tracker` runs tickets; `qa` runs the tests of a part; `reviewer` reviews. Read no diff, payload or test log. Put every needed value in the brief. Briefs: `agents/delivery.md`, `agents/tracker.md`.

Keep a ledger: the plan table, the old tip, the step 2 record, the version paths, the tip of every branch the run creates, the ticket ids and the saved-body path.

Before each `qa` dispatch, run `git switch <part branch>` (in a job, the orchestrator does). The dispatch carries the test command, the expected result and the short-hold claim when the goal claims.

## Steps

1. Preflight. A failure stops the skill with nothing changed.
2. Record the old tip (`git -C <repo> rev-parse <branch>`) and the paths that `git -C <repo> status --porcelain` lists.
3. Plan the chain on scratch branches `split-tmp/<k>`. No branch of the user changes in steps 3 to 5.
4. Test every scratch part, review part 1, run the fix loop (section "Tests").
5. `pr` only: create the tickets (section "Tickets"). Their ids fix the final branch names and messages.
6. Build `<branch>` and the stacked branches once, with final names (section "Build the chain").
7. `pr` only: push the chain, open the pull requests, link the tickets (sections "Publish" and "Tickets").
8. `git switch <branch>`, then report.

Every exit leaves `<branch>` checked out. Stage with explicit paths; never `git add -A` or `git add .`.

## Preflight

Under `pr`, dispatch `tracker` with the brief `check` and `delivery` with the brief `preflight`. The tracker comes from the ticket form, else from `<plugin-root>/bin/cure-job config get split.tracker` (default `github`). `check` reports `github: ok | no-auth | issues-disabled`, `jira: mcp | command | none` and `clickup: mcp | none`. `none`, `no-auth` or `issues-disabled` for the chosen tracker stops the skill.

Stop with nothing changed, naming the check, when a check fails, when `git branch --show-current` is not `<branch>`, or when `git status --porcelain` lists a staged entry or a path in `git diff --name-only --no-renames <base-commit> <branch>` or in the files of any item. Never log in and never read or store a token.

## Plan the chain

Read `<plugin-root>/skills/split/plan.md` before step 3.

## Seam

Each part is a seam when checks 1 to 3 hold.

1. Every part builds and passes its tests. Step 4 proves it.
2. No file that stays in an earlier part calls something only a later part defines.
3. The tests of a feature move with its code.
4. Every part has a PR diff at or under the cap (measured from the previous part). A part over the cap after one re-cut stops the split with `<branch>` unchanged.

Checks 2 and 3 need source reading: the `implementer` answers yes or no for each, with the failing file names, before `scratch 1`. A "no" stops the skill with nothing changed.

## Tests

Run the tests as the repository's CI or its recipe test task runs them (a wrapper, a daemon, an emulator), not only the bare command of `CLAUDE.md`; give `qa` this as its test-environment brief. Read `<plugin-root>/skills/split/tests.md` before step 4.

## Build the chain

Read `<plugin-root>/skills/split/build-publish.md` before step 6. `delivery` `apply` builds the branches once. A failed tree check rolls back.

## Roll back

A stop after step 2 and before `<branch>` is pushed runs these commands in order, through `delivery`. They restore `<branch>` to the old tip and leave it checked out. Never use `git reset --hard` or `git switch --discard-changes`.

1. For each path that `git status --porcelain` lists and the step 2 record does not: `git restore --staged --worktree -- <path>` for a tracked path, `git clean -f -- <path>` for an untracked one.
2. `git switch <branch>`.
3. `git reset --keep <old-tip>`.
4. For each branch the run created (steps 3 and 6, tips in the ledger): `git branch -D <name>`, only when its tip equals the recorded tip. Otherwise keep it and name it in the report.
5. Check: `git branch --show-current` prints `<branch>`, and `git rev-parse <branch>` prints the old tip.

A failed command ends the rollback. The report names the command, the checked-out branch and the tips of `<branch>` and each branch left.

## Tickets

Only under `delivery: pr`, in step 5, after every scratch part passes. Read `<plugin-root>/skills/split/build-publish.md` section "Tickets". `tracker` creates one ticket per stacked part, part 2 first. Part 1 keeps `<orig>`. The branch name of a stacked part is `<tid>_<slug>`; `<tid>` is `issue-<N>` for a GitHub `#N`, the key for Jira, the custom id for ClickUp.

## Publish

Read `<plugin-root>/skills/split/build-publish.md` section "Publish" before step 7; `delivery` runs the brief `publish`.

## Report

- the new ticket ids (none under `commit`)
- per part its branch, items and changed lines, with the estimate and the cap
- under `pr` the pull request URLs in chain order
- `<orig>` with the link and rewrite results and the saved-body path
- manual steps (field and link copy and rewrite for Jira without MCP tools, each companion pull request outside `repos`)
- each sibling PR with its part or the reason it stays
- the tree hash of the old tip and of the last part, locally and on `origin`
- a test failure also present at the old tip and the path of a clone left behind
- each fork decided
