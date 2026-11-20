# Base per repository

Applies when the job's row in `cure-job list --json` has `after`. For each repository R in the
handoff's `repos`, walk the chain from the row's `after`. Never use the handoff's `after:`.

| Step | Rule |
|---|---|
| Start | The job named by the row's `after`. |
| Changes R | R is in `repos` of the job's `handoff.md` (the row's `dir`). The row's `resources` also hold claimed repositories, which do not count. |
| Stop, resolved | The first job that changes R. `base` is the branch named in that job's `goal.md`. |
| Next job | The `after` of the current job's row. |
| Stop, unresolved | A passed row has `after-state` `missing` or `invalid`. |
| End of chain | No job changes R: `base` comes from the handoff or the default branch (`job.md` "Input"). |

Write the base of each repository left unresolved as an `## Open` item. Write the base per repository
in the goal's fact check. For a base taken from a predecessor or marked "Base: the PR branch of split
part 1", the fact check is the one in `rules.md`, not `<base>` equals `origin/<base>`.

A predecessor need not be done when the goal is written. Do not check its branch; work item 1 checks it at launch.
