# Dispatch split: tickets and writing

## Writing a split

Create the tickets, link them, rewrite the original ticket, then run `cure-job new` for each part in order, each with `after` set as in "Part handoffs" of `split.md`.

## Rewrite

Only with the effective `delivery: pr` and a session ticket: after the links, rewrite the description of the original ticket (part 1) to the scope that stays with part 1. Remove the moved scope.

- GitHub: read the body with `gh issue view <N> --repo <owner/repo> --json body`, then `gh issue edit <N> --repo <owner/repo> --body-file - <<'BODY'` with the remaining scope.
- Jira: read with `mcp__atlassian__getJiraIssue` or the session's Jira command, then edit with `mcp__atlassian__editJiraIssue` or the Jira command.
- ClickUp: read with `mcp__clickup__clickup_get_task`, then edit the description with `mcp__clickup__clickup_update_task`.

A failed link or rewrite is reported and the split continues. The report carries the original body.

## Tickets

Only with the effective `delivery: pr` and a split. Create tickets for parts 2 to n; part 1 keeps the original ticket. `<owner/repo>` comes from an `owner/repo#N` or URL ticket, else from the remote of the delivering repository. Pass it as `--repo` to every `gh` command. Before the first create, with `split.tracker` `github`, run `gh auth status` and `gh repo view <owner/repo> --json hasIssuesEnabled`. The first row that matches applies:

| Case | Action |
|---|---|
| `split.tracker` is `github` (default), `gh auth status` succeeds, and the session ticket is `#N`, `owner/repo#N` or a github.com issue URL, or there is none and `hasIssuesEnabled` is true for the delivering repository | `gh issue create --repo <owner/repo> --title "<outcome of the part>" --body-file - <<'BODY'`. The body is complete on its own: what the part does, its scope (commands, options, files, formats) and its acceptance criteria. It has no "Split from" line and no reference to another ticket. GitHub carries no link between the tickets. |
| `split.tracker` is `jira` and the session has a Jira command or MCP tool | Create each ticket with the session's Jira command or MCP tool. The project comes from the session ticket. The description follows the same rule. A Jira issue link carries the relation. |
| `split.tracker` is `clickup` and the session has the ClickUp MCP tools | Create each ticket with `mcp__clickup__clickup_create_task` in the list of the session ticket. The description follows the same rule. A ClickUp dependency (`mcp__clickup__clickup_add_task_dependency`) carries the relation. |
| No tracker the skill can write to, `gh auth status` fails, or issues are disabled (checked before any create) | Create no ticket and do not split: write one handoff with the Estimate line, as the no-usable-tracker rule in `split.md` says. The report names the check. The skill never logs in and never reads or stores a token. |
| A create or `cure-job new` fails after the checks above passed | Stop. Tell the user the ids of the tickets and jobs already created. Part 1 is queued and the dispatcher may launch it on its next wake or at once. Parts after part 1 wait on their `after:` chain. The user closes the created jobs with `cure-job close <id>`; for a running job, `cure-job stop <id>` first. |
