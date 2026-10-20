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
- A choice that changes behaviour the user would see is a question, also when the goal file or its
  design source is silent or contradictory on it. Never decide it silently.
- A fork whose options differ in nothing the user would see is not a question: take the recommended
  option and record it as an assumption.
- Asking: when the goal file names `worker.md`, take the `needs-input:` exit as `worker.md` says.
  Otherwise ask with `AskUserQuestion` and wait.
- Each question states the situation, the options, the consequence of each and a recommendation,
  for a reader who has not followed the run.
- A mechanical choice that the code or conventions determine: decide it. Scope with `grep` first.
- Read with `gh issue view --json <fields>` or `gh pr view --json <fields>`. Edit with `gh api`, for
  example `gh api -X PATCH repos/{owner}/{repo}/pulls/<n> -f body=...`. `gh issue view` and
  `gh pr edit` without these fail on the Projects (classic) deprecation.
- Stage git changes with explicit paths; never `git add -A` or `git add .`.
- Last step of every tier, Solo included: append one row to `~/.claude/retros/stats.md`, with this
  command and its values filled in. A failed goal appends a row. A `needs-input` exit does not.
  Unknown value is `-`; approximate value is `~45`. `|` and `'` are stripped from every value (the
  command quotes each value in single quotes). `outcome` is `met` or `failed`.

  ```sh
  mkdir -p ~/.claude/retros
  (set -C; printf '%s\n' '| date | repo | slug | tier | outcome | est_lines | lines | turns | agent_tokens | rounds | title |' '|---|---|---|---|---|---|---|---|---|---|---|' > ~/.claude/retros/stats.md) 2>/dev/null
  grep -qF '| <date> | <repo> | <slug> |' ~/.claude/retros/stats.md || printf '%s\n' '| <date> | <repo> | <slug> | <tier> | <outcome> | <est_lines> | <lines> | <turns> | <agent_tokens> | <rounds> | <title> |' >> ~/.claude/retros/stats.md
  ```

- The row's `lines` is insertions plus deletions of `git diff --shortstat <base>`, largest
  repository. `agent_tokens` is the sum of the subagent token reports. `rounds` is the review rounds.
- Done when: `grep -cF '| <date> | <repo> | <slug> |' ~/.claude/retros/stats.md` prints `1`.

## Light and Full

- The main session orchestrates: it dispatches agents, keeps the ledger, checks completeness. It
  reads no source and edits no code.
- The orchestrator creates the branch and makes every commit, with explicit paths. It never asks
  `implementer`, `test-author` or `skill-author` to do either.
- An agent returns its questions in its report. The orchestrator puts a work item's questions in one
  round.
- Record a mechanical choice in the ledger as an assumption.
- Pass agents paths and ids. Ask for findings only.
- Full: run `test-author` only for a behaviour change that has no test.
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
