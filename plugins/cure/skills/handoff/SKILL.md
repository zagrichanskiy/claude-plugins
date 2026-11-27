---
name: handoff
description: Write the session handoff as a cure:note working note before the user runs /clear, so the next session can continue without this conversation. Started only by the user, as /cure:handoff.
allowed-tools: Read, Write, Edit, Glob, Bash
disable-model-invocation: true
---

# Handoff

Read `${CLAUDE_PLUGIN_ROOT}/skills/note/SKILL.md` and follow it for the note home, the frontmatter
and the sweep rules. Do not restate them here.

## Steps

1. Find the handoff file. When the session started from a handoff (a "continue from <path>"
   message or a handoff file the user named), update that file in place. Otherwise create a
   working note by the note rules read above. Its `supersedes_when` names the artifact that ends
   the work, such as the pull request that merges it.
2. Write what the next session needs to continue without this conversation:
   - **Objective**: what the work is for.
   - **Done**: each finished item with its link or hash: commits, pull requests, issues.
   - **Decisions**: each decision taken, with its reason in one line.
   - **Open questions**: each question not yet answered.
   - **Next step**: the one action to start with.
3. When updating, keep the file's existing structure, frontmatter and earlier content that is
   still true, including sections another skill owns. Add or refresh only the five items above.
   Move finished items to Done and remove answered questions. When the file has no note
   frontmatter, add `status` and `supersedes_when` as the note skill defines them.
4. Reply with the handoff path and this line, ready to paste after `/clear`:

   `continue from <path>`

This skill cannot run `/clear`. The user runs it.
