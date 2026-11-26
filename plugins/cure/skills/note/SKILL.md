---
description: Create, find and retire working notes — the scratch files, research dumps, session handoffs and drafts that carry state until a real artifact exists. Gives them one home per repository, frontmatter that states their own end, and a sweep that deletes the ones a merged pull request or committed document has already superseded. Also writes design notes (problem, decisions, rejected, open, next steps). Use when writing a scratch file, when asked to sweep or tidy working notes, when asked to "save this idea", "capture this for later" or "write this design down", or when a stale one turns up while doing something else.
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
---

# Note

A working note carries state until something permanent holds it, then it is deleted. When to
delete: the global rule in `~/.claude/CLAUDE.md`.

## Where they live

**`.notes/` at the repository root. Never beside real documents.**

**Exclude it locally, not in `.gitignore`**:

```
grep -qxF '.notes/' "$(git rev-parse --git-path info/exclude)" 2>/dev/null ||
  echo '.notes/' >> "$(git rev-parse --git-path info/exclude)"
```

Outside a repository, use `.notes/` in the working directory.

## Anatomy

```markdown
---
title: Link and provisioning options
status: working              # working | resolved
created: 2026-08-29
supersedes_when: the architecture document for the radio link is committed
resolved_by:                 # the artifact, once it exists
---
```

**`supersedes_when`** is written at creation. It names the artifact whose existence ends the note: a
merged pull request, a committed document, a decision recorded where the team looks. "When we're
done" is not an answer.

A note that cannot name its replacement is not a working note. It is content that belongs in the
repository, or nothing.

## Design note

Read `${CLAUDE_PLUGIN_ROOT}/skills/note/design-note.md` before writing a design note. It holds the template and the writing rules.

## Commands

| Command | Effect |
|---|---|
| `/note <title>` | Create one in `.notes/`, asking for `supersedes_when` if it is not obvious |
| `/note design <title>` | Create a design note in `.notes/` from the conversation (see Design note) |
| `/note list` | Every working note in this repository, with age |
| `/note sweep` | Check each against its `supersedes_when`, and offer deletions |
| `/note resolve <name> <artifact>` | Record the artifact and delete the note |

## Sweeping

For each note with `status: working`, decide whether the artifact named in `supersedes_when` now
exists — look for it, do not guess. A merged pull request, a file in the tree, a section in a
committed document.

- **Exists, and covers everything the note held**: delete it. Say what went and what holds it now.
- **Exists, but part of the note never made it**: name that part, and offer to promote it or keep
  the note. Never delete an open question because most of the file is settled.
- **Design note**: a note with both a `## Decisions` and a `## Rejected` heading. Other notes
  follow the rules above. A design note follows the same outcome rules. These tests decide
  whether it is covered.
  - Covered by a document: every Decisions row, Rejected row and open decision is in the document.
  - Covered by a merged pull request: every Decisions row is in the diff, body or commits. Every
    Rejected row and open decision is in the body or a committed document.
  - A row or open decision that is not there is the part that never made it. Keep the note and
    list the missing rows.
- **Does not exist**: leave it, and report the age.

**Report ages.** A working note older than thirty days whose artifact never appeared is probably
abandoned; say so and ask.

## When one turns up on its own

When you find a stale working note while doing something else, say in one sentence which artifact
superseded it and offer to delete it.

## Never

- Delete a note the user wrote by hand without asking.
- Delete anything tracked by git without asking, whatever its frontmatter says.
- Move a tracked file into `.notes/` without asking — that is a change to the repository, not
  housekeeping.
- Add `.notes/` to a committed `.gitignore`.
