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
step 4. Step 1a is the one exception: re-check mode passes the open ledger ids, not the findings
themselves.

**Set the token budget for the round** before dispatching anything: 400k tokens per agent per
round, unless the caller states a different figure. State the figure in the same line as the
target. If an agent's per-leg usage (not its cumulative context — see step 5) is near the budget
with findings still open, stop it, take what it returned, and say so in the close-out rather than
letting it run unbounded.

### 1a. Re-check mode

Skip the collector and dispatch straight to step 3 when both hold:

- The diff since the last round touches 5 files or fewer, and 200 changed lines or fewer
  (`git diff --stat <last-round-ref>..HEAD`).
- The same agents from the previous round are being resumed, not freshly dispatched.

In that case, give each resumed agent the ledger ids still open, from `.notes/<slug>-ledger.md`,
and a diff range (`git diff <last-round-ref>..HEAD`) instead of a digest; do not re-run the
collector to produce one. A diff over the threshold, or a change of agents, forces the full
pipeline from step 2. The fix step commits each round with explicit paths, new files included,
before the round closes; that commit is the next `<last-round-ref>` — see step 5. `git diff` on
an uncommitted round misses untracked files, so a round is not closed until it is committed.

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

Give each the same things and nothing that constrains its reading. `reviewer`, `security-expert`,
`designer` and `architect` hold `Write` for this purpose only: the report path named below, under
`.notes/`, nothing else:

```
Target: <the boundary from step 1>
Digest: <path> — read it first; it is a map, not evidence. Cite the source for every finding.
Report path: .notes/<slug>-<agent>-r<N>-report.md — write your report there yourself; do not return it in full to the caller.
Token budget: <the figure from step 1>
Task: REVIEW. Decide for yourself which files to open.
```

`ui-reviewer` and `ux-reviewer` hold no `Write`. Give them the same brief without the `Report path`
line, and add instead: `Return your report in full in your reply.`

Name each agent's path distinctly (its own slug and round number) so two agents, and two rounds,
never collide. The orchestrator reads the written report from disk in step 4 for the agents that
hold `Write`; for `ui-reviewer` and `ux-reviewer` it reads the report from their return message
instead.

Project context (the platform, the hardware, where the conventions live) may be added. **Topics may
not.** Each agent's checklist already defines its work; a brief that asks `designer` to hunt
lifetime bugs, or `architect` to judge class structure, pulls the agent to another agent's altitude
and displaces the work only it does. In the review this skill was built from, a brief of that kind
turned every one of the designer's must-fix findings into a behaviour bug.

### 4. Merge

The agents return independently; the report is yours to assemble. **It has one section per
altitude, not one global ranking**: correctness (`reviewer`), system (`architect`), design
(`designer`), and any other agent dispatched. Each section keeps its own `MUST-FIX` and
`SHOULD-CONSIDER` order, by that agent's severity definitions; `NITPICK` findings do not stay in
the section body — see below.

`security-expert` grades `critical`, `high`, `medium`, `low`, and an overall verdict of `CHANGES
REQUIRED` or `SATISFIED`, not the four tags below directly. Map them when merging: `critical` and
`high` to `MUST-FIX`, `medium` to `SHOULD-CONSIDER`, `low` to `NITPICK`, and a verdict of `CHANGES
REQUIRED` to the round not passing the severity floor (`NOT SATISFIED`).

**Triage every finding into exactly one of four tags.** `MUST-FIX`, `SHOULD-CONSIDER`, and
`NITPICK` are severities, per the dispatched agent's own definitions (mapped for `security-expert`
above). `enhancement` is a separate tag, not a severity: it marks a proposal for new behaviour
rather than a defect in the change under review. Carry the `enhancement` tag from the agent that
raised the finding; the merge never assigns it to a finding the agent tagged with a severity
instead — recasting a defect as an enhancement removes it from the severity floor, and that call
belongs to the agent that read the source, not to the orchestrator.

Route every `NITPICK` and every `enhancement` to `.notes/<slug>-backlog.md` instead of the round's
report body; `MUST-FIX` and `SHOULD-CONSIDER` stay in the section. State the tag next to each
finding, both in the merged report and in the backlog.

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

- **State whether the round passes the severity floor.** A round passes when no `MUST-FIX` or
  `SHOULD-CONSIDER` finding is open across every section. Open `NITPICK`s and `enhancement`s do not
  hold the round open; they sit in `.notes/<slug>-backlog.md` for whoever picks them up later. Say
  the pass/fail plainly, before the summary counts.
- Report the run cost: each agent's reading footer, and the number of agents dispatched. The figure
  compared against the token budget (step 1) is always the per-leg figure below, never the
  cumulative one.
  - For a freshly dispatched agent, its reported token usage is the round's cost for that leg.
  - For a resumed agent (re-check mode, or a later round), the harness reports cumulative context,
    not the round's cost. The per-leg cost is the difference between this report and the agent's
    previous report; compute and state that difference, not the cumulative figure. That per-leg
    delta still understates the resumed agent's true cost: each request re-reads its full context,
    so the reading is paid for again even though it does not show up in the delta.
  - Flag any agent whose reported usage is at or over its token budget (step 1).
- The fix step commits each round with explicit paths, new files included. Record that commit as
  `<last-round-ref>` for the next round's re-check test (step 1a), and update
  `.notes/<slug>-ledger.md` with the round's finding ids and their status.
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
