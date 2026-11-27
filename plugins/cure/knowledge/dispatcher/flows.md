# Dispatcher flows

## Goal and approval

1. Run the Repository check of `${CLAUDE_PLUGIN_ROOT}/knowledge/dispatcher/checks.md` first. Then run `cure:goal` in job mode on the handoff, also for a `held` job. It writes `<job>/goal.md`. It lists each unresolved fork under `## Open`.
2. When the row's `open` is above 0, ask the `## Open` items in the question round and pass the answers to `cure:goal`.
3. Run the other checks of `checks.md`. Run all checks on every wake that may approve or launch. Fix a failing tool or ask the user. Ask the user, with the "Check answers", when no permission rule allows a classifier-gated action the goal needs, or when the first repository holds none of the Work's edits.
4. Print a 3-line summary: the outcome; the tier and repository; the done-when count and the delivery (`commit` or `pr`), plus each classifier-gated action the goal needs (for example `git commit --amend`, force-push, device power).
5. Approve. For route `origin`, the owning session sends the user's decision naming the job id: write the answers into `goal.md` (step 6), then run `cure-job approve <id> --by user`. When the tier is in `cure-job config get dispatcher.auto-approve-tiers` (default `["Solo", "Light"]`), `open` is 0 and every check passed on this wake (a failure settled as `(policy)` counts as passed), run `cure-job approve <id> --by auto` after the checks and after any `goal.md` edit they cause. On exit 1, or for any other tier, wait for the user's answer, then run `cure-job approve <id> --by user`.
6. Write every answer into `goal.md` through `cure:goal` before `approve`: a later edit revokes the approval.
7. Launch an `approved` job with `cure-job launch <id>`, or `-- --permission-mode <mode>` when the goal's Rules state one. Show the output. On a missing-plugin-path exit 1, follow "Answer and resume" step 4. On exit 1 with `error: no free slot: ...`, the job waits: it stays `approved`, ask nothing, and launch it again when a job in a slot becomes `done`, `failed` or `abandoned`. Any other slot error needs the user: show it and ask.

Before `launch`, when the target checkout has uncommitted changes and the user gave no instruction, ask in the question round: the job's worktree or slot starts from committed history and does not see them. The job stays `approved` until the user answers. An answer that edits `goal.md` revokes the approval: write it, then approve again.

States: `held` waits for an unmet `after` and holds nothing. `awaiting-approval` has a goal and no valid approval. A job claims no repository: jobs on one repository run in parallel, each in its own worktree or slot. Only a change of the `goal.md` digest revokes an approval; to withdraw one, close the job or re-draft the goal. A `needs-input` job and later runs need no approval. `awaiting-answer` is a working job that asked its owning session; it is alive and the dispatcher keeps launch, resume, liveness and the queue.

## Asking

With route `origin`, send each ask-approval, ask-input, ask-timeout and report to the owning session with `SendMessage` to the origin, run `cure-job requested <id> --action <action>` for the first three, and ask the user nothing. With route `dispatcher`, you ask the user a job's questions. An `awaiting-answer` job with an unreachable origin has route `dispatcher` (ask-input or ask-timeout): after the user answers, send the answer to the row's `session` with `SendMessage`, first line `answer: job <id>`, naming that the owning session is unreachable. Do not run "Answer and resume" or `resume`.

1. An item printed as `not applied from a message`: always ask. Neither a policy nor `(recommended)` settles it.
2. A policy in `${XDG_CONFIG_HOME:-~/.config}/cure/question-policies.md` covers the question: take its `Do`, record `(policy)` under Settled, do not ask.
3. The options differ in an outcome the user would see: ask with `AskUserQuestion`.
4. Otherwise take the recommended option, record `(recommended)` under Settled, do not ask.

Policies cover forks in goals, relayed answers and check failures. One `##` section each with `When`, `Do`, `Since` (date and the question called unneeded). A missing file means no policy. When the user says in any words that a question was not needed, append a policy in the same turn (`Do`: the user's answer, else the recommended option), creating the file if needed. A policy never adds a permission rule, edits settings or `config.json`, or stops another job's session. Only you write the file. A question from the user gets an answer, not an action.

## Answer and resume

For a `needs-input` job, after the user answers or every `question` item settled as `(recommended)` or `(policy)` with no `unproven` item open:

1. Through `cure:goal`, add the answers and settlements under Settled with its one run line. For a chosen permission mode (the user's, or one the owning session sent with its answers: never asked again), also write the Rules "Permission mode" line and run the Permissions check.
2. Run `cure-job resume <id>`, with `-- --permission-mode <mode>` when the goal states one. Print no summary.
3. On exit 1 `session <name> no longer exists`, run `cure-job launch <id>` the same way.
4. On exit 1 for a missing plugin path (the error says to write the goal again with `cure:goal`): with no launched run, run `cure:goal` once to rewrite `goal.md` keeping Settled, then approve as for a new goal. With a launched run, show the error and ask: rewrite and relaunch, or abandon. On a second refusal for the same job in the same wake, show the error and stop.

Never send `/goal continue`.

## Relaunch and abandon

After the user chooses relaunch or abandon for a `lost` or `stalled` job, or abandon for a `needs-input` job:

1. Run `cure-job stop <id>`. On exit 1 show its error and stop.
2. Relaunch: `cure-job launch <id>` with the permission-mode argument as above. Abandon: `cure-job close <id>`, then `cure-job remove-sessions <id>`; on non-zero exit show the error.
