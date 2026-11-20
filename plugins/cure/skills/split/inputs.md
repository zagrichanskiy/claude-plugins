# Split inputs

| Input | Meaning |
|---|---|
| Repository | Absolute git toplevel. One repository is split per run. Sibling and companion PRs in other repositories are handled as sections "Preflight" and "Plan the chain" say. |
| Branch | The branch to split. |
| Base | The branch the pull request targets (`<base>`), the ref the work was based on (`<base-ref>`) and the base commit the caller recorded (`<base-commit>`). `<base-ref>` is the local `<base>` when `<base>` is a predecessor's branch or the job's Settled says "Base: the PR branch of split part 1"; else `origin/<base>` when it exists; else the local `<base>`. Without a base commit: `git merge-base <base-ref> <branch>`. |
| Estimate | The estimated changed lines of the task. The report compares the diff with it. |
| Cap | `split.limit`, in changed lines (default 1200). In a job, the caller passes the value from Settled. Without one: `<plugin-root>/bin/cure-job config get split.limit`. |
| R | The required move: the PR diff before the split minus the cap, in changed lines. In a job, the caller passes it. By hand, measure the PR diff and subtract the cap. R is the trigger guard only; section "Plan the chain" decides what moves. |
| Ticket | In a job, the handoff `ticket`. By hand, the ticket parsed from the branch name or given by the user. `<orig>` is its id (`<N>` of a GitHub `#N`, the Jira key, or the ClickUp custom id). The form picks the tracker: `#N`, `owner/repo#N` or a github.com URL is GitHub; an app.clickup.com URL is ClickUp; `KEY-N` is ClickUp when `split.tracker` is `clickup`, else Jira. `split.tracker` applies only with no ticket; then the Jira project or the ClickUp list comes from the task context. `<ticket-repo>` is the repository the ticket names, else the remote; it is the `--repo` of every command on `<orig>`. With no ticket, the rewrite and the link are skipped. |
| Items | The packing units: the job's work items, each with its files and tests (from `git diff --stat`). By hand, the features of the diff that the user names or the diff shows. |
| Rewrite | By hand only: `yes` or `no` (default `no`). `yes` allows a re-cut across commit boundaries and `--force-with-lease` on an unmerged pull request branch, in section "Publish" only. A job never rewrites a published branch. |
| Delivery | `pr` or `commit`, as the caller passes it (the job's handoff `delivery`). Without one: `<plugin-root>/bin/cure-job config get handoff.delivery` (default `commit`). |

PR diff: the insertions plus deletions of `git diff --shortstat <base-ref>...<branch>`. It reads committed refs only, never the working tree.

Read a missing input from the context: the branch from `git -C <repo> rev-parse --abbrev-ref HEAD`, the base from the job's `base` or `gh pr view --repo <owner/repo> --json baseRefName`.
