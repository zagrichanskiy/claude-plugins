---
description: Explain a technology, design or codebase as a stepwise conversation instead of one dense answer. Builds an explanation tree from the user's questions, branches a node whenever they ask a burst of follow-ups, and answers one node per message so they can interrupt and dig in. Starts at expert level and drops a level whenever the user shows they need it. Use when the user asks about something they are evaluating or learning, especially when they ask several questions at once.
allowed-tools: Read, Grep, Glob, Bash, Write, Edit, Agent
---

# Explain

Run a conversation, not a document. The user is deciding something and needs the mechanism first.

The explanation is a tree of named nodes. Each node answers one question. Answer one node per message. Questions asked during a node become its children.

A node may have two parents when a prerequisite serves two branches. Write it once and reference it from both places. Never explain it twice.

Traversal order is free. Jump to a node in another branch when it lands better, and say why in one line.

## Persist the tree

Keep the tree in `~/.claude/explain/<slug>.md`. Write it after every node transition, not at the end.

Read `${CLAUDE_PLUGIN_ROOT}/skills/explain/tree-file.md` before the first write and when listing saved trees.

On skill load, list the open saved trees that belong to the current work, as that file describes. Offer to resume instead of starting a fresh tree. `/explain resume <slug>` picks up any saved tree by name, including one from another project.

## Open

1. Group the user's questions into nodes. Related questions share a node. Prerequisites become parents. Name a node for what it answers, not for its topic area.
2. Create one node per task with `TaskCreate` if the build has it, with exactly one `in_progress`. Otherwise use the printed tree, without comment.
3. Print the tree in the format of `tree-file.md` §Printed tree, then start the first node in the same message. Do not ask permission to begin.

Ask only when the answer changes the whole shape: the deliverable, or which of two unrelated systems they mean. Never ask what they already told you.

## Run

- Keep each message under 400 words. When a node does not fit, say so, branch it into children and answer the first child.
- More than three questions in one message: sort each into answer now (one line), new child node, or already covered. Print the updated tree, then answer one node.
- Stay on the node until the user moves on. A follow-up is not a signal that you were wrong.
- Answer a small question that belongs elsewhere now, with one line naming the node that holds the rest. Branch a large one. Never refuse a question to protect the plan.
- End each message with only the next node as a question: "Node 2b?".

## Commands

Bare `/explain` prints the tree.

| Command | Effect |
|---|---|
| `/explain` | Print the tree and stay put |
| `/explain <question>` | Branch a new child off the current node and go there |
| `/explain 2b` | Jump to that node |
| `/explain up` | Mark this node `[x]` covered and return to the parent |
| `/explain skip` | Mark this node `[~]` skipped and move on |
| `/explain resume <slug>` | Pick up a saved tree from an earlier session |
| `/explain cancel` | End the session, offer the write-up |

When every child of a node is done, print the tree and offer the parent's remaining siblings. Offer a choice at no other point.

## Level

Start at expert level. Name things, skip definitions, go to the mechanism.

Drop a level on any of these signals:

- "what is X": a term was assumed.
- "i don't get it" or "i still don't understand": it was named but not shown.
- "use simple language": an idiom replaced the literal thing.
- "but why?": a fact was stated where the cause was wanted.
- The same question twice in different words.

Dropping a level means a shorter message. Show the object instead of rephrasing: the struct, the signature, the file, the sequence of calls.

A signal that reveals missing groundwork becomes a child node placed before the current one. Say you added it. Two or three unpacking questions in a row mean the remaining tree is pitched too high: re-level the whole tree.

Once dropped, stay at that level for the rest of the branch. Never level back up silently.

## Write and verify

Read `${CLAUDE_PLUGIN_ROOT}/skills/explain/style.md` before the first answer. It holds the writing rules, the three confusions to check before sending, and the provenance tags (verified, upstream, proposal, inference) for every claim that decides something.

## Close

When the questions run out:

1. Offer to write the findings down for the project and ask where.
2. Record an approved decision as instructions: what to do, in what order, with the numbers. Cut the reasoning unless asked.
3. Back up any file you overwrite to the scratchpad first, especially one untracked in git.
4. Delete `~/.claude/explain/<slug>.md` when every node is covered or skipped, and say which file went. Keep it while any node is open.

## Reflection

Keep a running note in the scratchpad: where the level was wrong, which term broke, what the user asked twice, and each message over budget. At the end, offer to fold anything durable into this skill.
