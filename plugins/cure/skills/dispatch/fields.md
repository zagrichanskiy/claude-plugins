# Dispatch fields: rarely used rows

## ticket-summary

Omit the key from the draft. With a `ticket`, read its title once now:

- A `KEY-N` ticket with `split.tracker` `clickup`: `mcp__clickup__clickup_get_task`, field `name`.
- Another `KEY-N` ticket: `mcp__atlassian__getJiraIssue`, field `summary`.
- A GitHub ticket: `gh issue view <N> --repo <owner/repo> --json title`.

Pass the title to `cure-job new` as `--ticket-summary`, in the form of "Writing the handoff" in `SKILL.md`. `cure-job new` writes the key. When the read fails, pass no title.

## base and delivery

Set them only when the user stated them. Set `base` also when the job is stacked on a predecessor's branch without `after`. Otherwise omit the key. `cure:goal` resolves an omitted `base` from the branch checked out in the user's checkout under branch `current`, else from the default branch of each repository. `delivery` is `commit` or `pr`; an omitted `delivery` comes from `handoff.delivery`.

## after

Set `after` when this job builds on the result of an open job (any state other than `done`, `failed` or `abandoned`), or when it edits or may edit the same files as an open job and the user chose to stack it. The value is that job's id, one only. Otherwise omit the key.

- Overlap: for each open job in `<plugin-root>/bin/cure-job list --json`, read `handoff.md` in its `dir`. When its `repos` share a repository with this job and this job edits or may edit the same files as its `## Work`, name that job and ask the user one question: stack this job on it with `after`, or run both in parallel and fix conflicts later. With several such jobs, the stack option names the latest. When the user stacks it, write the Settled line `Stacked on <id>: overlapping files`; the job then gets its own branch by `handoff.branch`, and `after` only orders it and gives its base.
- Its `base` is the predecessor's branch.
- `cure-job new` refuses an id with no job.
- The successor stays `held` until the predecessor is `done`.

## Resource risk

Write one `## Settled` line per resource the user rated in the session, in the user's words, for example "Resource risk: bench is a test stand; any action on it is approved". Omit when the user said nothing.
