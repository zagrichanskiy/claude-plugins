# Tiers, delegation and tool names

## Agent tier

Choose by judgement from size and risk. A small change that is crucial (security, data loss, a
public interface, hard to reverse) takes a higher tier.

| Tier | Choose when | Agents |
|---|---|---|
| Solo | A small, low-risk change | None. The session does the task and runs the done-when checks. |
| Light | A modest change with contained risk | Implementer, `qa`, one reviewer, retrospective. |
| Full | A large or risky change | `designer` or `architect` consult, implementer, `test-author`, `qa`, `review-change`, `verifier`, retrospective. |

- Every goal has a tier; Solo also gets a goal file. The work items name the tier's agents.
- Light has N review rounds (N = `reviews.Light`) and no live-verification gate. A repository's
  `CLAUDE.md` may set a higher count; that count replaces N.
- Read N once: `<plugin-root>/bin/cure-job config get reviews.<tier>`. Write the number into the goal.
  Bounds: Solo 0 (default 0), Light at least 1 (default 2), Full at least 2 (default 3). The CLI
  rejects other values. Never copy a cap from a handoff or a design source. In a direct run the user's
  own statement may set it.
- A review round is one reviewer pass, as `rules.md` "Light and Full" defines. A work item with a
  fresh-reader check adds its passes, as `fresh-reader.md` defines.

`<review cause>` of the failure exit:

| Tier | `<review cause>` |
|---|---|
| Light | a `MUST-FIX` or `SHOULD-CONSIDER` is open after review round <N> (N = `reviews.Light`, or the higher count the repository's `CLAUDE.md` sets) |
| Full | a `MUST-FIX` or `SHOULD-CONSIDER` is open after a PR's review round <N> (N = `reviews.Full`) |
| Solo | none |

A Solo goal differs from the template:

- Work: the read-first line, item 1, the task, and a clean-up item only when the task creates a
  working file. The clean-up item reads "Delete `<each working file>`. Keep the goal file." Its
  done-when item carries at least one path. With no working file, write neither.
- No retrospective item, no ledger, no backlog. The stats row work item and done-when item stay.
- Exits: drop `<rounds>`, `<review cause>` and the retrospective clause from the failure exit.
- Rules: the lines "Tier: Solo.", Stops, Permission mode (only when the user chose one) and Waiting.

## Delegate, then reflect (Light and Full)

- Orchestrator: the main session dispatches, tracks and checks. It reads no source and edits no code.
- Branch and commits: each is an orchestrator work item, committed with explicit paths. No work item
  or agent brief assigns them to `implementer`, `test-author` or `skill-author`; these refuse. The
  orchestrator's commit messages omit attribution trailers (`Co-Authored-By`, `Claude-Session:`,
  "Generated with") when the user's `CLAUDE.md` forbids them. Trailers the repository requires, such
  as `Signed-off-by:`, stay.
- Agent per step: each work item names its agent. Items with disjoint files run in parallel. Two
  writing agents that share a CLI or a file format get its command names, run semantics and format in
  both briefs; otherwise the docs agent runs after the CLI.
- Review-then-fix split: round 1 produces a triaged fix list, not fixes. Fixes ship as small PRs per
  component, each with at most N review rounds (N = `reviews.Full`). The cap counts per PR. A round
  that ended on a failed test or check counts apart from a round spent on review findings. A
  `MUST-FIX` or `SHOULD-CONSIDER` open after a PR's round N takes the failure exit; no round N+1
  starts. Rounds 2..N re-check only the previous round's fixes and raise no new topic. The
  orchestrator commits each round's fixes with explicit paths, new files included, before the
  re-check. Once the PR exists, a fix is squashed into the job's latest commit. One doc-only edit
  pass is allowed after the last review round. It changes no file that the build, the tests, or a
  loaded skill or agent reads.
- Consultation: `designer` answers class-level questions, `architect` component-level ones. Record
  the answer before the implementer starts. A class flagged in 2 consecutive review rounds gets a
  `designer` consult before an implementer touches it again; round-1 triage and the PR's first
  review round count as consecutive. After each consult, compare its line estimate plus the lines
  already changed with `<lines>`, as `rules.md` "Light and Full" states. The orchestrator never
  writes the class-level decision.
- Review loop: done when no `MUST-FIX` or `SHOULD-CONSIDER` is open. `NITPICK` and
  `enhancement`-tagged findings go to the backlog, not into another round. The backlog never holds a
  `MUST-FIX` or `SHOULD-CONSIDER`, except a fresh-reader finding that `fresh-reader.md` sends there. A `SHOULD-CONSIDER` that needs only an owner decision on behaviour a fix introduced is
  asked before its round closes. The `review-change` skill defines the triage words. The ledger holds
  every finding with its status, every assumption and every question with its answer. State a token
  budget per agent per round.
- Verification: `qa` runs the suite after each fix. Its pass count is a done-when item, and its brief
  gives the expected value of each check. In Full, a live-verification gate runs before merge: the
  `verifier` agent's output is a done-when item. A green suite alone does not clear it. A manual
  check goes into the PR checklist, never into the done-when list.
- Retrospective: a work item and a done-when item before the stats row item.
- Stats row: the second-last work item and the done-when item before the clean-up item, in every tier.
- Implementer brief: when the repository ships a versioned plugin or package, the brief says to bump
  the version once per branch, not per commit, and points to the repository's version rule when its
  `CLAUDE.md` has one.

## Name the tools

- Write the repository's own agents, skills and commands: the build command, the review agent, the
  hardware agent, the PR skill. Never write "verify it works".
- Take the names from the session's agent and skill list (job mode: the handoff's `## Tools`).
  Prefer the project's plugin over a general one.
- `implementer`, `test-author`, `qa`, `reviewer` and the other agents without a `Skill` tool cannot
  invoke a skill. For such an agent write "the orchestrator passes the skill's `SKILL.md` path to the
  agent; the agent reads that file and the docs it routes to". The path is
  `<installPath>/skills/<skill>/SKILL.md`, with `installPath` read from the plugin's entry in the
  plugin directory's `installed_plugins.json`. For a cure skill it is
  `<plugin-root>/skills/<skill>/SKILL.md`.
