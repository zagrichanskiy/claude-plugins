# Saved tree file

Path: `~/.claude/explain/<slug>.md`.

```markdown
---
slug: packets-and-firewalls
project: /Volumes/work/rnd/workspace/docs    # where the session ran; empty if not project-bound
started: 2026-08-29
updated: 2026-08-29
status: open
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

`[x]` covered, `[ ]` open, `[~]` skipped.

## Listing on load

- List the files with `status: open` whose `project` is the current directory, an ancestor of it or a descendant of it.
- List a file with an empty `project` always.
- Name each `status: open` file untouched for more than thirty days. Ask whether it is finished, abandoned or still live.

## Printed tree

Head every message that changes position with the level and the counter.

```
explanation · packets and firewalls          4/11 nodes · depth 2 · 3 open below
  1 links and MTU ✓
  2 what is in a packet                      ← here
      2a ports and headers ✓
      2b broadcast addressing
  3 netfilter and iptables
  4 connection tracking
```

Show the path from the root plus the current node's children and siblings once the tree outgrows a screen. The fraction falls when branching adds nodes.
