---
description: Turn the retrospectives in ~/.claude/retros/ into GitHub issues and delete each retrospective once every proposal in it has a decision. Run by the user, never by a job. Use when the user asks to process, triage or apply retrospectives, or runs /cure:retro.
allowed-tools: Read, Grep, Glob, Bash
---

# Retro

Input: `~/.claude/retros/????-??-??-*.md`, written by `cure:goal`. Sizing data: `~/.claude/retros/stats.md`.

A retrospective has the sections Outcome, "Where it went wrong" (rows `W1…Wn`) and Proposed changes
(`| Target | Change | Evidence (Wn) | Expected effect |`). A legacy retrospective has a Measurements
section and free-form proposals.

| Target form | Meaning |
|---|---|
| `<plugin>:<path>` | A file in a plugin, for example `cure:skills/goal/rules.md` |
| `repo:<path>` | A file in the goal's own repository |
| `user:CLAUDE.md` | The user's global instructions |

Create nothing and delete nothing before step 7.

## 1. Collect

- List `~/.claude/retros/????-??-??-*.md`.
- Report the other files in one line and leave them.
- Run `cure-job list --json`. Its rows have `id` (`<yymmdd>-<hhmm>-<repo>-<slug>`), `state` and `dir`. A job matches a retrospective when its id ends in `-<repo>-<slug>`. The job is open in any state except `done`, `failed` or `abandoned`. Skip a retrospective whose job is open.

## 2. Backfill stats

- A row matches a retrospective when `<date>-<repo>-<slug>` of the row, joined with `-`, equals the file name without `.md`. Repo names contain hyphens, so do not split the file name.
- For each retrospective that has a Measurements section and no row in `stats.md`, append a row with the command of `${CLAUDE_PLUGIN_ROOT}/skills/goal/rules.md` "All tiers". Read the values from the Measurements section. Use `-` for an unknown value. Take the repo from the retrospective's content, and ask the user when it is unclear.
- A retrospective without Measurements gets no row.

## 3. Read the proposals

- Read the Proposed changes table of each retrospective.
- Map a legacy proposal to a Target by judgement. Mark it `?` when unsure.

## 4. Merge and check

- Merge proposals with the same Target and intent across retrospectives. Keep every source in `Seen in`.
- Check each proposal against the current target file. If the file already holds the change, the status is `in <file>:<line>`.
- Check each proposal against `gh issue list --state all --limit 1000 --json number,title,state` of its repository. A match with an open issue is `open #N` and is dropped, not commented. A match with a closed issue is `closed #N`.

## 5. Resolve the repository

| Target | Repository |
|---|---|
| `<plugin>:` | Through the `installed_plugins.json` and `known_marketplaces.json` files of the Claude plugin directory |
| `repo:` | The origin of the goal's repository |
| `user:` | None. The user applies it by hand. |

## 6. Review

Show one table:

`| # | Target | Change | Seen in | Status | Proposed action |`

| Column | Value |
|---|---|
| Status | `new`, `open #N`, `closed #N` or `in <file>:<line>` |
| Proposed action | `create`, `drop` or `by hand` |

- List the retrospectives to be deleted below the table.
- Take overrides by row number, then ask for one confirmation.

## 7. Execute

- Create each accepted issue with `gh issue create`. The body is self-contained: copy the evidence, do not link to the retrospective.
- Delete a retrospective only when both hold:
  - Its `stats.md` row exists (matched as in step 2), or it had no Measurements section.
  - Every proposal in it has an executed decision: issue created, dropped, or marked by hand.
- A failed `gh issue create` keeps the retrospectives that contain that proposal.
- Print the created issue numbers and the deleted files.
