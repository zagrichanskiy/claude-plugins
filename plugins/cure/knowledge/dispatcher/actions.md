# Dispatcher actions in detail

## ask-timeout

Condition: `needs-input`, and the only question of `result.md` starts with `short-hold timeout:`. `args`: `resource`, `holder` (holder id; null when the question has no "held by").

1. Read the holder's row in `cure-job list --json`.
2. Tell the user the resource, the holder id and the holder's state (the resource only when `holder` is null).
3. Ask: wait again (as in "Answer and resume") or abandon (as in "Relaunch and abandon"). When the holder is `lost`, offer relaunch or abandon of the holder first, as in `ask-relaunch`.
4. Never settle it as `(recommended)` or `(policy)`. Never run `cure-job release` for a job: only its own claimant releases.

## ask-input

Condition: `needs-input`, not `ask-timeout`.

1. Read `result.md`.
2. A `question` item that starts with `auto-mode no verdict:` is asked with the leave-auto-mode answers in `checks.md` "Check answers". Never settle it as `(recommended)` or `(policy)`.
3. Settle each other `question` item as in "Asking". Ask the user the rest and each `unproven` item.
4. Continue as in "Answer and resume" (step 1 writes the leave-auto-mode choice). When the user chooses abandon, continue as in "Relaunch and abandon".

## config-error

Condition: `config.json` has an error. The element is last in the array, `id` is null. `args`: `errors`.

Show each line of `errors` to the user. Ask nothing. Each line is `config.json: <key>: <problem>`, or `config.json: <problem>` for a whole-file error (for example `config.json found at the old location <path>; run cure-job config init`).

When every line is a flat-key problem (`config.json: handoff.delivery: flat key; write it as {"handoff": {"delivery": ...}}`) or a removed-key problem (`config.json: <group>: "<name>" is removed; <reason>`):

1. Rewrite `${CURE_JOB_CONFIG:-${XDG_CONFIG_HOME:-~/.config}/cure/config.json}` to the nested layout of `${CLAUDE_PLUGIN_ROOT}/skills/dispatch/config.example.json`. Move each flat dotted key into its group, drop each removed key, keep every other value. A removed `band.jira-url` becomes `band.tracker-url` with the value `<jira-url>/browse/<key>`.
2. Run `cure-job config check`. On exit 0, tell the user which keys moved or were dropped. On exit 1, show its stderr.

When any line is another problem, do not edit the file; suggest `cure-job config check` after the user fixes it. An unknown-key line ends with `unknown to cure <version>; restart the dispatcher after an update`; do not edit the file for it.

Until the error is fixed, `prune` removes no job and `approve --by auto` exits 1. Wait for the user's answer, then run `cure-job approve <id> --by user`.

## States with no action

| State | Note |
|---|---|
| `held` | Nothing unless `draft`, `ask-approval` or `close-successor` applies. A `held` job holds nothing. |
| `held`, `after-state` `invalid` | Do nothing for the successor: `draft`, `ask-approval` and auto-approval do not apply. The predecessor's `repair` action asks the user. Do not close the successor. |
| `launched`, `running` | For `launch-grace-seconds` seconds (`cure-job config get launch-grace-seconds`; default 60) after a launch or resume, a session that `claude agents` does not list yet, or lists stopped, shows as `launched`, not `lost`. After `cure-job stop`, a session listed stopped shows as `lost` at once. |
| `done`, `abandoned` | Nothing left to report or remove. |
