---
description: Create, find and retire working notes — the scratch files, research dumps, session handoffs and drafts that carry state until a real artifact exists. Gives them one home per repository, frontmatter that states their own end, and a sweep that deletes the ones a merged pull request or committed document has already superseded. Use when writing a scratch file, when asked to sweep or tidy working notes, or when a stale one turns up while doing something else.
allowed-tools: Read, Write, Edit, Grep, Glob, Bash
---

# Note

A working note carries state until something permanent holds it. Deleting it then is the job; the
rest of this skill exists to make that possible, because a note nobody can identify as temporary
never gets deleted.

The global rule in `~/.claude/CLAUDE.md` says *when* to delete. This says where notes live, how they
declare their own end, and how to find the ones already superseded.

## Where they live

**`.notes/` at the repository root. Never beside real documents.**

A working note sitting next to committed content is read as content. That is how a file whose own
first line says "nothing here is decided" ends up cited as a decision.

**Exclude it locally, not in `.gitignore`** — the exclusion is your working preference, not a fact
about the project, and `.gitignore` is shared:

```
grep -qxF '.notes/' "$(git rev-parse --git-dir)/info/exclude" 2>/dev/null ||
  echo '.notes/' >> "$(git rev-parse --git-dir)/info/exclude"
```

Outside a repository, use `.notes/` in the working directory just the same.

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

**`supersedes_when` is the field that matters.** It is written at creation, before anyone is
attached to the file, and it names the thing whose existence ends this note: a merged pull request,
a committed document, a decision recorded where the team looks. "When we're done" is not an answer —
name the artifact.

A note that cannot name what would replace it is not a working note. It is either content that
belongs in the repository proper, or nothing.

## Commands

| Command | Effect |
|---|---|
| `/note <title>` | Create one in `.notes/`, asking for `supersedes_when` if it is not obvious |
| `/note list` | Every working note in this repository, with age |
| `/note sweep` | Check each against its `supersedes_when`, and offer deletions |
| `/note resolve <name> <artifact>` | Record the artifact and delete the note |

## Sweeping

For each note with `status: working`, decide whether the artifact named in `supersedes_when` now
exists — look for it, do not guess. A merged pull request, a file in the tree, a section in a
committed document.

- **Exists, and covers everything the note held** — delete it. Say what went and what holds it now.
- **Exists, but part of the note never made it** — name that part, and offer to promote it or keep
  the note. Never delete an open question because most of the file is settled.
- **Does not exist** — leave it, and report the age.

**Report ages.** A working note older than thirty days whose artifact never appeared is usually
abandoned rather than pending; say so and ask.

## When one turns up on its own

Finding a stale working note while doing something else is worth one sentence: which artifact
superseded it, and an offer to delete. Do not silently leave it — the next reader takes it for
current.

## Never

- Delete a note the user wrote by hand without asking.
- Delete anything tracked by git without asking, whatever its frontmatter says.
- Move a tracked file into `.notes/` without asking — that is a change to the repository, not
  housekeeping.
- Add `.notes/` to a committed `.gitignore`.
