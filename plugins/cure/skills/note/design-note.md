# Design note

A design note records a design worked out in the conversation, so a fresh session can implement it
without replaying the conversation. It is a working note in `.notes/<slug>.md`. It uses the five
frontmatter keys of a working note and no others. `supersedes_when` names the design document or the
implementing pull request.

```markdown
---
title: <Title>
status: working              # working | resolved
created: <YYYY-MM-DD>
supersedes_when: <the design document or the implementing pull request>
resolved_by:                 # the artifact, once it exists
---

# <Title>

## Problem

<The need or friction, and why it is worth doing.>

## Decisions

| Decision | Reason |
|---|---|
| <what was decided> | <why> |

## Rejected

| Alternative | Reason |
|---|---|
| <what was not chosen> | <why not> |

## Open decisions

<Unresolved forks and questions. Omit the section when none is open.>

## Next steps

1. <The first concrete action for an implementer.>
```

Rules:

- Write from the conversation, not from a fresh guess. Record what was decided and why.
- One idea per file. If the session covered several, ask which one, or write one file for each.
- The slug is kebab-case and stable. If `.notes/<slug>.md` exists, update it. Do not overwrite
  agreed Decisions or Rejected rows.
- Report the path and a one-line summary. Do not start implementing unless asked.
