# Dispatch fields: rarely used rows

## ticket-summary

Omit the key from the draft. With a `ticket`, read its title once now:

- A `KEY-N` ticket with `split.tracker` `clickup`: `mcp__clickup__clickup_get_task`, field `name`.
- Another `KEY-N` ticket: `mcp__atlassian__getJiraIssue`, field `summary`.
- A GitHub ticket: `gh issue view <N> --repo <owner/repo> --json title`.

Pass the title to `cure-job new` as `--ticket-summary`, in the form of "Writing the handoff" in `SKILL.md`. `cure-job new` writes the key. When the read fails, pass no title.

## base and delivery

Set them only when the user stated them. Set `base` also when the job is stacked on a predecessor's branch without `after`. Otherwise omit the key. `cure:goal` resolves an omitted `base` from the default branch of each repository. `delivery` is `commit` or `pr`; an omitted `delivery` comes from `handoff.delivery`.

## after

Set `after` only when this job builds on the result of an open job of the same stack (any state other than `done`, `failed` or `abandoned`). The value is that job's id, one only. Otherwise omit the key.

- A job stacked only because it edits the same files gets no `after`.
- Its `base` is the predecessor's branch.
- The repository resource runs the jobs in order. A failed predecessor does not close it.
- `cure-job new` refuses an id with no job.
- The successor stays `held` until the predecessor is `done`.

## Resource risk

Write one `## Settled` line per resource the user rated in the session, in the user's words, for example "Resource risk: bench is a test stand; any action on it is approved". Omit when the user said nothing.
