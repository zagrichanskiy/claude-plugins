# C++ change: two waves (review-change step 3a)

The brief, the report path rule and the ban on topics from step 3 apply unchanged.

Gate from the digest, not from judgement. Read the digest's §10 *Gating signals* table and nothing
else to gate the `cg-*` agents and `architect`. Do not open source. Do not override a row. A signal
recorded as `unknown` counts as present. `security-expert`, `ui-reviewer`, `ux-reviewer` and the
prose reviewer keep step 3's conditions.

| Agent | Runs when | Evidence in §10 |
|---|---|---|
| `cg-interfaces`, `cg-classes`, `cg-resources`, `cg-statements`, `cg-philosophy` | Always. | `cpp` is `yes`. |
| `cg-concurrency` | The change shows threads, atomics, mutexes or coroutines. | `concurrency` is `yes`. |
| `cg-generic` | The change shows templates or concepts. | `templates` is `yes`. |
| `reviewer` | Always. | None. |
| `architect` | The change touches a public header, an IPC surface, a build dependency, config or schema, or a design document; or the user passed `--with architect`. | Any of `public_header`, `ipc_surface`, `build_dependency`, `config_schema`, `design_document` is `yes`; or the flag from step 1. |
| `security-expert`, `ui-reviewer`, `ux-reviewer` | As in step 3's table. | None. |
| The prose reviewer | As in step 3's table, in wave 1. | None. |
| `designer` | Always, in wave 2. | None. |

**Wave 1.** Dispatch every gated-in agent except `designer` in one message, each with step 3's brief
and its own report path. `reviewer` gets one more line:

```
Core Guidelines: <the report paths of the cg-* agents in this wave, one per line> — checked by the cg-* agents; do not read these reports.
```

Wait for all of them.

**Wave 2.** Dispatch `designer` with step 3's brief and one more line. Pass paths, never findings:

```
Already reported: <the wave 1 report paths, one per line> — already reported, do not repeat; input for cause analysis, not scope. The cg-* deviation findings in these reports are yours to decide.
```

The `cg-*` agents do not rank. `designer` decides each `deviation` finding: fix, accept here, propose
a project-wide entry, or reclassify as defect.

**Record every skip**, one line per agent left out, for the report:

- A `cg-*` agent or `architect`: the agent, every section it owns that went unchecked, and the §10
  row it needed with its value, for example
  `cg-generic — skipped: T (Templates and generic programming), SL (The Standard Library) not checked; templates = no (grep over 6 changed C++ files, 0 hits)`.
- `security-expert`, `ui-reviewer`, `ux-reviewer` or the prose reviewer: the agent, the step 3
  condition, and why it did not hold, for example `ui-reviewer — skipped: the change has a user interface; no UI file changed`.

## Registration check

Check that `cg-interfaces`, `cg-classes`, `cg-resources`, `cg-statements`,
`cg-philosophy`, `cg-concurrency` and `cg-generic` are in the session's agent list (plugin agents
appear prefixed, for example `cure:cg-philosophy`). When any is missing, tell the user so, in
those words, before dispatching:
- Cause: the session loaded a `cure` version without the `cg-*` agents. A session that started
  before a plugin update keeps the old agent list.
- Fix: run `claude plugin marketplace update zagrichanskiy` and
  `claude plugin update cure@zagrichanskiy`, then restart Claude Code.

Do not fall back to step 3's table without saying so. If the user continues, state in the report
that the Core Guidelines section is absent and why.
