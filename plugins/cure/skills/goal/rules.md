# Goal rules

A goal file names this file in its Work section. Its Rules section names the tier. Follow "All
tiers", then "Light and Full" or "Solo". The exit clauses are in the goal file; this file does not
add one.

## All tiers

- Work item 1: run `git fetch`, then the fact check the item names. A false Settled statement, a
  failed fetch or a failed tool check is a failure cause. Base moved: base the work on
  `origin/<base>`. Other mismatch: record it, use the corrected value.
- A choice that changes behaviour the user would see is a question, also when the goal file or its
  design source is silent or contradictory on it. Never decide it silently.
- Asking: when the goal file names `worker.md`, take the `needs-input:` exit as `worker.md` says.
  Otherwise ask with `AskUserQuestion` and wait. Each question states the situation, the options,
  the consequence of each and a recommendation, for a reader who has not followed the run.
- A mechanical choice that the code or conventions determine: decide it. Scope with `grep` first.
- Stage git changes with explicit paths; never `git add -A` or `git add .`.

## Light and Full

- The main session orchestrates: it dispatches agents, keeps the ledger, checks completeness. It
  reads no source and edits no code.
- An agent returns its questions in its report. The orchestrator puts a work item's questions in one
  round.
- Record a mechanical choice in the ledger as an assumption.
- Pass agents paths and ids. Ask for findings only.
- Full: run `test-author` only for a behaviour change that has no test.
- When a failure cause holds: stop, write the retrospective with the cause and what is left, print
  its summary, keep the ledger, take the failure exit.

## Solo

- The session does the task itself. It starts no subagent, holds no review round, writes no
  retrospective, and runs the done-when checks.
- Questions are the session's own (asked or exited per mode). Assumptions are recorded in the final
  message.
- When a failure cause holds: stop, keep the working files, take the failure exit.
