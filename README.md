# claude-plugins

A personal [Claude Code](https://claude.com/claude-code) plugin marketplace.

## Install

```
/plugin marketplace add zagrichanskiy/claude-plugins
/plugin install cure@claude-plugins
```

## Plugins

### `cure`

Design and architecture advisors, review agents, and working-note discipline.

**Agents**

| Agent | What it does |
| --- | --- |
| `architect` | System-level architecture advice, review and documents for networked embedded systems. |
| `designer` | Module/class/interface-level design advice, review and documents. |
| `security-expert` | Security architecture and protocol review; authentication and key lifecycle. |
| `doc-reviewer` | Reviews how a technical document reads — structure, padding, misplaced content. |
| `ui-reviewer` | Visual-design review of web UI: typography, spacing, colour, contrast, hierarchy. |
| `ux-reviewer` | Interaction and accessibility review: task flow, feedback, keyboard and screen reader. |
| `knowledge-librarian` | Maintains a personal `~/knowledge` note library, delivered as a pull request. |

`architect` and `designer` share the checklists in `knowledge/design-advisor/`; each reads only
the checklist for its own mode.

**Skills**

| Skill | What it does |
| --- | --- |
| `note` | Gives working notes one home per repo, frontmatter that states their own end, and a sweep that deletes superseded ones. |
| `explain` | Explains a technology or codebase as a stepwise conversation, building a tree from the user's questions. |
| `stop-slop` | Removes AI writing patterns from prose. Vendored from [hardikpandya/stop-slop](https://github.com/hardikpandya/stop-slop) (MIT) — see `skills/stop-slop/VENDORED.md`. |

## Layout

```
.claude-plugin/marketplace.json
plugins/cure/
  .claude-plugin/plugin.json
  agents/                     # one .md per agent, auto-discovered
  skills/<name>/SKILL.md      # auto-discovered
  knowledge/design-advisor/   # shared reference material
```

Agents reference bundled files through `${CLAUDE_PLUGIN_ROOT}` so the plugin works wherever it
installs.
