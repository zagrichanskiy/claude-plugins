# Retrospective

Each section ends with a retrospective. Its format is the retrospective bullet of "Light and Full" in `${CLAUDE_PLUGIN_ROOT}/skills/goal/rules.md`: sections Outcome, Where it went wrong, Proposed changes, in that order. The kinds of event for "Where it went wrong" rows are in `${CLAUDE_PLUGIN_ROOT}/skills/goal/sizing.md`, "The retrospective". `/cure:retro` turns its proposals into issues and deletes the file.

| Item | Rule |
|---|---|
| Path | `~/.claude/retros/<date>-<repo>-<slug>.md`. `<date>` is `YYYY-MM-DD`, `<repo>` is the repository of the document, `<slug>` is `architecture-doc-<stem>-<section>`: the document file stem and the section title, lowercase, words joined by hyphens. When the file exists, append the new section's rows to it. Do not overwrite. |
| Outcome | `met`, or `failed: <cause>, what is left` |
| Where it went wrong | Rows `W1…Wn` with evidence: rework, a failed exit check, a question the user answered that the skill should have asked earlier, a layout section that did not fit |
| Proposed changes | `Target / Change / Evidence (Wn) / Expected effect`. Targets: `cure:skills/architecture-doc/SKILL.md`, `cure:` path of the layout file, `repo:<path>`. |

- Make no proposal without `Wn` evidence.
- Write the file even when the table is empty.
- Never edit the skill or the layout from this skill.
