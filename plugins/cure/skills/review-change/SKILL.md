---
description: Review a change with more than one agent without paying for the same reading twice: collect a source digest once, dispatch the reviewing agents against it in parallel, merge their findings into one report with a section per altitude. Use it whenever the user asks for a design, architecture or multi-agent review of a pull request, a branch, a pull request group or a change ("review this PR with the designer and architect", "do a design review of this branch", "review the change" on more than a handful of files), and whenever two or more of reviewer, designer and architect would otherwise each read the same tree. Prefer it to dispatching those agents directly.
argument-hint: "[target] [--with architect]"
allowed-tools: Read, Grep, Glob, Bash, Write, Edit, Agent
---

# Review change

Collect once, then judge in parallel. Assign no areas and forbid no files: each reviewer decides
what to open.

## 1. Fix the target

State in one line before dispatching: the base, the branches or pull requests, the repositories, the
token budget, and whether the target is a **C++ change**. Resolve it with
`git diff --stat <base>...HEAD`, `gh pr view`, `gh pr diff`. Never substitute a local `git diff` for
an unchecked-out pull request. Every agent inherits this boundary.

- A C++ change has at least one *Changed C++ file*, as `${CLAUDE_PLUGIN_ROOT}/agents/collector.md`
  *Gating signals* defines it. It runs step 3a; any other change runs step 3.
- Record `--with architect` when passed; step 3a uses it.
- Token budget: 400k tokens per agent per round unless the caller states another figure. When an
  agent's per-leg usage (step 5) nears it with findings open, stop the agent, take what it returned,
  and say so in the close-out.
- Find earlier review reports of the same target (under `.notes/`, a published report the user
  names, an earlier digest). Record each and the commits since. Do not pass their findings to the
  agents; step 4 uses them.
- For a C++ change, read `${CLAUDE_PLUGIN_ROOT}/skills/review-change/cpp-change.md` §Registration check
  before dispatching anything.

## 1a. Re-check mode

Skip the collector and dispatch straight to step 3 when the agents are resumed from the previous
round, or are fresh and the diff since the last round is 5 files and 200 lines or fewer. Read
`${CLAUDE_PLUGIN_ROOT}/skills/review-change/recheck.md` before dispatching in this mode. A fresh
agent over the threshold forces the full pipeline from step 2.

## 2. Collect once

Dispatch `collector` with the target and a digest path (default `.notes/<slug>-digest.md` at the
repository root, per the `note` skill). Wait for it.

Run it once per target. Re-run it only when the target changes materially, and say the digest is
stale. Skip it for a handful of files in one repository, never for a C++ change.

## 3. Judge in parallel

For a C++ change, dispatch by step 3a instead of this table. Otherwise dispatch the agents the
change warrants, in one message so they run concurrently:

| Agent | Dispatch it when |
|---|---|
| `reviewer` | Always. |
| `designer` | The change adds or reshapes a component, or changes class decomposition, an interface contract, a design pattern, an ownership model or an error strategy. |
| `architect` | The change touches a boundary, a resource budget, a deployment surface, or hardware, or introduces or changes an architectural pattern. |
| `security-expert` | The change touches authentication, keys, trust boundaries, or a network protocol. |
| `ui-reviewer`, `ux-reviewer` | The change has a user interface. |

Give each agent this brief and nothing that constrains its reading. `reviewer`, `security-expert`,
`designer`, `architect` and the `cg-*` agents hold `Write` for the report path only. Name each path
distinctly:

```
Target: <the boundary from step 1>
Digest: <path> — read it first; it is a map, not evidence. Cite the source for every finding.
Report path: .notes/<slug>-<agent>-r<N>-report.md — write your report there yourself; do not return it in full to the caller.
Token budget: <the figure from step 1>
Task: REVIEW. Decide for yourself which files to open.
```

- `ui-reviewer` and `ux-reviewer` hold no `Write`: omit the `Report path` line and add
  `Return your report in full in your reply.` Read the other reports from disk.
- Add project context if useful. Add no topics: no area, defect class or earlier finding to look at.

## 3a. C++ change: two waves

Read `${CLAUDE_PLUGIN_ROOT}/skills/review-change/cpp-change.md` before dispatching. It holds the
gating table, the wave briefs and the skip lines. Run wave 1, wait, then run wave 2 (`designer`).

## 4. Merge

Read `${CLAUDE_PLUGIN_ROOT}/skills/review-change/merge-rules.md` before merging. You may delegate
the assembly to a `general-purpose` agent, which holds `Read` on the source; brief it as
`merge-rules.md` §Delegating the merge states.

Check the assembled report against the rules before closing the round. Resume an agent that stopped
on a usage or rate limit with `SendMessage` once the limit resets; do not dispatch a new one.

## 5. Close the run

- State plainly, before the summary counts, whether the round passes the severity floor: it passes
  when no `MUST-FIX` or `SHOULD-CONSIDER` finding is open in any section. `NITPICK`s and
  `enhancement`s sit in `.notes/<slug>-backlog.md` and do not hold the round open.
- Report each agent's reading footer and per-leg token usage (for a resumed agent, the difference
  from its previous report, never the cumulative figure), and the number of agents dispatched. Compare
  the per-leg figure with the budget. Flag any agent at or over budget.
- The fix step commits each round with explicit paths, new files included, before the round closes.
  Record HEAD at the start of the round (before the fix commit) as `<last-round-ref>` for step 1a,
  and update `.notes/<slug>-ledger.md` with the round's finding ids and status.
- A fix that changes a rule beyond its finding needs a test in the same round. The fix brief tells
  the implementer to return such a change as a question, and states each finding's cause scope:
  local to the cited line, or also present elsewhere.
- Sweep the digest once the report is delivered, per the `note` skill. Persist a report the author
  works from over several sessions where the project keeps documents, and hand back the path.

## Never

- Never dispatch the same agent twice over one target for confidence. Dispatch a second kind
  of agent or verify the finding.
- Never merge the altitudes into one ranking.
- Never re-run the collector to answer one question.
- Never drop an earlier must-fix without checking it. Not raised this round is not resolved.
