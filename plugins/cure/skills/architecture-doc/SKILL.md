---
description: Write an architecture document section by section with the user, using the cure:architect agent to draft and review each section and a handoff file to resume across sessions. Use when the user says "write an architecture document", "architecture doc", "draft the architecture of <subject>", or "/cure:architecture-doc".
allowed-tools: Read, Write, Edit, Grep, Glob, Bash, Agent, AskUserQuestion
---

# Architecture document

Run this skill in the main session, because each section needs decisions from the user. The `cure:architect` agent drafts and reviews. The session asks, decides and records. The session does not write section text itself.

The document rules (reader, size limit, left-out content, style, review) are in `${CLAUDE_PLUGIN_ROOT}/knowledge/design-advisor/core.md`, *DOCUMENT*. A project's own documentation conventions take precedence.

## Inputs

| Input | Source |
|---|---|
| Layout | `${CLAUDE_PLUGIN_ROOT}/knowledge/design-advisor/checklist-architecture.md`, section "Document skeleton — architecture document". Read it on each run. Every section is optional. |
| Handoff file | A path the user names. Ask for it when not given. |
| Document path | The user names it. Record it in the handoff file. |
| Diagram convention | The target project's, when one exists. Mermaid otherwise. |

## Handoff file

The handoff file is the only state. Create it in step 1. Update it at the end of every step.

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

An unattended run (a goal or a job) has no user to confirm or answer. It takes each recommended option, records it, and skips step 3.4.

1. Start or resume.
   - Handoff file exists: read it, report the status of each section, and continue at the first section that is not `done`.
   - No handoff file: read the layout, find the project's diagram convention, ask the user for the subject, the document path and the handoff path, then create the handoff file.
2. Choose the sections. Propose which layout sections the subject needs and which it does not, with one line of reason each. The user confirms or changes the list. Record it. When the sections will not fit the size limit, split the subject into several documents and record the split.
3. Work on one section at a time, in layout order.
   1. Ask the user the questions the section needs, in one round.
   2. Record the answers in the handoff file. Dispatch `cure:architect` in DOCUMENT mode with paths only: the layout file, the document path, the handoff path, the section title and the project's diagram convention. Pass no pasted content. The brief says: write only the named section and modify no other section, except to add a glossary entry to §2 (Concepts) for a term the section needs. Record each added entry in the handoff file. List each companion file in the handoff file.
   3. Run the reader pass before the user sees the section. Dispatch a general-purpose agent given only the text of the document and its companion files up to and including the section, not the handoff file or the layout. It reads as an engineer of the team and returns the places where it cannot follow what the thing does or why. It does not ask for a definition of a term a team engineer knows. Fix a gap that needs no new fact through `cure:architect` in DOCUMENT mode. A gap that needs a fact becomes a question to the user.
   4. Present the draft. Agree changes with the user. Record each decision and each agreed change in the handoff file. Dispatch `cure:architect` in DOCUMENT mode again with the same brief to apply the agreed changes. Repeat until the user accepts the draft.
   5. Read `${CLAUDE_PLUGIN_ROOT}/skills/architecture-doc/exit-check.md` and run it. The review needs at least one round: dispatch `cure:architect` in REVIEW mode with paths and the section title, and fix the findings through DOCUMENT mode. Apply its proposed deletions. Decline a finding that adds text without stating what the reader cannot do without it. Review again only while a `MUST-FIX` or `SHOULD-CONSIDER` remains, at most 5 rounds. A `NITPICK` does not block. After round 5 without `SATISFIED`, the section stays `agreed` and the open findings are reported to the user, who decides.
   6. Read `${CLAUDE_PLUGIN_ROOT}/skills/architecture-doc/retrospective.md` and write the retrospective.
   7. Set the section to `done`, report it in a few lines and stop. An unattended run reports at the end.
4. Continue to the next section only when the user says so. An unattended run continues.

## Rules

- Stop after each section. A user's earlier "continue" does not cover the next section.
- A document names only what the user supplied or the sources show. Do not invent names.
- Record every unresolved question as an open item, not as prose in the section.
- When the user drops the open-decisions and risks section, the final stop lists every open item to the user.
