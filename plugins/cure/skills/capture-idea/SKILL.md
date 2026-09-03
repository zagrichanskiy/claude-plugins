---
name: capture-idea
description: >
  Capture an idea, proposal, or design discussed in the current session as a
  structured "goal file" for later implementation. Invoke when the user says
  something like "save this idea", "capture this for later", "write this down",
  or "/cure:capture-idea" — typically after working through a design in
  conversation.
  Writes one markdown file per idea to ~/.claude/ideas/, in a form that a fresh
  session or the /goal command can pick up cold.
---

# Capture Idea

Turn an idea just discussed in this session into a self-contained goal file
under `~/.claude/ideas/`, so it can be implemented later without replaying the
conversation.

## When to use

The user wants to record an idea, design, or proposal for later — not implement
it now. Common phrasings: "save this idea", "capture this", "write this down for
later", "/cure:capture-idea". Often invoked right after reaching agreement on
a design in conversation.

## Steps

1. **Identify the idea.** Default to the most recently discussed proposal in
   this session. If the session covered several distinct ideas, ask the user
   which one (or capture each to its own file).

2. **Choose a slug.** Kebab-case, descriptive, stable — e.g.
   `agent-feedback-skill`. This becomes the filename `~/.claude/ideas/<slug>.md`.
   If a file with that slug already exists, read it and update it rather than
   creating a duplicate; append new detail instead of overwriting agreed points.

3. **Write the goal file** using the template below. Draw the content from the
   conversation, not from a fresh guess — the value is in preserving what was
   actually decided, including the reasoning and the parts left open.

4. **Report** the path written and a one-line summary. Do not start
   implementing unless the user asks.

## Goal file template

```markdown
# <Idea title>

- **Captured:** <today's date, YYYY-MM-DD>
- **Source session:** <session name if known, else "unnamed">
- **Status:** draft

## Problem

<What need or friction this addresses. Why it is worth doing.>

## Proposed approach

<The design agreed in conversation. Concrete enough to act on. Record the key
architectural decisions and the reasoning behind them, not just the conclusion.>

## Open decisions

<Unresolved forks, trade-offs deferred, or questions to settle before or during
implementation. Omit the section only if genuinely nothing is open.>

## Next steps

<The first concrete actions an implementer would take.>
```

## Notes

- Keep each idea in its own file. One file, one idea.
- Preserve rejected alternatives when they carry rationale — knowing why a path
  was not taken saves re-litigating it later.
- These are personal drafts; do not commit them to a project repo unless the
  user explicitly asks.
