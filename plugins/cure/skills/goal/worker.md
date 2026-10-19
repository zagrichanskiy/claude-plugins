# Worker exit protocol

A job goal file points here. Read this file before work item 1, and again after a context
compaction and before an exit. The goal file names the job id (`<id>`) and the dispatcher's session
name. The exit clauses and done-when items are in the goal file; this file says how to carry them
out.

`<plugin-root>` below is this file's path without its trailing `/skills/goal/worker.md`.

## Every exit, in order

1. Run `<plugin-root>/bin/cure-job finish <id> --status <status>` with the options below. Never
   write `result.md` yourself.
2. Send `job <id>` to the dispatcher session with `SendMessage`.
3. Print the final message.

The `finish` command, its output and its exit code, and the `SendMessage` or its error, must be in
the transcript before the final message. If `finish` exits non-zero, run it once more. If it fails
again, take the `failed:` exit without the `finish` report.

## `finish` options

| Option | Value | Use |
|---|---|---|
| `--status` | `done`, `failed` or `needs-input` | Always |
| `--unproven` | `N[,N...]`, done-when numbers | `done` with an item whose proof is unavailable |
| `--question` | text, repeatable | `needs-input`, one per question |
| `--retro` | path | The retrospective, when one was written |
| `--pr` | full URL, repeatable | One per pull request on the job's branch |
| `--kept` | path, repeatable | Each file left in the repository |

Each text value (`--question`, `--retro`, `--pr`, `--kept`) is one line. A long question stays one
line, its parts separated by `; `. Exit 2 means the arguments are wrong: fix them before the retry,
and do not repeat the same command.

## Final message

- It restates each done-when item with its evidence.
- An item is unproven only when its proof is unavailable to the worker (a device, a login, a manual
  check), never when its check ran and failed. Give a reason for each unproven item.
- `failed:` and `needs-input:` messages start with that word.

## `needs-input:`

1. Skip clean-up. Keep the ledger and the working files. Keep the session: do not stop it.
2. Run `finish` with `--status needs-input`, one `--question` per question and `--kept` for each
   kept file.
3. Send the message, then print the final message starting with `needs-input:`.

The dispatcher resumes this session after the user answers. It adds the answers to the goal file
under Settled and sets the goal again with `/goal @<goal file>`. After the resume:

1. Read this file and the goal file again.
2. Take the answers from Settled. The questions of the earlier `needs-input:` exit are closed.
3. Continue from the ledger, at the work item that stopped.

The resume is a new run in this session. Its exit follows "Every exit, in order" again. When the
session is gone, the dispatcher launches a new run in a new session. It also continues from the
ledger.

## Short holds

A short hold is a `device:*` or `build:*` resource. A job claims it for one step and releases it at
the end of the step. Repositories are not short holds: the handoff holds them until the job ends,
and `release` refuses them (exit 1).

| Item | Rule |
|---|---|
| Single claimant | One claimant per job: the session that dispatches agents. That is the orchestrator in Light and Full, and the worker in Solo. |
| Dispatched agents | A dispatched agent never runs `claim` or `release`. Claims are a set, not a count: an agent's `release` would end the claimant's hold. |
| When to claim | Before each bench step, and before each step that runs a command that takes `bitbake.lock` (`bitbake`, `devtool`, `kas`). The claimant claims before it dispatches an agent for the step. |
| What to claim | Every short hold the step needs, in one call: `<plugin-root>/bin/cure-job claim <id> --wait 540 device:bench build:<absolute path>`. |
| Hold | Keep the holds across the consecutive commands of the step. Do not release and claim again between two bitbake commands: a waiter would enter mid-step. |
| When to release | At the end of the step, on success or failure, after the agent returns: `<plugin-root>/bin/cure-job release <id> <resource>`, once per resource. |
| Held by another job | `claim --wait` polls every 10 s, for at most 540 s, and exits 0 when it holds every resource. On timeout it exits 1 `ResourceHeld`, naming the resource and its holder. Call it again. |
| Claim refused | `claim` exits 1 without waiting when the job has no launched run, is abandoned, or has a result for its run (`result.md` exists or is archived). `--wait` outside 0..540 exits 2. Do not retry either: report it as `failed:`. |
| Wait budget | Wait for short holds for at most 120 minutes in total over all calls (`short-hold.wait-total-minutes`). Then take the `needs-input:` exit with the question "short-hold timeout: <resource> held by <holder id>". |
| Foreign edits | Before each build claim, run `git -C <repo> status --porcelain` for each repository that another open job names in `cure-job list --json`. Record each dirty one with that job's id: in the ledger in Light and Full, in the final message in Solo (Solo has no ledger). A build failure on another job's edits is then named before fix rounds are spent on it. |
| Scope | A short-hold claim counts only while its run is the latest run and `result.md` does not exist. A finish, a `needs-input` exit, a resume or a relaunch drops it. A forgotten `release` is bounded by the run. |

`release` exits 0 whenever the job does not hold the resource after the call, so a retry is harmless.
It exits 1 for an unknown or invalid job, and for a repository name.

## Keep rules

- Keep the goal file, the retrospective and the backlog. List the retrospective with `--retro`.
- Never touch the job directory.
