---
description: Review a change with more than one agent without paying for the same reading twice — run the collector once to produce a source digest, dispatch the reviewing agents against that digest in parallel, then merge their findings into one report with a section per altitude. Use it whenever the user asks, in any words, for a design, architecture or multi-agent review of a pull request, a branch, a pull request group or a change ("review this PR with the designer and architect", "do a design review of this branch", "review the change" on more than a handful of files), and whenever two or more of reviewer, designer and architect would otherwise each read the same tree. Prefer it over dispatching those agents directly.
allowed-tools: Read, Grep, Glob, Bash, Write, Edit, Agent
---

# Review change

Two advisory agents reviewing one pull request group independently cost 4.4 M weighted input tokens
across 249 requests, and six of their findings were the same finding reached twice. Neither agent
was wrong. The cost was structural: each ran its own collection pass over the same source before it
judged anything.

This skill separates collection from judgement. Collection happens once, cheaply, and produces an
artifact. Judgement happens in parallel against that artifact.

**It does not divide the source between the agents.** Each reviewer still decides for itself what to
open; the digest makes that decision informed rather than exhaustive. Assigned areas and forbidden
files would trade a cost problem for a coverage problem, and the defects worth finding are the ones
that cross an area.

## The pipeline

### 1. Fix the target

State it in one line before dispatching anything: the base, the branches or pull requests, the
repositories. Resolve it with `git diff --stat <base>...HEAD`, `gh pr view`, `gh pr diff`. Every
agent in the run inherits this boundary, so it is written once here rather than re-derived five
times.

Also find earlier review reports of the same target: a report or handoff under `.notes/`, a
published report the user names, an earlier digest. Record each one and the commits that landed
since it. Do not pass their findings to the agents (step 3 forbids topics); the merge uses them in
step 4.

### 2. Collect once

Dispatch `collector` with the target and a digest path — `.notes/<slug>-digest.md` at the repository
root by default, per the `note` skill. Wait for it. It returns the path, the totals and its verbatim
shortlist.

Run it exactly once per target. If the target changes materially mid-review, the digest is stale:
say so and re-run it, rather than letting reviewers work from a map of a different change.

For a change of a handful of files, skip this step and dispatch the reviewers directly. The digest
earns its cost when more than one agent reads, or when the target spans repositories.

### 3. Judge in parallel

Dispatch the agents the change warrants, **in one message so they run concurrently**:

| Agent | Dispatch it when |
|---|---|
| `reviewer` | Always. Correctness, convention, safety, test coverage. |
| `designer` | The change adds or reshapes a component: class decomposition, interface contracts and completeness, design patterns, ownership model, error strategy. |
| `architect` | The change touches a boundary, a resource budget, a deployment surface, or hardware; architectural patterns. |
| `security-expert` | The change touches authentication, keys, trust boundaries, or a network protocol. |
| `ui-reviewer`, `ux-reviewer` | The change has a user interface. |

Give each the same three things and nothing that constrains its reading:

```
Target: <the boundary from step 1>
Digest: <path> — read it first; it is a map, not evidence. Cite the source for every finding.
Task: REVIEW. Decide for yourself which files to open.
```

Project context (the platform, the hardware, where the conventions live) may be added. **Topics may
not.** Each agent's checklist already defines its work; a brief that asks `designer` to hunt
lifetime bugs, or `architect` to judge class structure, pulls the agent to another agent's altitude
and displaces the work only it does. In the review this skill was built from, a brief of that kind
turned every one of the designer's must-fix findings into a behaviour bug.

### 4. Merge

The agents return independently; the report is yours to assemble. **It has one section per
altitude, not one global ranking**: correctness (`reviewer`), system (`architect`), design
(`designer`), and any other agent dispatched. Each section keeps its own `MUST-FIX`,
`SHOULD-CONSIDER`, `NITPICK` order, by that agent's severity definitions.

A single global ranking was tried and failed: behaviour defects outrank structural ones on
immediacy, so every design finding sank to a one-line bullet at the bottom and its proposed
interfaces were cut. The structural findings were the part of the review no other agent could have
produced.

- **Every section gets the same depth.** A design finding carries its proposed types, declarations
  and diagram as fully as a correctness finding carries its failing scenario and code excerpt.
  Never compress one altitude to make room for another; if the report is too long, cut nitpicks in
  every section.
- **Carry the assessments through.** The designer's structure assessment and pattern assessment,
  and the architect's component and boundary assessment and pattern assessment, go into their
  sections verbatim or as tables — they are deliverables, not preamble.
- **One defect, one entry.** When two agents raise the same defect, report it once, in the
  section of the altitude it belongs to, and record that both reached it independently.
  Agreement is a confidence signal, **not a rank boost**: agents at different altitudes can only
  overlap on behaviour, so boosting agreement would promote behaviour over structure again.
- **Keep the evidence.** Every entry keeps its `path:line` and its concrete failing scenario or
  forces. Drop the reasoning and the entry becomes an assertion the author cannot act on.
- **Keep the suggested change.** Proposed decompositions, interface declarations and pattern
  recommendations are the designer's and architect's deliverable; a finding reduced to its
  diagnosis loses the part the author asked for.
- **State disagreements as disagreements.** Where two agents recommend incompatible changes, give
  both with their tradeoffs and say which you would take first. Do not average them.
- **Open with the first thing to address in each section**, then one line on the order across
  sections. Summary counts, if any, count every section.
- **Carry the open questions through.** A question an agent could not answer is not noise; it is
  work for the author.
- **Account for every earlier finding.** When step 1 found an earlier report, add a carry-over
  table: each earlier finding is *re-raised* (with its new ID), *resolved* (with the commit), or
  *not raised*. Re-check every must-fix that was not raised against the source yourself before you
  drop it. If it still holds, keep it in its altitude's section, marked as carried by the merging
  session. Independent agents drop findings between rounds; on unchanged code a must-fix that
  disappears is a miss, not a fix.

An agent that stops on a usage or rate limit has not finished. Resume that same agent with
`SendMessage` once the limit resets; it keeps its context and its reading. Do not dispatch a new
one: that pays for the reading again and counts as a second agent over the target.

### 5. Close the run

- Report the run cost: each agent's reading footer, and the number of agents dispatched.
- Give the digest a `supersedes_when` that names the report, and sweep it once the report is
  delivered — see the `note` skill.
- If the report is large enough that the author will work from it over several sessions, persist it
  where the project keeps documents and hand back the path, not the whole text.

## Never

- **Never dispatch the same agent twice over one target** to raise confidence. Dispatch a second
  *kind* of agent, or verify the specific finding.
- **Never assign files or areas to a reviewing agent.** State the target; let it choose.
- **Never brief an agent with another agent's topics.** Context yes; topics no.
- **Never merge the altitudes into one ranking.** One section per altitude, each at full depth.
- **Never let the digest be the evidence.** A finding cited to the digest instead of the source is
  unverified, and the digest was written by an agent that was told not to judge.
- **Never re-run the collector to answer one question.** Read the file.
- **Never drop an earlier must-fix without checking it.** Not raised this round is not resolved.
