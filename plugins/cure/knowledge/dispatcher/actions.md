# Dispatcher actions in detail

## ask-timeout

Condition: `needs-input`, or `awaiting-answer` with an unreachable origin, and the only question (of `result.md`, or `args.question`) starts with `short-hold timeout:`. `args`: `resource`, `holder` (holder id; null when the question has no "held by").

Route `origin`: send the question to the owning session (`SendMessage` to the origin, kind `question`), run `cure-job requested <id> --action ask-timeout`, and stop. Route `dispatcher`:

1. Read the holder's row in `cure-job list --json`.
2. Tell the user the job's owning session and ticket, the resource, the holder id and the holder's state (the resource only when `holder` is null).
3. Ask: wait again or abandon (as in "Relaunch and abandon"). When the holder is `lost`, offer relaunch or abandon of the holder first, as in `ask-relaunch`.
4. Wait again: for `awaiting-answer`, send the answer with `SendMessage` to the row's `session`, first line `answer: job <id>`, naming that the owning session is unreachable, and do not run `resume`; otherwise continue as in "Answer and resume" (after a route `origin` answer, the same).
5. Never settle it as `(recommended)` or `(policy)`. Never run `cure-job release` for a job: only its own claimant releases.

## ask-input

Condition: `needs-input` or `awaiting-answer` with an unreachable origin, not `ask-timeout` (`args`: `route` `dispatcher`, `question`).

Route `origin`: send the `question` items of `result.md` to the owning session (`SendMessage` to the origin, kind `question`), run `cure-job requested <id> --action ask-input`, and stop. The owning session's answers arrive as a message naming the job id: continue as in "Answer and resume". Route `dispatcher`:

1. Read `result.md`, or `args.question` for `awaiting-answer`. Name the job's owning session and ticket in every question to the user.
2. A `question` item that starts with `auto-mode no verdict:` is asked with the leave-auto-mode answers in `checks.md` "Check answers". Never settle it as `(recommended)` or `(policy)`.
3. Settle each other `question` item as in "Asking". Ask the user the rest and each `unproven` item.
4. For `awaiting-answer`, send the answer with `SendMessage` to the row's `session`, first line `answer: job <id>`, naming that the owning session is unreachable. Do not run "Answer and resume" or `resume`. Otherwise continue as in "Answer and resume" (step 1 writes the leave-auto-mode choice; a mode the owning session sent is that choice, not asked again). When the user chooses abandon, continue as in "Relaunch and abandon".

## config-error

Condition: `config.json` has an error. The element is last in the array, `id` is null. `args`: `errors`.

Show each line of `errors` to the user. Ask nothing. Each line is `config.json: <key>: <problem>`, or `config.json: <problem>` for a whole-file error (for example `config.json found at the old location <path>; run cure-job config init`).

When every line is a flat-key problem (`config.json: handoff.delivery: flat key; write it as {"handoff": {"delivery": ...}}`) or a removed-key problem (`config.json: <group>: "<name>" is removed; <reason>`, or `config.json: <group>: group is removed; <reason>` for a whole group):

1. Rewrite `${CURE_JOB_CONFIG:-${XDG_CONFIG_HOME:-~/.config}/cure/config.json}` to the nested layout of `${CLAUDE_PLUGIN_ROOT}/skills/dispatch/config.example.json`. Move each flat dotted key into its group, drop each removed key and group, keep every other value.
2. Run `cure-job config check`. On exit 0, tell the user which keys moved or were dropped. On exit 1, show its stderr.

When any line is another problem, do not edit the file; suggest `cure-job config check` after the user fixes it. An unknown-key line ends with `unknown to cure <version>; restart the dispatcher after an update`; do not edit the file for it.

Until the error is fixed, `prune` removes no job and `approve --by auto` exits 1. Wait for the user's answer, then run `cure-job approve <id> --by user`.

## States with no action

| State | Note |
|---|---|
| `held` | Nothing unless `draft`, `ask-approval` or `close-successor` applies. A `held` job holds nothing. |
| `held`, `after-state` `invalid` | Do nothing for the successor: `draft`, `ask-approval` and auto-approval do not apply. The predecessor's `repair` action asks the user. Do not close the successor. |
| `launched`, `running` | For `launch-grace-seconds` seconds (`cure-job config get launch-grace-seconds`; default 60) after a launch or resume, a session that `claude agents` does not list yet, or lists stopped, shows as `launched`, not `lost`. After `cure-job stop`, a session listed stopped shows as `lost` at once. |
| `awaiting-answer` | The job asked its owning session a question and its session is busy, idle or stalled. It is alive: never `confirm-stalled`. A reachable origin gets no action. |
| `done`, `abandoned` | Nothing left to report or remove. |
