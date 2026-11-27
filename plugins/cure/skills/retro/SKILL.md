---
description: Turn the retrospectives in ~/.claude/retros/ into GitHub issues and delete each retrospective once every proposal in it has a decision. Run by the user, never by a job. Use when the user asks to process, triage or apply retrospectives, or runs /cure:retro.
allowed-tools: Read, Grep, Glob, Bash
---

# Retro

Input: `~/.claude/retros/????-??-??-*.md`, written by `cure:goal`.

A retrospective has the sections Outcome, "Where it went wrong" (rows `W1…Wn`) and Proposed changes
(`| Target | Change | Evidence (Wn) | Expected effect |`). A legacy retrospective has a Measurements
section and free-form proposals.

| Target form | Meaning |
|---|---|
| `<plugin>:<path>` | A file in a plugin, for example `cure:skills/goal/rules.md` |
| `repo:<path>` | A file in the goal's own repository |
| `user:CLAUDE.md` | The user's global instructions |

Create nothing and delete nothing before step 6.

## 1. Collect

- List `~/.claude/retros/????-??-??-*.md`.
- Report the other files in one line and leave them.
- Run `cure-job list --json`. Its rows have `id` (`<ticket>-<repo>-<slug>`, or `<yymmdd>-<hhmm>-<repo>-<slug>` without a ticket), `state` and `dir`. A job matches a retrospective when its id ends in `-<repo>-<slug>`. For an id that `cure-job new` cut to 60 characters, the id holds, after the ticket or time part, a prefix of `<repo>`, a `-`, then a prefix of `<slug>`. Example: repo `video-core-firmware-images-and-more` and slug `report-pass-from-signal-and-more` give `abc-1-video-core-firmware-images-report-pass-from-signal-an`. The job is open in any state except `done`, `failed` or `abandoned`. Skip a retrospective whose job is open.

## 2. Read the proposals

- Read the Proposed changes table of each retrospective.
- Map a legacy proposal to a Target by judgement. Mark it `?` when unsure.

## 3. Merge and check

- Merge proposals with the same Target and intent across retrospectives. Keep every source in `Seen in`.
- Check each proposal against the current target file. If the file already holds the change, the status is `in <file>:<line>`.
- Check each proposal against `gh issue list --state all --limit 1000 --json number,title,state` of its repository. A match with an open issue is `open #N` and is dropped, not commented. A match with a closed issue is `closed #N`.

## 4. Resolve the repository

| Target | Repository |
|---|---|
| `<plugin>:` | Through the `installed_plugins.json` and `known_marketplaces.json` files of the Claude plugin directory |
| `repo:` | The origin of the goal's repository |
| `user:` | None. The user applies it by hand. |

## 5. Review

Show one table:

`| # | Target | Change | Seen in | Status | Proposed action |`

| Column | Value |
|---|---|
| Status | `new`, `open #N`, `closed #N` or `in <file>:<line>` |
| Proposed action | `create`, `drop` or `by hand` |

- List the retrospectives to be deleted below the table.
- Take overrides by row number, then ask for one confirmation.

## 6. Execute

- Create each accepted issue with `gh issue create`. The body is self-contained: copy the evidence, do not link to the retrospective.
- Delete a retrospective only when every proposal in it has an executed decision: issue created, dropped, or marked by hand.
- A failed `gh issue create` keeps the retrospectives that contain that proposal.
- Print the created issue numbers and the deleted files.
