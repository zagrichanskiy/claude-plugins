# Dispatch estimate and split: procedure

## Sequence

| # | Action |
|---|---|
| 1 | Estimate the change per repository (section "Estimate"). |
| 2 | Add the current diff of the target PR, for the size decision of rows 3 and 4 only. Run `git -C <repo> fetch`, then `git -C <repo> diff --shortstat origin/<base>...<branch>`, insertions plus deletions; M is the result. `<base>` is the handoff `base`, else the default branch of the repository; when `origin/<base>` is absent, use the local `<base>...<branch>`. `<branch>` is the handoff `branch`, resolved as `job.md` resolves an omitted `branch`. When the local ref of `<branch>` is absent, use `origin/<branch>`. M = 0 when `<branch>` is absent locally and on `origin` (check each with `git rev-parse --verify -q`), as with the branch of an `after` predecessor. Skip this row for a small change (see `ticket`, `branch` in `SKILL.md` Fields). The sum of estimate and M, per repository, goes into no handoff. |
| 3 | No repository sum above the cap: the work stays in one ticket and one pull request, even when it holds several features. Add the Settled line "Estimate: ~N changed lines" (N is the repository estimate, without the diff; "in <repo>" and one line per repository when there are several) and write one handoff. Done. |
| 4 | Otherwise cut the work into parts by the split rule and draft one handoff per part. Split without asking. When the existing diff takes the sum over the cap, the PR stays as it is. Part 1 commits on the PR's own branch with the budget cap minus M. When that budget is 0 or less, part 1 gets no new work and is not queued, and new work starts at part 2 (see `after`, `base` and `branch` in "Part handoffs"). Further parts (2 to n) have the budget cap and are stacked on part 1's branch (the draft's `branch:`, else the head branch of the PR) through `after`; under `delivery: pr` each has a new ticket and branch. |
| 5 | Only with the effective `delivery: pr`, create the tickets of parts 2 to n (read `split-tickets.md`). Part 1 keeps the ticket and branch of the unsplit draft. A repository with no usable tracker is a case where the work cannot be cut: no ticket and no split. When the work cannot be cut, write one handoff with the Estimate line and tell the user in the report why. |
| 6 | Keep the drafts. Write nothing yet. |

## Estimate

1. From Work and Done when, list every file each step changes: new, edited, deleted, tests, docs. Read each file to be edited.
2. Per file, estimate added plus deleted lines with a one-phrase basis. Estimate tests apart from code by the rule in the goal skill, section "Sizing a goal".
3. Sum per repository. The unit is insertions plus deletions of `git diff --shortstat <base>`.
4. Run `grep '| <repo> |' ~/.claude/retros/stats.md`. If a row is a similar goal, check the sum against its `lines`.

## Part handoffs

| Field | Value |
|---|---|
| `outcome`, `## Work`, `## Done when`, `device` | Per part. `device: bench` only if the part needs the bench. |
| `## Settled` | The applicable lines, plus "Estimate: ~N changed lines" (N is the part's own estimate, without the diff; "in <repo>" and one line per repository when there are several) and "Split: part k of n". Part 2 with part 1 not queued also has "Base: the PR branch of split part 1". |
| `Resource risk:` lines, `## Tools` | Copied verbatim. |
| `## Open` | Each item goes into the first part it affects. |
| `after` | Part 1: the `after` of the unsplit draft, if any. Part k > 1: the job id of part k-1, printed by `cure-job new`; part 2 with part 1 not queued: the `after` of the unsplit draft. |
| `base` | Part 2 with part 1 not queued: the head branch of the PR. Other parts: as the unsplit draft. |
| `ticket` | Part 1: the `ticket` of the unsplit draft. Part k > 1, `delivery: pr`: the part own ticket. Part k > 1, `delivery: commit`: the session ticket. |
| `branch` | Part 1: the `branch` of the unsplit draft (omitted when the draft omits it). Part k > 1, `delivery: pr`: `<ticket>_<slug>`, with the ticket in the branch form of `skills/split/SKILL.md` section "Tickets" (`<tid>`). Part k > 1, `delivery: commit`: the `branch:` value of part 1, else the head branch of the PR; the parts stack as commits on it. |
| `--ticket-summary` | The title of the part's `ticket`, read as in `fields.md`. |
| Slug | `<slug>-part<k>`, for parts k > 1. |

## Part spec rules

Each part's handoff and ticket body, including any list of events or scope items in the ticket body, follow them:

1. List only the items this part owns. Mark each item an earlier part delivers as "delivered by part j" and do not list it as work. The marking applies to the handoff only. The marked items go in a separate list, not under work. The ticket body lists them as prerequisites present at the base and names no part or ticket.
2. For each config key the spec cites, say whether it exists at the base of this part. A key that a later part adds is marked "not yet".
3. Name each line a downstream reader parses, with its exact form: the file, the line text and the parser.
4. A part that creates a file format includes the format's frontmatter block in the spec.
5. A state whose action a later part adds gets an interim procedure in this part: what the user or dispatcher does meanwhile.
6. A "no references" check excludes migration code. Name the paths it excludes.
7. Name fields as they are in the file: handoff `repos`, not the row field `resources`.

## Split rule

1. Cut only the repository over the cap.
2. A whole feature is the packing unit. A single feature over the cap is cut by layer: types and interfaces, implementation, callers and wiring, removal of what was replaced, docs.
3. Use the fewest parts, each at or below the cap. Pack whole features into the parts up to the cap. A part may hold several features. One part per feature is not required.
4. Tests go with the code they test.
5. No part leaves a caller of something that does not exist yet. Each part builds and passes its tests alone.
6. A repository at or under the cap stays whole and goes with the part that needs it. That part lists both repos, the delivering repo first.
7. With two repositories over the cap, the provider repository parts come first.
8. The parts form one linear chain.
