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
| `--pr` | URL | A pull request was opened |
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

1. Skip clean-up. Keep the ledger and the working files.
2. Run `finish` with `--status needs-input`, one `--question` per question and `--kept` for each
   kept file.
3. Each question states the situation, the options, the consequence of each and a recommendation,
   for a reader who has not followed the run.
4. Send the message, then print the final message starting with `needs-input:`.

A later run continues from the ledger.

## Keep rules

- Keep the goal file, the retrospective and the backlog. List the retrospective with `--retro`.
- Never touch the job directory.
