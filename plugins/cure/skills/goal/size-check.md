# Size check

`<plugin-root>` below is this file's path without its trailing `/skills/goal/size-check.md`.

Run the check after the last review round and the final commit, before the push. Measure each
repository's diff (as the failure exit states, from the base commit) against its Estimate line in
Settled ("Estimate: ~N changed lines", with "in <repo>" for several). Skip the check when Settled has
no estimate. The check asks the user nothing. The job does not stop at `split.factor` × the estimate;
it finishes its work first.

- The PR diff is the insertions plus deletions of `git diff --shortstat <base-ref>...<branch>`,
  committed refs only. `<base-ref>` is the local `<base>` when `<base>` is a predecessor's branch or
  Settled says "Base: the PR branch of split part 1"; else `origin/<base>` when it exists; else the
  local `<base>`.
- When any repository's diff passes `split.factor` × its estimate: add a `Wn` row (why the diff
  grew) and a proposal (the fix to the rule or skill) to the job's retrospective file. The
  retrospective work item completes that file.
- Call `cure:split` only when the job has one repository,
  `<plugin-root>/bin/cure-job list --json` shows no job whose `after` is this job, and the PR diff
  passes the cap (`split.limit`: the Settled line "Split cap", else
  `<plugin-root>/bin/cure-job config get split.limit`). Otherwise the `Wn` row names the unmet
  condition, the retrospective is written and the job delivers its single branch.
- Compute R = PR diff − cap. When R exceeds the job's own diff (insertions plus deletions of
  `git diff --shortstat <base commit>..HEAD`), skip `cure:split`, add a `Wn` row naming this
  reason and deliver the single branch.
- The call passes the repository, the branch, the base ref, the base commit item 1 recorded, the
  estimate, the delivery, the cap, R and the job's work items (each with files and tests).
  `cure:split` cuts the PR diff into as many parts as the cap needs. Record the tip of `<branch>`
  before the call.
- `pr`: the push and the pull requests are those of `cure:split`. When it stops before it pushes
  `<branch>`, it has rolled `<branch>` back to the recorded tip (its section "Roll back"). The job
  checks that `git -C <repo> branch --show-current` prints `<branch>` and that
  `git -C <repo> rev-parse <branch>` prints the recorded tip. Then it pushes and opens its single
  PR as planned. A failed check or a failed rollback takes the failure exit, and the job pushes
  nothing. When `cure:split` pushed `<branch>` and then failed, the job takes the failure exit with
  `--pr` for each pull request opened, pushes nothing further and names the work as left on the
  local stacked branches. The retrospective records why the split stopped. The report names any
  ticket `cure:split` created.
- `commit`: `cure:split` creates the stacked branches locally, with no ticket and no push, and the
  report names them. When it stops, the job runs the same two checks, then delivers its single
  branch. A failed check takes the failure exit.
- `cure:split` stops at its check 4 (a part of the chain is still over the cap after one re-cut): it
  has changed no branch. The job adds a `Wn` row naming the overrun in changed lines and delivers
  its single branch.
- After a successful split, re-run each done-when check that a moved work item owns on the branch of
  the part the split report maps the item to (`qa` for a test run). The item counts as delivered
  when the check passes there, and the final message names that branch as evidence. A check on
  `<branch>` that fails only because the work moved is not a failure cause.
