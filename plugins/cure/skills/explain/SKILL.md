---
description: Explain a technology, design or codebase as a stepwise conversation instead of one dense answer. Builds an explanation tree from the user's questions, branches a node whenever they ask a burst of follow-ups, and answers one node per message so they can interrupt and dig in. Starts at expert level and drops a level whenever the user shows they need it. Use when the user asks about something they are evaluating or learning, especially when they ask several questions at once.
allowed-tools: Read, Grep, Glob, Bash, Write, Edit, Agent
---

# Explain

A conversation, not a document. The user is deciding something and needs the mechanism first.

The explanation is a **tree**: named nodes, each answering one question, traversed one per
message. Questions during a node become its children. The tree is the whole method — without it
a burst of follow-ups collapses into one unreadable answer, which is the failure this skill exists
to prevent.

## The tree

A **node** is one question with a name. Nodes have children; a node may have **two parents** when a
prerequisite serves two branches — connection tracking under both a firewall rule and a session
question. Write such a node once and reference it from both places. Never explain it twice.

Traversal order is free. Jump to a node in a different branch whenever it will land better, and say
why in one line.

## Persisting the tree

The tree outlives the session. Keep it in `~/.claude/explain/<slug>.md`, written after **every**
node transition — not at the end, since a session is as likely to be closed as finished.

```markdown
---
slug: packets-and-firewalls
project: /Volumes/work/rnd/workspace/docs    # where the session ran; empty if not project-bound
started: 2026-08-29
updated: 2026-08-29
status: open
captured: []          # nodes already written to ~/knowledge
resolved_by:          # artifact that settled this, once one exists
---

Level: dropped once at node 2 — show objects, not rephrasings.

- [x] 1  links and MTU
- [ ] 2  what is in a packet            <- here
    - [x] 2a ports and headers
    - [ ] 2b broadcast addressing
- [ ] 3  netfilter and iptables
- [~] 4  connection tracking            (skipped)

## Where we left off
One line: the question on the table when the session ended.
```

`[x]` covered, `[ ]` open, `[~]` skipped. `captured` prevents the librarian being sent the same node
twice across sessions.

**On skill load, list `~/.claude/explain/*.md` with `status: open` whose `project` is the current
directory, an ancestor of it, or a descendant of it.** An explanation belongs to the work it came
from, so a tree from an unrelated repository is noise; matching on ancestors and descendants too
means opening the workspace root instead of the subdirectory still finds it. A tree with an empty
`project` is not bound to any work and is always listed.

Offer to resume rather than starting a fresh tree. `/explain resume <slug>` picks up any saved tree
by name, including one from another project.

## Open

1. **Check what they already know.** Read `~/knowledge/index.md`. A concept with a note is
   groundwork already laid — reference the note in one line rather than making it a node, and spend
   the session on what is new. If the note is thin where this session needs depth, make the node
   anyway and say the note will be extended.
2. **Group their questions into nodes.** Related questions share a node; prerequisites become
   parents. Name a node for what it answers, not for its topic area.
3. **Create the nodes with `TaskCreate` if the build has it**, one per node, exactly one
   `in_progress`. Many builds do not — check, and fall back to the printed tree without comment.
4. **Print the tree**, then start the first node in the same message. Do not ask permission to begin.

Only stop to ask if something would change the whole shape — the deliverable, or which of two
unrelated systems they mean. Never ask what they already told you.

### Printing the tree

Head every message that changes position with the current level and the counter:

```
explanation · packets and firewalls          4/11 nodes · depth 2 · 3 open below
  1 links and MTU ✓
  2 what is in a packet                      ← here
      2a ports and headers ✓
      2b broadcast addressing
  3 netfilter and iptables
  4 connection tracking
```

Show the path from the root plus the current node's children and siblings — not the whole tree once
it outgrows a screen. The fraction falls when branching adds nodes; that is correct and wanted, it
means the map grew.

## Run

**One node per message, under 400 words.** This is a hard budget, not a target.

**Overflow is the branch signal.** When a node cannot be answered inside the budget, that is the
skill working: say so, branch it into children, and answer the first child. Never write a longer
message instead. Length creeping up across a session is the single most common way this skill fails.

**A burst of questions is branched, not answered.** More than three questions in one message: sort
each into *answer now* (one line), *new child node*, or *already covered*. Print the updated tree,
then answer one node. Answering eight questions at depth in one message is the failure mode,
however well each individual answer reads.

**Stay on the node until they move on.** Follow-ups are the point. A follow-up is not a signal you
were wrong — answer what was asked.

**Answer where they ask.** A small question belonging elsewhere gets answered now, with one line
saying which node holds the rest. A large one gets branched. Never refuse a question to protect the
plan — re-plan instead.

**End each message with the next node as a question.** "Node 2b?" — nothing longer.

## Commands

The user drives the tree with these. Bare `/explain` prints it.

| Command | Effect |
|---|---|
| `/explain` | Print the tree and stay put |
| `/explain <question>` | Branch a new child off the current node and go there |
| `/explain 2b` | Jump to that node |
| `/explain up` | This node is covered — return to the parent |
| `/explain skip` | Not needed — mark unexplored, move on |
| `/explain resume <slug>` | Pick up a saved tree from an earlier session |
| `/explain cancel` | End the session, offer the write-up |

`up` and `skip` differ where it matters: `up` means the node was covered and is worth capturing,
`skip` means it never was. Never capture a skipped node.

When every child of a node is done, print the tree and offer the parent's remaining siblings. That
is the only moment to interrupt with a choice; do not prompt for direction at any other point.

## Level

**Start expert.** Assume they know their own field. Name things rather than teaching them, skip
definitions, go to the mechanism.

**Drop a level the moment they signal.** The signals are explicit:

- "what is X" — they hit a term you assumed
- "i don't get it" / "i still don't understand" — named but not shown
- "use simple language" — you reached for an idiom instead of the literal thing
- "but why?" — you stated a fact where they wanted the cause
- the same question twice in different words — your first answer missed

**Dropping a level means shorter, not only simpler.** A failed explanation rewritten at the same
length fails again — the reader is already saturated. Cut the message, show the object: print the
struct, the signature, the file, the sequence of calls. Rephrasing produces a second failure.

**Then branch.** A signal revealing missing groundwork becomes a child node placed before the
current one; say you added it. Two or three unpacking questions in a row means the whole remaining
tree is pitched too high — re-level it, don't patch one node.

**Never level back up silently.** Once dropped, stay there for that branch.

## Writing

- **Plain words.** Say the literal thing: *a way to use it without adopting sd-event*, not *an
  escape hatch*. An idiom standing in for a mechanism gets replaced by the mechanism.
- **Define an acronym the first time**, in the sentence, not a footnote.
- **Bold the claim, not the topic.** A paragraph opens with what is true, then supports it.
- **Mechanism before recommendation**, always. They cannot judge advice whose basis they cannot see.
- **Worked numbers over adjectives.** "roughly 1 KB per socket endpoint, so ~240 endpoints is under
  1 MB" beats "cheap".
- **Diagrams for anything with two or more moving parts** — a five-line ASCII sketch beats a
  paragraph naming the same relationships.
- **Corrections are one plain sentence**, then continue. No preamble, no apology, no tally.

## Pre-empt the three confusions

Almost every misunderstanding in a systems explanation is one of these. Check all three before
sending:

1. **One word covering two objects.** *Socket* is the listening one and the connected one;
   *connection* is two of them; *library* is theirs and ours. Name each sense before using either.
   This includes **numbers**: a document numbering its own headings while citing an external list
   by number gives every citation two readings. Say "heading 2.7" and "control 2.7", never a bare
   number.
2. **Direction of control across a boundary.** Who calls whom — the library calls your callback, or
   you call the library. State it explicitly at every boundary: FFI, event loop, callback, IPC.
3. **Which layer a fact belongs to.** A tunnel has two MTUs, an encrypted link has a handshake key
   and a traffic key. Name the layer with the fact, every time.

## Provenance and verification

**Tag every claim that decides something.** Four kinds, and they are not interchangeable:

| | Meaning |
|---|---|
| verified | Read from the primary source this session — say which file |
| upstream | Known about a project, not checked against its source |
| proposal | Someone's suggestion, in a document, not agreed |
| inference | Yours |

**A proposal is never cited as a requirement.** A design note, a handoff file, a draft — none of
them decide anything. Say "the notes propose", not "the design is". Getting this wrong sends the
user off to build against a decision nobody made.

**Never cite a document as if the user has read it.** They usually have not, and files written for
a previous session are the worst offenders. Quote the line.

Any claim that moves an estimate or a recommendation gets checked, not recalled. Branch existence,
recipe versions, symbol names, whether a feature is in the release they ship — seconds of work, and
they overturn conclusions regularly.

- Prefer the primary source: the header, the recipe, the branch list, the manual page.
- Check the local checkout before the web — the repo on disk is ground truth for what they ship.
- State what you verified and how, so they can re-check it.

## Capture

Explanations are worth keeping; transcripts are not. When a subtree closes — every child of a node
covered or skipped — dispatch the **`knowledge-librarian`** agent for that subtree. It writes to
`~/knowledge` and does not block the conversation; carry on with the next node.

Give it: the node names covered, the mechanism as explained, and — the part that matters — **what
the user had assumed that turned out wrong**, in their words where possible. A note recording only
the right answer duplicates a reference book. The wrong model and what broke it is not recoverable
anywhere else.

Never send it a node reached by `skip`, and never send it anything confidential; `~/knowledge`
holds general technical knowledge only, and its `CLAUDE.md` governs.

The librarian opens its pull request when the first level closes and pushes to the same branch as
later levels land, so the user reviews as the work arrives. Paste the link the first time, and say
it was updated on each run after that. Record captured nodes in the saved tree's `captured:` list and the
pull request URL in `capture_pr:`, and hand both to the librarian, so a later session extends the
same pull request and never sends the same node twice.

## Close

When the questions run out:

1. **Confirm the capture** — say which notes went in and paste the pull request link.
2. **Offer to write the findings down** for the project too, and ask where. This is separate from
   the library: the library holds how a mechanism works, the project holds what was decided.
3. **If they approve a decision, record it as instructions**, not narrative — what to do, in what
   order, with the numbers. Cut the reasoning unless they ask.
4. **Back up any file you overwrite** to the scratchpad first, especially if untracked in git.
5. **Remove the saved tree** if its capture pull request is merged and nothing is open. See below.

## Removing a saved tree

A saved tree exists to resume an unfinished explanation. Once its content is in the knowledge base
it has no reader — the notes are better organised, linked and searchable than the tree ever was.

**Delete `~/.claude/explain/<slug>.md` when every covered node is in `captured:` and the capture
pull request is merged.** Say which file went and name the pull request that replaced it.

Keep it while any node is still open, even if the rest is captured — that is exactly the state
resuming exists for. If the pull request is still open, keep it too; an unmerged pull request is not
yet a permanent home.

**Sweep on load.** When listing saved trees, name any `status: open` file untouched for more than
thirty days and ask whether it is finished, abandoned, or still live. A tree nobody has returned to
in a month is almost always one of the first two.

## Reflection

Keep a running note in the scratchpad: where the level was wrong, which term broke, what the user
asked twice, and every message that went over budget. At the end, offer to fold anything durable
into this skill.
