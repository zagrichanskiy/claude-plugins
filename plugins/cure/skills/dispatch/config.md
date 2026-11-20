# Dispatch configuration

The configuration file is `${CURE_JOB_CONFIG:-${XDG_CONFIG_HOME:-~/.config}/cure/config.json}`. One file serves all jobs. A missing file means the built-in defaults. The defaults live only in the key table of `config.py`. `config.example.json` in this directory is generated from that table and is never read at runtime.

Read a value with `<plugin-root>/bin/cure-job config get <key>`; it prints JSON. Never read the file.

## Config errors

A config error is a parse error, a bad value, an unknown key, a removed key, or a `config.json` at the old location `${CURE_JOB_ROOT:-~/.claude/cure}/config.json` while the new path is missing (`cure-job config init` moves it). The CLI then is in safe mode:

- A bad key takes its default. An unparseable file gives all defaults.
- `prune` removes no job and exits 1.
- `approve --by auto` exits 1.
- `next` exits 0 with a `config-error` element.

## Keys

| Key | Used for |
|---|---|
| `handoff.delivery` | `delivery`, when the user did not state it. |
| `handoff.branch` | Values: `new` (default), `current`, or a literal branch name. Not applied by dispatch: it omits `branch` unless the `ticket`, `branch` rule in `SKILL.md` sets it. `cure:goal` applies it when the handoff omits `branch` (see `skills/goal/job.md` Input). |
| `reviews.Solo`, `reviews.Light`, `reviews.Full` | Review rounds per tier; one round is one reviewer pass (bounds: Solo 0, Light at least 1, Full at least 2; defaults 0, 2, 3). `cure:goal` reads `reviews.<tier>` once with `cure-job config get reviews.<tier>` and writes the number into the goal as the round limit. Solo 0 means no review round. A repository's `CLAUDE.md` may set a higher Light count. |
| `split.limit` | Integer from 100 to 5000 (default 1200). The cap: the split threshold, the largest changed-line count of a part and the PR-diff threshold of the goal size check. |
| `split.factor` | Number from 1.0 to 1.9 (default 1.5). `cure:goal` uses it only for the overrun check: the job diff passed `split.factor` × the estimate. It does not change the cap. It stays below 2, because the failure exit of `skills/goal/job.md` fires at 2 × the estimate. |
| `split.tracker` | Where a ticket for split-off work is created. Values: `github` (default; an issue in the delivering repository, through `gh`), `jira` (through a Jira command or MCP tool of the dispatching session) or `clickup` (through the ClickUp MCP tools of the dispatching session). `cure:split` uses the ticket form to pick the tracker and this key only with no ticket; a `KEY-N` ticket is ClickUp when this key is `clickup`, else Jira. Its `tracker` agent runs `split.jira-command` when it has no Jira MCP tool. |
| `split.jira-command` | Shell command template with `<title>`, `<body>` and an optional `<project>` (the project key of the ticket of the job's branch) that creates a Jira ticket and prints its key (default empty). Used only by `cure:split` when `tracker` has no Jira MCP tool; `jira` there fails preflight while it is empty. |
| `band.tracker-url` | An https URL with `<key>` (default `https://ienso-team.atlassian.net/browse/<key>`). The job band links a `KEY-N` ticket to this URL with `<key>` replaced by the ticket. ClickUp: `https://app.clickup.com/t/<workspace-id>/<key>`. |
