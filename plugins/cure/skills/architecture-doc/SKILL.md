---
description: Write an architecture document section by section with the user, using the cure:architect agent to draft and review each section and a handoff file to resume across sessions. Use when the user says "write an architecture document", "architecture doc", "draft the architecture of <subject>", or "/cure:architecture-doc".
allowed-tools: Read, Write, Edit, Grep, Glob, Bash, Agent, AskUserQuestion
---

# Architecture document

This skill runs in the main session, because each section needs decisions from the user. The
`cure:architect` agent drafts and reviews; the session asks, decides and records.

## Inputs

| Input | Source |
|---|---|
| Layout | `${CLAUDE_PLUGIN_ROOT}/knowledge/design-advisor/checklist-architecture.md`, section "Document skeleton — architecture document" |
| Handoff file | A path the user names. Ask for it when not given. |
| Document path | The user names it. Record it in the handoff file. |
| Diagram convention | The target project's, when one exists. Mermaid otherwise. |

Every section of the layout is optional. This skill does not repeat the section list; read it from the
layout file on each run.

## Handoff file

The handoff file is the only state. Create it in step 1; update it at the end of every step.

| Field | Content |
|---|---|
| Document path | Path of the document being written |
| Companion files | Other files of the document, such as concept relation pages, each with its diagram |
| Layout | Path of `checklist-architecture.md` and the section title above |
| Diagram convention | The project's convention, or Mermaid |
| Sections chosen | Ordered list, each with a status: `pending`, `drafted`, `agreed`, `done` |
| Decisions | One row per decision: section, decision, reason |
| Answers | One row per answer: section, question, answer |
| Open items | One row per item: section, item, status. Items stay here until the open-decisions and risks section is written. |

## Steps

1. Start or resume.
   - Handoff file exists: read it, report the status of each section, and continue at the first
     section that is not `done`.
   - No handoff file: read the layout, find the project's diagram convention, ask the user for the
     subject, the document path and the handoff path, then create the handoff file.
2. Choose the sections. Propose which layout sections the subject needs and which it does not, with
   one line of reason each. The user confirms or changes the list. Record it.
3. Work on one section at a time, in layout order.
   1. Ask the user the questions the section needs. Ask them in one round.
   2. Record the answers in the handoff file. Dispatch `cure:architect` in DOCUMENT mode with
      paths only: the layout file, the document path, the handoff path, the section title and the
      project's diagram convention. Pass no pasted content. The brief says: write only the named
      section and modify no other section. One exception: add a glossary entry to §2 (Concepts)
      for a term the section needs, and record each added entry in the handoff file. The brief
      also says: list each companion file in the handoff file.
   3. Run the newcomer-reader pass. Dispatch a general-purpose agent given only the text of the
      document and its companion files up to and including the section, not the handoff file or
      the layout. It returns a list of terms, arrows and claims it cannot explain from that text.
      Fix a gap that needs no new fact through `cure:architect` in DOCUMENT mode. A gap that needs
      a fact becomes a question to the user. Do this before the user sees the section.
   4. Present the draft. Agree changes with the user. Record each decision and each agreed change
      in the handoff file. Dispatch `cure:architect` in DOCUMENT mode again with the same brief,
      so that it applies the agreed changes. Repeat until the user accepts the draft.
   5. Run the exit check (below). Run the table checks first. Then run the prose review as a loop:
      dispatch `cure:architect` in REVIEW mode with paths and the section title, fix the findings
      through DOCUMENT mode, and review again. Stop when a round ends with `SATISFIED` (no
      `MUST-FIX` or `SHOULD-CONSIDER`), or after 5 rounds. After round 5 without `SATISFIED`, the
      section stays `agreed`, the open findings are reported to the user, and the user decides.
   6. Write the retrospective (below).
   7. Set the section to `done`, report it in a few lines and stop.
4. Continue to the next section only when the user says so.

## Exit check

A section is `done` when all of these hold:

| Check | Pass condition |
|---|---|
| Description | The section meets its description in the layout |
| Open items | Open items are in the handoff file. For the open-decisions and risks section: all of them are in its tables, or it states there are none |
| Diagrams | Each one, in the document and in companion files, renders and follows the project's convention. Mermaid: extract each block and run `npx -y @mermaid-js/mermaid-cli -i <file>.mmd -o <file>.svg` |
| Consistency | Names and terms match the sections already `done` and the companion files |
| Decisions | Each decision made in the session appears in the document or in the handoff file |
| Review | The `cure:architect` REVIEW ends with `SATISFIED`, or its open findings were reported to the user after round 5 and the user accepted them |

A failed table check returns the section to step 3.4. Report it to the user. A REVIEW that ends with `NOT SATISFIED` follows step 3.5.

## Retrospective

Each section ends with a retrospective. Its format is "The retrospective" in
`${CLAUDE_PLUGIN_ROOT}/skills/goal/SKILL.md`: sections Outcome, Where it went wrong, Proposed
changes, in that order. `/cure:retro` turns its proposals into issues and deletes the file.

| Item | Rule |
|---|---|
| Path | `~/.claude/retros/<date>-<repo>-<slug>.md`. `<date>` is `YYYY-MM-DD`, `<repo>` is the repository of the document, `<slug>` is `architecture-doc-<stem>-<section>`: the document file stem and the section title, lowercase, words joined by hyphens. When the file exists, append the new section's rows to it. Do not overwrite. |
| Outcome | `met`, or `failed: <cause>, what is left` |
| Where it went wrong | Rows `W1…Wn` with evidence: rework, a failed exit check, a question the user answered that the skill should have asked earlier, a layout section that did not fit |
| Proposed changes | `Target / Change / Evidence (Wn) / Expected effect`. Targets: `cure:skills/architecture-doc/SKILL.md`, `cure:` path of the layout file, `repo:<path>`. |

A proposal with no `Wn` evidence is not made. Write the file even when the table is empty. Never
edit the skill or the layout from this skill.

## Rules

- Draft and review through `cure:architect`. The session does not write section text itself.
- Read the layout file on each run. Do not rely on a remembered section list.
- Stop after each section. A user's earlier "continue" does not cover the next section.
- A document names only what the user supplied or the sources show. Do not invent names.
- Record every unresolved question as an open item, not as prose in the section.
- When the user drops the open-decisions and risks section, the final stop lists every open item to the user.
