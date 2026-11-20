# Checks before launch

Run the Repository check before writing `<job>/goal.md`: the ledger path and the Permissions check depend on the first repository. Run the other checks after writing it. All run again on every wake before a launch. The Permissions check also runs before a resume whose permission mode changed. Fix a failed check, or ask about it in the question round, before launch.

| Check | How | On failure |
|---|---|---|
| Tools | Run each executable that work item 1's tool check names, with the check's command (for example `devicectl --help`). The tool `claude` counts as present without running it. | Install or fix it, or ask the user. After the user installs it, run the check again. |
| Permissions | Auto mode: for each classifier-gated action the goal needs (for example `git commit --amend`, a force-push, device power), read the permission rules the worker loads. When the goal's Rules state a non-auto permission mode: the same for every tool the mode does not pass, each needing an allow rule. Under `acceptEdits` these are Bash command prefixes and MCP tools. Under `default` they also include Edit and Write. | No rule allows the action or prefix: ask the user. |
| Repository | Compare the handoff's first `repos` entry with the repositories the Work items edit. | The first repository holds none of the Work's edits: ask the user. |
| Trust | Every work item that launches interactive or `--bg` `claude` (not `claude -p`) in a directory names it as a literal absolute path. Read `projects["<path>"].hasTrustDialogAccepted` in `~/.claude.json` for the path and each ancestor. | A path that is not literal, or no entry that is `true`: through `cure:goal`, rewrite the work item to a literal path under a trusted ancestor and move the directory there. Ask the user to trust it only for a fixed directory that exists. |
| Length | Run `wc -c <job>/goal.md`. | None. Report the count with the summary. |

## Permission rules the worker loads

The worker starts in the handoff's first repository. It loads:

- `~/.claude/settings.json`.
- The managed settings file. Linux: `/etc/claude-code/managed-settings.json`. macOS: `/Library/Application Support/ClaudeCode/managed-settings.json`.
- `.claude/settings.json` and `.claude/settings.local.json` of the handoff's first repository.
- The `--settings` rules that `cure-job launch` adds: `finish <id>`, `claim <id>`, `release <id>`, `config get`, `list`, `finish --help`, each on `<plugin-root>/bin/cure-job`.

An action counts as allowed only when an `allow` rule matches it and no `deny` or `ask` rule matches it. `Bash(<command prefix>:*)` matches a command by prefix. An MCP tool rule is `mcp__<server>__<tool>`.

## Check answers

Approval of an action in `goal.md`, or given in this session, does not reach the auto-mode classifier, so it does not pass the check.

Failed permission check:

| Answer | Effect |
|---|---|
| The user adds an allow rule | The check runs again. |
| Drop the action | Edit `goal.md` through `cure:goal`. The check runs again. |
| Launch anyway | Auto mode: the run may stop at `needs-input` when the classifier denies the action. Other modes: an unallowed tool opens a permission prompt and the job becomes `blocked` (`tell-blocked`). |

Leave auto mode (an agent's "no verdict"):

| Answer | Effect |
|---|---|
| `acceptEdits` (recommended) | File edits pass. Other tools need allow rules. |
| `default` | Every unapproved tool call stops the job. |
| Stay in auto mode | The run may stop at `needs-input` again. |

Write a mode the user chooses into the goal's Rules "Permission mode" line through `cure:goal` ("Answer and resume" step 1). Every later launch, resume and relaunch passes it.

Failed Repository check:

| Answer | Effect |
|---|---|
| Re-dispatch | Run `cure-job close <id>`, then Tell origin, kind `re-dispatch`. The origin session queues a new handoff with that repository first. |
| Start in the first repository anyway | Record the decision under Settled in `goal.md`. The check passes on later wakes. |
