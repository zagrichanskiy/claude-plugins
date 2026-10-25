# Short holds

`<plugin-root>` below is this file's path without its trailing `/skills/goal/short-holds.md`.

A short hold is a `device:*` or `build:*` resource. A job claims it for one step and releases it at
the end of the step. Repositories are not short holds: the handoff holds them until the job ends,
and `release` refuses them (exit 1).

| Item | Rule |
|---|---|
| Single claimant | One claimant per job: the session that dispatches agents. That is the orchestrator in Light and Full, and the worker in Solo. |
| Dispatched agents | A dispatched agent never runs `claim` or `release`. Claims are a set, not a count: an agent's `release` would end the claimant's hold. |
| When to claim | Before each bench step, and before each step that runs a command that takes `bitbake.lock` (`bitbake`, `devtool`, `kas`). The claimant claims before it dispatches an agent for the step. |
| What to claim | Every short hold the step needs, in one call per step, all or none: `<plugin-root>/bin/cure-job claim <id> --wait <short-hold.wait-seconds> device:bench build:<absolute path>`. When one resource is held by another job, none is granted. |
| `build:` name | The worker fills it at claim time: the absolute bitbake TOPDIR (the directory that holds `bitbake.lock`) of the build the step runs. The handoff never names a `build:` resource, because a handoff resource is held until the job ends. A relative path is refused. A symlink or `..` path is stored as its realpath. Equal names conflict; build directories do not nest. |
| One hold at a time | While the run holds a short hold, it releases that hold before it claims anything else. A claim that names a resource the run does not hold exits 1 with `release <held> first`. `claim --wait` of a repository exits 1. Name every resource of the step in the first claim. |
| Hold | Keep the holds across the consecutive commands of the step. Do not release and claim again between two bitbake commands: a waiter would enter mid-step. |
| When to release | At the end of the step, on success or failure, after the agent returns: `<plugin-root>/bin/cure-job release <id> <resource>`, once per resource. |
| Foreground | Run the claim in the foreground with a Bash timeout of 600000 ms (the tool default is 120000 ms, shorter than the `--wait` value). Never run it in the background. If the tool times out anyway, run `release` for every resource named in that claim before anything else, then claim again. |
| Wait per call | Read `short-hold.wait-seconds` once per run with `<plugin-root>/bin/cure-job config get short-hold.wait-seconds` (default 540) and pass it as `--wait`. Its ceiling of 540 is fixed. |
| Held by another job | `claim --wait` polls every 10 s, for at most the `--wait` seconds, and exits 0 when it holds every resource. On timeout it exits 1 with `error: <resource> is held by <holder id>` on stderr. Call it again. |
| Claim refused | Exit 1 at once, without waiting. Act on the Action column of the table below: most messages end the step as `failed:`, and the `release <held> first` refusal is retried after `release`. `--wait` outside 0..540 exits 2 (`invalid seconds` or `is outside 0..540`) and is also not retried. |
| Wait budget | Wait for short holds for at most `short-hold.wait-total-minutes` minutes in total over all calls (default 120; read it with `<plugin-root>/bin/cure-job config get short-hold.wait-total-minutes`). Each run starts a new budget: a resume after `needs-input:` is a new run. When the budget is spent, take the `needs-input:` exit with the question "short-hold timeout: <resource> held by <holder id>". |
| Foreign edits | Before each build claim, run `git -C <repo> status --porcelain` for each repository that another open job names in `<plugin-root>/bin/cure-job list --json`. Record each dirty one with that job's id: in the ledger in Light and Full, in the final message in Solo (Solo has no ledger). Other jobs' in-progress edits can enter this build through `EXTERNALSRC`. A build failure on another job's edits is then named before fix rounds are spent on it. Where verify allows, build the job's own recipes instead of the image. Name the foreign edits as the cause in the retrospective. |
| Scope | A short-hold claim counts only while its run is the latest run and `result.md` does not exist. A finish, a `needs-input` exit, a resume or a relaunch drops it. A forgotten `release` is bounded by the run. |

`claim` stderr messages (each starts with `error: `):

| Message | Meaning | Action |
|---|---|---|
| `<resource> is held by <holder id>` | Another job holds it | Wait again (see "Held by another job") |
| `job <id> is abandoned; claim needs a launched run` | Refusal | `failed:` |
| `job <id> has no launched run; claim needs a launched run` | Refusal | `failed:` |
| `job <id> has a result for run <n>; claim needs a running run` | Refusal | `failed:` |
| `job <id> is invalid: <problem>` or `claim refused: job <id> is invalid and may hold any resource; ...` | Invalid job: a failure, not a hold | `failed:` |
| `unknown job <id>: ... holds no handoff.md` | Wrong id | `failed:` |
| `job <id> holds <held>; release <held> first` | The run holds a short hold and named another resource | Release, then claim every resource of the step in one call |
| `<repo> is a repository; claim --wait accepts only device: and build:` | A repository was named with `--wait` | Claim only `device:` and `build:` with `--wait`, otherwise `failed:` |

`release` exits 0 whenever the job does not hold the resource after the call, so a retry is harmless.
It exits 1 for an unknown or invalid job, and for a repository name.
