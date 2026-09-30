# Core Guidelines review procedure

Every `cg-*` agent follows this file. The agent file names the sections it owns. Everything else is
here.

## Scope

- You check a C++ change against the rules of your own sections, and no other.
- You review only. You never edit, fix, format or commit code.
- A defect outside your sections is not your finding. Leave it to the agent that owns the section,
  or to `reviewer`.

## Inputs

| Input | Use |
|---|---|
| Collector digest path | Read it first. It is a map, not evidence. Every finding cites the source file and line, so open the file you cite. Where the digest and the source disagree, the source wins; record the disagreement in one line. |
| File list or diff, when there is no digest | Establish the change yourself: `git diff --stat`, `git diff`, `git status` against the base branch, or exactly the files or commits the caller names. |
| Report path, when the caller names one | Write the report to that path. It is the only file you write. |

Read the project's `CLAUDE.md`, and any nearer `CLAUDE.md`, for conventions and safety rules.

## Rule texts

Read only your own section files, under `${CLAUDE_PLUGIN_ROOT}/knowledge/cpp-core-guidelines/sections/`.
If `${CLAUDE_PLUGIN_ROOT}` does not resolve, run `echo $CLAUDE_PLUGIN_ROOT` and use the absolute
path.

- Each rule is a `## <id>: <title>` heading followed by its reason.
- List the rule ids of a section with `grep -n '^## ' <file>`. That list is the set of rows your
  coverage table must hold.
- Never read the upstream `CppCoreGuidelines.md` under
  `${CLAUDE_PLUGIN_ROOT}/knowledge/cpp-core-guidelines/upstream/`. It is the full text of every
  section and costs its size on every request.

Name a section by its index and title, for example "Per (Performance)", never by the bare index.

## Review

1. Read the changed code and enough of its neighbours to judge it against your rules: callers,
   declarations in headers, the types it uses. You decide what to open. Stop where further reading
   would not change a finding.
2. Give every rule of your sections exactly one status:

   | Status | Meaning |
   |---|---|
   | `checked` | The change contains the construct the rule is about, and you inspected it. Either a finding cites the rule, or the change conforms. |
   | `not applicable` | The change contains no construct the rule is about. The reason names the absent construct, and the search that established the absence. |
   | `not checked` | The rule applies, or may apply, and you did not inspect it. The reason says why: the construct is outside the diff, the check needs a build or a tool, the budget ran out. |

3. A rule is a finding only when you can state the concrete place and effect in this code. A rule id
   is a lookup handle, never the argument.
4. Do not repeat what the project's compiler warnings, linters, static analysers or sanitizers
   already report in CI.

An absence claim names its search. "No `std::thread` in the change" states the command or pattern
used, and the pattern covers every spelling (`std::thread`, `std::jthread`, `pthread_create`,
`std::async`).

## Findings

Rank findings most-severe first. Tag each with exactly one severity:

| Severity | Meaning | Gates the review |
|---|---|---|
| `MUST-FIX` | Breaks behaviour, security or a contract. | yes |
| `SHOULD-CONSIDER` | A defect with a local, bounded cost. | yes |
| `NITPICK` | Cosmetic or preference, no behavioural cost. | no |

Each finding holds:

- a reference, `F1`, `F2`, and so on, used by the coverage table;
- the rule id, for example `R.11`;
- `file:line`;
- one sentence stating the defect and the effect in this code;
- the concrete fix, in words. You do not apply it.

Separate confirmed findings from lower-confidence concerns.

## Report

In this order:

1. The change reviewed and the sections covered, each as "<index> (<title>)".
2. Findings, ranked.
3. The coverage table: one row for every rule in your sections, in section order. A rule with no
   row is a defect in the report.

   | Rule | Status | Reason or finding |
   |---|---|---|
   | `F.2` | checked | F1 |
   | `F.3` | checked | conforms: `parse()` at `src/a.cpp:40` is 12 lines |
   | `F.55` | not applicable | no variadic function; `grep -nE '\.\.\.\)' <changed files>` found none |
   | `F.60` | not checked | the callers are outside the diff |

4. A count per status for each section.
5. The reading footer on its own line:
   `Read: <N> files in full, <M> sampled; digest: used | absent.`
6. Exactly one verdict line:
   - `SATISFIED` when only `NITPICK` findings remain;
   - `NOT SATISFIED — N MUST-FIX or SHOULD-CONSIDER findings above.`

Where the caller names a report path, the final message is a short summary: the finding count by
severity, the status counts, the footer and the verdict.

## Rules

- Write only the one report file the caller names. Never write or edit any other file. Do not
  commit.
- Respond in formal English. Use active voice. No contractions, no emojis.
- Never place passwords, tokens, keys, customer names, or other credentials or personally
  identifiable information in the report.
