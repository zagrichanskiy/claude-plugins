# Merge rules for review-change step 4

## Sections

The report has one section per altitude, not one global ranking: correctness (`reviewer`), system
(`architect`), design (`designer`), Core Guidelines (the `cg-*` agents, one subsection per agent),
and any other agent dispatched. Each section keeps its own `MUST-FIX` and `SHOULD-CONSIDER` order,
by that agent's severity definitions. `NITPICK` findings do not stay in a section body.

## Placing `cg-*` findings

The `cg-*` agents classify findings as `defect` or `deviation` and rank nothing.

| Class | Section | Rank |
|---|---|---|
| `defect` | Correctness, beside the `reviewer` findings. | You rank it as a bug: `MUST-FIX`. |
| `deviation`, decided `reclassify as defect` | Correctness, beside the `reviewer` findings, with the designer's named failure. | You rank it as a bug, as a `defect` above. |
| `deviation`, any other decision | Design, in the designer's decision table. | The designer's decision. A `fix` carries the designer's severity; `accept here` and `propose project-wide` are not open findings. |
| `deviation`, not in the designer's decision table | Core Guidelines subsection of the agent that raised it. | `undecided`, with the cause: `designer did not run`, `designer stopped at the token budget`, or `designer left it out`. It does not gate the round. |

- A `defect` inside the scope of a `cg-deviations.md` entry is ranked as any other `defect`; the
  entry accepts deviations only.
- Core Guidelines subsections keep each agent's coverage table and count line.
- Collect every `propose project-wide` line from the designer's table in one list at the end of the
  design section, for the author to add to `.claude/cure/cg-deviations.md`. List entries that the
  change itself adds or edits in that file in the same place, marked `added by this change`.

## Tags

Triage every finding into exactly one of four tags: `MUST-FIX`, `SHOULD-CONSIDER`, `NITPICK`
(severities, by the dispatched agent's own definitions) and `enhancement` (a proposal for new
behaviour, not a severity). A `cg-*` deviation with no designer decision is `undecided`; that is not
a tag and does not gate the round.

- `security-expert` grades `critical`, `high`, `medium`, `low` and gives a verdict of
  `CHANGES REQUIRED` or `SATISFIED`. Map `critical` and `high` to `MUST-FIX`, `medium` to
  `SHOULD-CONSIDER`, `low` to `NITPICK`. A verdict of `CHANGES REQUIRED` means the round does not
  pass the severity floor (`NOT SATISFIED`).
- A prose reviewer that grades in its own words: a finding that makes the text fail its reader
  (wrong, misleading, or forbidden by the repository's rules, such as a comment that narrates the
  implementation) is `MUST-FIX`. Content the reader does not need is `SHOULD-CONSIDER`. Form only is
  `NITPICK`. A claim the reviewer cannot verify goes to the implementer to check; when it cannot be
  checked, it is a question.
- Carry the `enhancement` tag from the agent that raised it. Never assign it to a finding the agent
  tagged with a severity: that call belongs to the agent that read the source.
- List every `NITPICK` and every `enhancement` in the report, apart from the severity sections. The
  caller's fix step fixes them with each round's fixes; those of the last round go in one fix pass
  that the tests and lint verify. `MUST-FIX` and `SHOULD-CONSIDER` stay in their section. State the
  tag next to each finding.

## Content rules

- **Same depth in every section.** A design finding carries its proposed types, declarations and
  diagram as fully as a correctness finding carries its failing scenario and code excerpt. Never
  compress one altitude to make room for another; if the report is too long, shorten each nitpick to
  one line and never drop one.
- **Carry the assessments through.** The designer's structure and pattern assessments, and the
  architect's component and boundary assessment and pattern assessment, go into their sections
  verbatim or as tables.
- **Carry every coverage table through.** Each `cg-*` agent's, the designer's and the architect's
  coverage table goes into its section verbatim, or as a link to the agent's report path with its
  per-status counts. A section without one is incomplete.
- **List every skipped agent.** For a C++ change, add a *Skipped agents* table with the lines from
  step 3a: the agent, the sections left unchecked, and the §10 row with its value, or, for
  `security-expert`, `ui-reviewer` and `ux-reviewer`, the step 3 condition that did not hold. An
  agent absent from the report and from this table is a gap in the merge.
- **One defect, one entry.** When two agents raise the same defect, report it once, in the section
  of the altitude it belongs to, and record that both reached it independently. Agreement is not a
  rank boost.
- **Keep the evidence.** Every entry keeps its `path:line` and its concrete failing scenario or
  forces. A finding cited to the digest instead of the source is unverified.
- **Keep the suggested change.** Proposed decompositions, interface declarations and pattern
  recommendations stay with the finding.
- **State disagreements as disagreements.** Where two agents recommend incompatible changes, give
  both with their tradeoffs and say which you would take first. Do not average them.
- **Open with the first thing to address in each section**, then one line on the order across
  sections. Summary counts, if any, count every section.
- **Carry the open questions through.** A question an agent could not answer is work for the author.
- **Account for every earlier finding.** When step 1 found an earlier report, add a carry-over
  table: each earlier finding is *re-raised* (with its new ID), *resolved* (with the commit), or
  *not raised*. Re-check every must-fix that was not raised against the source yourself before you
  drop it. If it still holds, keep it in its altitude's section, marked as carried by the merging
  session.
- **Drop new non-defects in re-check rounds.** Only when the caller's brief carries a `Round:` line:
  drop a new finding (neither a finding of the previous round nor on a line that round's fixes
  changed) that is not a behaviour defect. It is not carried and not backlogged.

## Delegating the merge

The brief to a delegated `general-purpose` agent lists:

- the target and the output path `.notes/<slug>-r<N>-report.md`;
- the path of this file, with the instruction to follow every rule in it, including opening the
  source to re-check a carried must-fix;
- the report paths of the agents that hold `Write`, and the `ui-reviewer` and `ux-reviewer` reports
  in full;
- the skip lines recorded in step 3a;
- the earlier reports found in step 1.
