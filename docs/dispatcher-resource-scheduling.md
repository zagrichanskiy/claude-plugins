# Dispatcher resource scheduling and job split

Status: agreed design. Implementation follows the parts in [Parts](#parts).

Paths under `cli/`, `agents/`, `skills/` and `.claude-plugin/` are relative to `plugins/cure/`.
Paths under `cli/src/cure_job/` are cited by file name alone where the file name is unique.

## Problem

The dispatcher queues jobs that share a resource and runs them unattended when the resource frees.
In cure 0.20.0 it does not do that well:

| Gap | Effect |
|---|---|
| A `held` job gets no goal and no approval. | The user must be present when the resource frees. |
| A job holds its resources from launch to finish. `claim` exists, `release` does not. | A job that needs the bench only for verify blocks it for hours. |
| Resources are a repository path or `device:bench` only. | Two jobs in different repos share `build/` and the bitbake lock; the CLI sees no conflict. |
| No ordering between jobs. | Stacked changes cannot be queued. |
| No size control. | A job can produce a change too large to review. |

`device:bench` is the only hardware resource name (`resource.py`). It stands for the bench camera
at `root@192.168.240.1`.

## Decisions

| Decision | Reason |
|---|---|
| Changes stack in one workspace. | Yocto workspace with many repos. |
| No git worktrees per job. | `workspace/appends/*.bbappend` set `EXTERNALSRC` to fixed paths under `repositories/`; a worktree would build the main checkout. |
| Draft the goal and ask for approval while a job is `held`. Launch an approved job automatically when its resources free. | Unattended queueing. Needs an `approved` event in the CLI. |
| Add `cure-job release <id> <resource>`. The worker claims `device:bench` before verify and releases it after. | Short resource holds. |
| Add a `build:<dir>` resource. The worker claims it before each bitbake run and releases it after. | Serialises builds in a shared build directory; edits and reviews of other jobs keep running. |
| Add `after: <id>` to the handoff. The job stays `held` until the predecessor is `done`. Its `base` is the predecessor's branch. | Stacked changes. |
| Add a split skill with `context: fork`, called by `cure:goal` in job mode before the goal is written. | Estimation reads code; it must not land in the long-lived dispatcher context, which has no `Agent` tool. |
| Split trigger: estimated change in one repository above 800-1000 lines. | Reviewable PR size. A model estimate can be off by about 2x, so the value is a trigger, not a hard limit. |
| Split rule: each part builds, passes its tests and is reviewable alone. Cut at interfaces or layers. A cross-repo job splits only in the repo that exceeds the limit. | Each part is a mergeable PR. |
| A split creates one job per part (`cure-job new`) and one ticket per part in the repository's tracker (Jira, GitHub issues or other). The original job is closed with pointers to the parts. | Parts are tracked like any other work. |
| The split and the per-part estimate appear in the 3-line approval summary. | The user approves the split. |
| Remove the `capture-idea` skill and its row in `README.md`. Move its body sections (problem, decisions with reasons, rejected alternatives, open decisions, next steps) into the `cure:note` anatomy as the layout for a design note. | `capture-idea` writes to `~/.claude/ideas/`, outside the repository, and duplicates `cure:note`. |

## Rejected

| Alternative | Reason |
|---|---|
| Second `repo` workspace per job from a local mirror. | Own `build/` per instance; disk use doubles. Acceptable later only as a fixed pool of 2 workspaces, each one resource, with shared `DL_DIR` and `SSTATE_DIR`. |
| Build-service long-running session. | Builds come from `EXTERNALSRC` working trees; the builder needs its own tree, which is the second-workspace option. Every job build would wait on a queue. |
| `finish` appends a `release` for every claim. | Two non-atomic writes; misses a relaunched lost session; a resume could revive an old claim. |
| `release` wakes the dispatcher. | Not needed; each wake costs a turn on up to 200k context. |
| `cure-job with ID RES -- CMD` wrapper. | The repository's build agent decides how bitbake is called (`skills/dispatch/SKILL.md:34`); run-scoped claims bound a forgotten release. |
| Waiting through a background Bash call. | Unmeasured whether the session lists as idle; it could derive `stalled`. |
| Approval revoked by `goal.md` mtime. | Compares mtime with local-time stamps; the digest is exact. |
| Create jobs and tickets in the plan fork. | A decline leaves orphan tickets and jobs. |
| Keep the split plan only in the fork's reply. | Breaks `agents/dispatcher.md:11`; compaction loses it. |
| Embed part handoffs as fenced blocks in `split.md`. | `cure-job new` takes a file. |
| Split logic as a section of `skills/goal/job.md`. | The estimate would run in the dispatcher's context. |
| Tracker only from `defaults.md`. | Every repository would need a row before its first split. |
| `kind:` frontmatter key for design notes. | Nothing reads it. |

## State model

### Current facts

- Every lock rule is derived from `dispatch.jsonl` and the job files (`state.py:1-6`). The CLI holds no lock (`providers/jobs.py:5-6`).
- A job with a `goal.md` derives `awaiting-approval` even when blocked (`state.py:154-156`). `held` means "blocked and no goal".
- `launch` accepts `awaiting-approval` (`state.py:45`). The approval exists only in the dispatcher prompt (`agents/dispatcher.md:65`).
- `resources` is the handoff set plus the claimed set. No command removes one (`job.py:62-65`).
- `device: bench` locks the bench from queue to job end (`handoff.py:100-104`).
- No agent or skill tells a worker to call `claim`.

### States

| State | Condition | Launchable |
|---|---|---|
| `queued` | Unlaunched, not blocked, no goal. | no |
| `held` | Unlaunched, `blocked_by` non-empty, with or without a goal. | no |
| `awaiting-approval` | Unlaunched, not blocked, goal, no valid approval. | no |
| `approved` | Unlaunched, not blocked, goal, valid approval. New. | yes |
| `launched`, `running`, `stalled`, `blocked` | Session states. Unchanged. | no |
| `lost` | Unchanged. | yes |
| `needs-input` | Unchanged. | yes |
| `done`, `failed`, `abandoned` | Unchanged. | no |

`is_launchable` returns true for `approved`, `lost` and `needs-input`. `awaiting-approval` is no
longer launchable. `list --json` gains the fields `goal`, `approved`, `after` and `after-state`.

### Events

Existing events: `launched`, `claim`, `closed`, `origin`, `reported`, `stopped`, `sessions-removed`
(`events.py:222-228`). New events:

| Event | Form | Writer |
|---|---|---|
| `approved` | `{"event":"approved","goal":"sha256:<hex>","by":"user"\|"auto","at":...}` | `cure-job approve` |
| `release` | `{"event":"release","resource":...}` | `cure-job release` |
| `claim` | Gains a `run` field. | `cure-job claim` |

### Approval

| Item | Decision | Reason |
|---|---|---|
| Valid approval | An `approved` event whose digest equals sha256 of the current `goal.md` bytes. | Re-drafting the goal revokes the approval mechanically. |
| Digest normalisation | None. Checked in `_prepare_run` before `rewrite_goal` (`providers/jobs.py:142-152`), only for run 1. | The plugin-path retarget runs only at launch, after the check. |
| `cure-job approve ID [--by user\|auto]` | Legal when the job is open, has no launched run, has no result, and `goal.md` exists. These are the states `held`, `awaiting-approval` and `approved`. The same digest again writes nothing. The dispatcher is the only caller. | One durable record answers "may this session open". |
| `launch` | Run 1 needs a valid approval, else exit 1 "approve first". Later runs need none: relaunch of `lost` or `stalled`, launch of `needs-input`. | The user's answer is the approval for a later run (`agents/dispatcher.md:84`). |
| Solo/Light rule (`agents/dispatcher.md:65`) | Becomes `approve --by auto`. Its condition "holds every resource" moves to launch time. | One approval path. |

### Derivation order

First match wins:

1. closed -> `abandoned`
2. result failed -> `failed`; result done with no unproven item -> `done`
3. any other result -> `needs-input`
4. a launched event exists -> session states, unchanged
5. `blocked_by` non-empty (repo held by another job, or `after` predecessor not `done`) -> `held`
6. no goal -> `queued`
7. valid approval -> `approved`
8. otherwise -> `awaiting-approval`

### Transitions

| From | Trigger (caller) | To |
|---|---|---|
| none | `new` (dispatch skill) | `queued` or `held` |
| `queued` | `goal.md` written (dispatcher via `cure:goal`) | `awaiting-approval` |
| `held`, no goal | `goal.md` written | `held`, goal true |
| `awaiting-approval` | `approve` (dispatcher) | `approved` |
| `held`, goal, not approved | `approve` | `held`, approved true |
| `approved` / `held`, approved | `goal.md` bytes change | `awaiting-approval` / `held`, approved false |
| `queued`, `awaiting-approval`, `approved` | a launched job claims one of its repos | `held` |
| `held` | every blocker reaches `done`, `failed` or `abandoned`, and the predecessor is `done` | `queued`, `awaiting-approval` or `approved` by flags |
| `held`, after | predecessor `failed` or `abandoned` | stays `held`; the dispatcher closes it |
| `approved` | `launch` (dispatcher, no question) | `launched` |
| `awaiting-approval` | `launch` | refused, exit 1 |
| `launched` to `lost` | unchanged | unchanged |
| `needs-input` | `resume` or `launch`, no approval needed | `launched` |
| any open state without a session | `close` | `abandoned` |

### `cure-job release <id> <resource>`

| Item | Decision | Reason |
|---|---|---|
| Releasable | Only `device:*` and `build:*`. Releasing a repo path exits 1 "held until the job ends". | A repo tree holds uncommitted work. Unlaunched jobs are then blocked only by repos. |
| Caller | The worker, for its own job only. Never the dispatcher. | The CLI cannot authenticate callers; this is a stated contract. |
| Idempotence | Exit 0 whenever the job does not hold the resource after the call. Exit 1 only for an unknown or invalid job, or a repo name. | Retries are harmless. |
| Dispatcher rescans | No dispatcher wake on release. After its own `close`, the dispatcher runs `list` again in the same turn. Today it runs `list` once per wake (`agents/dispatcher.md:33-38`). | Unlaunched jobs name only repos. Repos free at `done` or `failed`, followed by the worker's message, or at `abandoned`, the dispatcher's own close. Short-hold waiters use `claim --wait`. |

### Run-scoped claims

| Item | Decision | Reason |
|---|---|---|
| Claim scope | A short-hold claim (`device:*`, `build:*`) counts only while its run is the latest run and no result exists. A `release` cancels it in event order. Repo claims are held to job end. A `claim` without `run`, written by an older version, counts for the whole job. | Finish, needs-input, resume or relaunch drop short holds with no write. A forgotten release is bounded by the run. The scope is derived, not stored (`state.py:1`). |
| Lost session | Keeps its claims until relaunch or close. | Bench state is unknown after a crash. |
| At finish | Short holds free when `result.md` exists. Repos stay held through `needs-input` and free at `done`, `failed` or `abandoned`. | A `needs-input` tree still holds edits. |
| Bench in handoff | `device: bench` no longer adds `device:bench` to `Handoff.resources` (`handoff.py:100-104`). It declares bench use and keeps the resource-risk scope (`skills/goal/job.md:17-18`). The goal writes claim and release around verify. | Otherwise the bench is held from launch. |

### `claim` changes and `claim --wait`

| Item | Decision | Reason |
|---|---|---|
| Precondition | `claim` needs a launched run with no result and no close, checked on the record. | A claim outside a run never takes effect. |
| `--wait SECONDS` | At most 540. Polls until the resource is free, then exits 0. On timeout exits 1 `ResourceHeld`. | Fits one foreground Bash call under the 600 s cap. The session stays busy, not `stalled` (`state.py:145-146`). |
| Atomicity | Check and append run under `fcntl.flock` on the `jobs/` directory descriptor. The docstring at `providers/jobs.py:5-6` changes. | The id tie-break in `holders()` (`state.py:79-92`) lets a lower-id claimant overtake a running build; the second bitbake fails on `bitbake.lock`. A directory flock creates no lock file. |
| Wait budget (A7) | A worker waits for a short hold for at most 2 hours in total, through repeated `claim --wait` calls. Then it finishes with `needs-input`. | Bounds the polling cost. One request per 9 minutes. |
| Worker protocol | `skills/goal/worker.md` gains "Short holds". Before each bench step, and before each command that takes `bitbake.lock` (`bitbake`, `devtool`, `kas`): `claim --wait`. After it, on success or failure: `release`. In Light and Full mode the orchestrator claims before it dispatches the agent and releases after the agent returns. | One protocol for every job worker. |

### `build:<dir>`

| Item | Decision | Reason |
|---|---|---|
| Syntax | `build:<absolute path of the bitbake TOPDIR>`. | `bitbake.lock` lives in TOPDIR. |
| Normalisation | `os.path.realpath`. A relative path is refused at the claim argument. | `bitbake.lock` is per physical directory. This differs deliberately from `repo()` (`resource.py:9-13`). |
| Conflict | Equal names conflict. No prefix nesting. No relation to repo paths. | Build directories that share `DL_DIR` and `SSTATE_DIR` are supported. |
| Who fills it | The worker, at claim time. See [Who fills `build:<dir>`](#who-fills-builddir). | |

### `after: <id>`

| Item | Decision | Reason |
|---|---|---|
| Storage | Handoff frontmatter scalar `after: <job id>`, one predecessor. `Handoff.after`, checked with `job_id.is_valid`. `new` refuses an id with no job. | A stack is a chain. |
| Leaves `held` | When the predecessor derives `done`. `needs-input`, including done with an unproven item, keeps it held. The predecessor id is added to `blocked_by`. | The successor's branch base exists only after `done`; a successor never runs after a failure. |
| `launch` while after-blocked | Exit 1 `after <pred> is <state>`. | `providers/jobs.py:144-147` uses `next()` over resources; a non-resource blocker raises `StopIteration`. |
| Predecessor failed or abandoned (A6) | The CLI derives `held`; `list` shows `after-state`. The dispatcher closes the successor without asking and sends the origin "closed: predecessor <id> <state>; re-dispatch" (as `skills/goal/job.md:94`). Successors of the closed job follow on the next scan. | A failed job is terminal (`state.py:45`). |
| `base` (A5) | `cure:goal` job mode sets `base` to the predecessor's branch, read from the predecessor's `goal.md`, only for a repository the predecessor also changes. For any other repository `base` comes from the handoff as today. The dispatcher drafts a successor's goal only after the predecessor's row has `goal` true. | Handoff `branch` may be `current` (`skills/dispatch/defaults.md:9`). A branch exists only in its own repository. Base moves are caught by work item 1 (`skills/goal/rules.md:194`). |
| Cycles | No check. The predecessor must exist at `new`; the new id is fresh. `derive` looks one hop. | A cycle cannot be built. |
| Prune | `prune` keeps an expired job named by an open job's `after` (`providers/jobs.py:326-334`, `state.py:55-59`). A missing predecessor derives `held` with `after-state: missing`. | Otherwise a pruned predecessor leaves the successor unknown. |

### Dispatcher table changes

| Row | Action |
|---|---|
| `held`, no goal | Steps 1-4: draft, checks, summary, question. |
| `held`, goal, not approved | Ask once, then `approve`. |
| `held`, approved | Nothing. |
| `held`, `after-state` `failed` or `abandoned` | `close` the successor, tell the origin, run `list` again. |
| `approved` | Re-run the step 2-3 checks, then `launch`. |

### Risks

| Risk | Impact | Mitigation |
|---|---|---|
| Another job's in-progress edits enter this job's image build via `EXTERNALSRC`. | The build fails, or verify runs with foreign changes. | Build own recipes where verify allows; name the cause in the retrospective. |
| Bench jobs lose the launch-time bench lock at the part 1 upgrade. | Two jobs on the bench. | Upgrade with no `device: bench` job open. The part 1 PR states this. |
| A worker forgets `release`. | The bench is held until the run ends. | Run-scoped claims. |
| A lost session keeps short holds. | Other workers wait. | Deliberate. |

## Split skill

The dispatcher has no `Agent` tool (`agents/dispatcher.md:121`) and keeps no request state in its
context (`agents/dispatcher.md:11`). A forked skill cannot ask the user; every question the split
raises goes back to the dispatcher's question round. No job and no ticket exists before the user
approves the split.

### Skill file

| Item | Decision | Reason |
|---|---|---|
| File | `skills/split/SKILL.md`, invoked as `cure:split`. | Matches the one-word skill names. |
| Frontmatter | `name: split`; `description:` states the purpose and "invoked by `cure:goal` in job mode with a job directory, and by the dispatcher with `apply` or `decline`"; `context: fork`; `allowed-tools: Read, Write, Grep, Glob, Bash`; `user-invocable: false`. No `agent:` key. | Estimating is a judgement. `Explore` cannot write `split.md`. `collector` never judges. A fork cannot reach the user, so no `AskUserQuestion`. |
| Lint | Add `context` and `agent` to `SKILL_KEYS` (`scripts/lint-plugin.py:25-28`). Check `context` against `{fork}` with `check_enum`. | The lint rejects `context:` today (`scripts/lint-plugin.py:117-118`). |
| `goal/SKILL.md` | Add `Skill` to `allowed-tools` (`skills/goal/SKILL.md:3`). | Job mode calls a skill. |

### Modes and inputs

| Mode | Caller | Action |
|---|---|---|
| `plan` (default) | `cure:goal` job mode | Estimate. Under the limit: return `no split: ...`. Over the limit: write the plan files and return `split proposed: ...`. |
| `apply` | dispatcher, after the user chooses apply | Create tickets and jobs, close the original. |
| `decline` | dispatcher, after the user chooses run as one | Set `status: declined`. |

`$ARGUMENTS` is `<job dir> [plan|apply|decline]`. The skill reads `<job>/handoff.md`. The job id
is the directory name (`skills/goal/job.md:6-10`). The skill reads
`${CURE_JOB_ROOT:-~/.claude/cure}/defaults.md` for the limit and tracker rows.

### Plan state files

| File | Content |
|---|---|
| `<job>/split.md` | Frontmatter: `status: proposed \| declined \| applying \| applied`, `original`, `limit`, `tracker`. Body: `## Estimate` (table), `## Parts` (table: k, slug, repos, outcome, estimate, after, ticket, job), `## Summary` (3 lines). |
| `<job>/part-<k>.md` | One handoff per part. |

`cure:split` is the only reader and writer of these files. The store ignores files it does not
name (`cli/src/cure_job/store.py:5-6,28-31`). The plan survives between wakes. `apply` is
repeatable after a partial failure.

### Trigger and estimation

| Item | Decision |
|---|---|
| Call site | In `skills/goal/job.md`, after Input and before the question round. Only when `<job>/goal.md` does not exist and the handoff has no `split-from:` key. A re-run on an existing `goal.md` does not re-estimate. A part is not split again. The CLI ignores unknown frontmatter keys (`handoff.py:4-5`). |
| Method | 1. From Work and Done when, list every file each step changes: new, edited, deleted, tests, docs. Read each file to be edited. 2. Per file, estimate added plus deleted lines with a one-phrase basis. 3. Sum per repository. 4. If `~/.claude/retros/` has a similar goal, check the sum against its Measurements row (`skills/goal/SKILL.md:235-236`). |
| Unit | Insertions plus deletions of `git diff --shortstat <base>`, the unit of the goal's cap (`skills/goal/job.md:127-128`). |
| Trigger | `split limit` row in `defaults.md`, default 800. Split when one repository's estimate is above it. 800 is the lower edge of 800-1000 because the estimate can be 2x low. |
| Under the limit | Return `no split: <repo> ~N[, <repo> ~M]; limit L`. Write no file. `cure:goal` records "Estimate: ~N changed lines (cure:split)" under Settled and sets `<lines>` to 2 x N rounded up to 100. The retrospective's "Changed lines against the cap" (`skills/goal/SKILL.md:221`) also reports the estimate. |
| Cannot cut | Return `no split: cannot cut <repo> below L: <reason>`. `cure:goal` asks: run as one job, or abandon. |

### Split rule

1. Cut only the repository over the limit.
2. Order by layer: types and interfaces, implementation, callers and wiring, removal of what was replaced, docs.
3. Use the fewest parts with each part at or below the limit.
4. Tests go with the code they test.
5. No part leaves a caller of something that does not exist yet.
6. Each part builds and passes its tests alone.
7. Repositories under the limit stay whole and go with the part that needs them. That part lists both repos, the delivering repo first (`skills/dispatch/SKILL.md:25`).
8. With two repos over the limit, the provider repo's parts come first.
9. Parts form one linear chain. This matches a single-id `after:`.

### Part handoffs

| Field | Value |
|---|---|
| Template fields | As in `skills/dispatch/template.md`. |
| `split-from:` | The original job id. |
| `outcome`, `## Work`, `## Done when`, `device` | Per part. `device: bench` only if the part needs the bench. |
| Settled | Applicable lines copied, plus "Split: part k of n of <original id>; estimate ~N lines". |
| `Resource risk:` lines, `## Tools` | Copied verbatim. |
| `## Open` | Each item goes into the first part it affects. |
| `ticket:`, `after:` | Empty until apply. |
| `branch` | With `delivery: pr`: `<original branch>-part<k>`. |
| Slug | `<original slug>-part<k>`. It passes `_slug_arg` (`commands/new.py:42-47`). |

### Plan return, dispatcher, apply and decline

| Step | Decision | Reason |
|---|---|---|
| Plan return | `split proposed: <job>/split.md` plus the 3 summary lines. `cure:goal` writes no `goal.md`, skips its question round and reports this line in place of the launch line (`skills/goal/job.md:148`). | The job stays `queued` without a goal (`state.py:154`) and cannot be launched. |
| Dispatcher | In step 1 (`agents/dispatcher.md:61`), on a proposed split, print `## Summary` from `split.md` verbatim and ask in the question round: apply, or run as one job. A split is never auto-launched. `agents/dispatcher.md:120` allows `split.md` and `part-<k>.md` through `cure:split`. After apply, the dispatcher sends the origin the returned line and runs `cure-job list` again. | `split.md` is the single source; later wakes re-print from the file. |
| Apply | Per part k in order: (a) create the ticket if a tracker is active and the row has none; record it. (b) Fill `ticket:` and `after:` in `part-<k>.md`. Part 1 takes the original's `after:`. Part k > 1 takes part k-1's job id. (c) `cure-job new --slug <slug> <job>/part-<k>.md`; record the id. (d) If the original has an `origin`, run `cure-job origin <id> <origin>` (`providers/jobs.py:209-217`). After the last part: comment the part tickets on the original ticket if it is in the same tracker. Run `cure-job close <original> --reason "split into <id1>, <id2>, ..."` (`commands/close.py:18`). Set `status: applied`. Return `job <original> closed: split into <ids>`. | `status: applying` during the loop. Each step is recorded before the next, so a failed apply resumes without duplicates. The original is closed last. The fork has no `SendMessage`. |
| Decline | `status: declined`. A later `plan` returns `no split: declined, estimate ~N` without re-estimating. The dispatcher then runs step 1 again. | The decision persists across wakes. |

### 3-line summary

| Line | Split job |
|---|---|
| 1 | `<id>: <outcome> -> split into <n> parts in <repo>; estimate ~<total>, limit <L>` |
| 2 | `1 <slug> ~<lines>; 2 <slug> ~<lines> after 1; ...` |
| 3 | `tickets: <n> new in <tracker> \| none: <reason>; original closed on apply` |

For an unsplit job, line 2 of the normal summary (`agents/dispatcher.md:64`) gains `~N lines`.

### Risks

| Risk | Mitigation |
|---|---|
| Unverified: a `context: fork` skill forks when the caller has no `Agent` tool and honours `allowed-tools`. | Part 4 done-when 2 tests it. |
| The estimate may read a tree another job edits. | Accepted within the 2x margin. |
| The close reason is not in `cure-job list --json` (`commands/list.py:59-72`). | Pointers live in `dispatch.jsonl`, the origin message and the ticket. |

## Design note

### `capture-idea` removal

`~/.claude/ideas/` files lie outside the repository. Part 5 does not touch them (A2).

| File | Change |
|---|---|
| `plugins/cure/skills/capture-idea/SKILL.md` | Delete the file and the directory. |
| `README.md:141` | Delete the `capture-idea` row. |
| `README.md:142` | The `note` row gains "and design notes (problem, decisions, rejected, open, next steps)". |
| `plugins/cure/skills/note/SKILL.md:2` | The description gains the trigger phrases of `capture-idea`: "save this idea", "capture this for later", "write this design down". |
| `plugins/cure/.claude-plugin/plugin.json:3` | Bump the version. |

`git grep -n -i "capture-idea\|capture_idea\|capture idea\|claude/ideas\|ideas/"` finds no other
tracked mention.

### `cure:note` design-note anatomy

| Item | Decision | Reason |
|---|---|---|
| Place | A `## Design note` section in `skills/note/SKILL.md` after Anatomy (`:28-46`), with the template inline. A command row `/note design <title>` in Commands (`:48-55`). | About 40 lines. The sweep needs it too. |
| Frontmatter | The existing five keys. No `kind:` key. `supersedes_when` names the design document or the implementing PR. | Nothing would read `kind`. |
| Layout | `# <Title>`, `## Problem`, `## Decisions` (table Decision \| Reason), `## Rejected` (table Alternative \| Reason), `## Open decisions` (omitted when none), `## Next steps` (numbered). | The layout of the brief this document came from, with Decisions and Rejected as top-level sections. |
| Rules carried over | Write from the conversation. One idea per file. If `.notes/<slug>.md` exists, update it and do not overwrite agreed rows. | `capture-idea` `:25-28`, `:31-34`, `:65-71`. |
| Sweep | A design note is covered only when every Decisions, Rejected and Open decisions row is in the artifact. | Extends the sweep rule (`:64-65`) to the tables. |

## Decisions on the open questions

### Tracker detection and authentication

Decision: detect the tracker at plan time, first match wins. Authenticate only through a client
that is already logged in. Part 4 ships the GitHub row only (A3).

| # | Source | Result |
|---|---|---|
| 1 | Handoff `ticket:` form. `^[A-Z][A-Z0-9]+-\d+$` is Jira (project = prefix). `#N`, `owner/repo#N` or a github.com issue URL is GitHub. | Direct evidence. |
| 2 | `defaults.md` row `tracker` with scope `all` or `repo: <path>`. Value `github`, `jira <PROJECT>` or `none`. `skills/goal/job.md:16-18` and `defaults.md` gain the `repo:` scope form. | Explicit user setting. |
| 3 | The over-limit repo's `CLAUDE.md` names a tracker. | Project convention. |
| 4 | `git remote get-url origin` is on github.com and `gh repo view --json hasIssuesEnabled` is true. | GitHub issues. |
| 5 | None of the above. | `tracker: none` |

| Rule | Decision |
|---|---|
| Credentials | The skill never logs in, never reads or stores a token, and never passes credentials. |
| Auth check | At plan time, the client's status command. GitHub: `gh auth status`. |
| Tracker table | One row per tracker in `SKILL.md`: detect, auth check, create, comment. |
| Jira (A3) | A Jira key is detected and reported `tracker: none (no Jira client configured)`. A Jira row is added when the user names a client. |
| No tracker at plan | No tracker, an unsupported tracker or a failed auth check gives `tracker: none <reason>`. Summary line 3 states the reason and the fix, for example `gh auth login`. The user chooses apply without tickets, or run as one. Parts copy the original `ticket:`. |
| Failure during apply | Auth or create fails: stop before that part's `cure-job new`. `split.md` keeps progress. Return `failed at part k: <error>`. A later `apply` resumes. |

Reason: the ticket form and an explicit setting are direct evidence, and the repository fallback
spares a `defaults.md` row per repository. Credentials stay with the user's own client.

### Approval expiry for a `held` approved job

Decision: no expiry by time. Only a change of the `goal.md` digest revokes an approval. To
withdraw an approval, the user closes the job or the goal is re-drafted.

Reason: a time limit brings the user back on every long wait. Prelaunch checks re-run on every wake
before launch (`skills/goal/job.md:58`), followed by the uncommitted-changes question
(`agents/dispatcher.md:63`). Stale code facts fail in work item 1 (`skills/goal/rules.md:194`).

### Who fills `build:<dir>`

Decision: the worker fills it at claim time, from the directory the build runs in. The handoff
never names a `build:` resource.

Reason: a handoff resource is held from queue to job end and would block other jobs' edits and
reviews. The cost is that the dispatcher cannot foresee build contention; a worker resolves it by
waiting with `claim --wait`.

### More than one bench device name

Decision: `device:bench` stays the only name. `Device` stays a closed set (`handoff.py:84-86`,
`resource.py:6`). No second bench is assumed (A8). When a second bench exists, names come from a
`<root>/devices` file, one name per line, and unknown names are refused. Name-to-address mapping
stays in `defaults.md`.

Reason: there is one bench. An open `device:<name>` grammar turns a typo into a resource that never
conflicts.

## Parts

All parts change claude-plugins only. Order: 1, 2, 3, 4, 5 (A9). Each part is one job and one PR.
Each part that changes `plugins/cure/` bumps the plugin version.

1. Short holds: `release`, run-scoped claims, `claim --wait`, `build:<dir>`
   - Issue: TBD
   - Scope: `release` command and event; `run` field on claims; `claim` precondition, `--wait` and directory flock; `device: bench` no longer a handoff resource; `build:<dir>`; worker "Short holds" protocol.
   - Files: `cli/src/cure_job/` `resource.py`, `events.py`, `job.py`, `handoff.py`, `store.py`, `providers/jobs.py`, `commands/claim.py`, new `commands/release.py`, `cli.py`; tests `test_events`, `test_jobs`, `test_state`, `test_cli`, `test_handoff` (about 44 bench references); `skills/goal/worker.md`, `skills/goal/job.md`, `skills/dispatch/SKILL.md:26`, `agents/dispatcher.md`; `plugin.json`.
   - Estimate: 610 changed lines in claude-plugins (230 code, 320 tests, 60 docs). Cut line: if the diff passes 800 lines, `build:<dir>` (about 150 lines) moves to a part 1b between parts 1 and 2.
   - Depends on: none.
   - Done when:
     1. `claim ID build:<symlinked or ../ path>` stores the realpath.
     2. Two launched jobs: B's claim exits 1 naming A. After A's `release`, B's `claim --wait` exits 0 (fake clock).
     3. A run-1 claim is absent from `resources` after `finish` and after run 2 starts.
     4. `release` of a repo exits 1. A second `release` of a device exits 0.
     5. `device: bench` no longer blocks a second job at launch.
     6. A legacy `claim` without `run` still counts.
     7. `pytest` and `scripts/lint-plugin.py` pass.

2. Approval while held, auto-launch
   - Issue: TBD
   - Scope: `approved` event bound to the goal digest; `cure-job approve`; state `approved`; `held` with or without a goal; run-1 launch needs approval; `list --json` fields `goal` and `approved`; dispatcher table rows for `held` and `approved`; Solo/Light rule as `approve --by auto`.
   - Files: `events.py`, `job.py`, `store.py`, `goal.py` or a digest helper, `state.py`, `providers/jobs.py`, new `commands/approve.py`, `cli.py`, `commands/list.py`; tests (an approving builder helper; about 68 `launch` call sites); `agents/dispatcher.md`, the launch line in `skills/goal/job.md`, `README.md:107`; `plugin.json`.
   - Estimate: 510 changed lines in claude-plugins (150 code, 300 tests, 60 docs).
   - Depends on: part 1.
   - Done when:
     1. A blocked job with a goal lists `held` with `goal` true.
     2. `approve` then `launch` succeeds. `launch` without `approve` exits 1.
     3. Editing `goal.md` after `approve` returns `approved` to `awaiting-approval`.
     4. After the blocker is `done`, the held approved job lists `approved` with no new event.
     5. A `needs-input` launch or resume needs no approval.
     6. `pytest` and `scripts/lint-plugin.py` pass.

3. `after:` ordering
   - Issue: TBD
   - Scope: handoff key `after:`; predecessor in `blocked_by`; `after-state` in `list`; launch refusal; prune guard; `base` from a same-repository predecessor; dispatcher closes the successor of a failed or abandoned predecessor.
   - Files: `handoff.py`, `state.py`, `providers/jobs.py`, `commands/list.py`; tests; `skills/dispatch/SKILL.md`, `skills/dispatch/template.md`, `skills/goal/job.md`, `agents/dispatcher.md`; `plugin.json`.
   - Estimate: 310 changed lines in claude-plugins (90 code, 180 tests, 40 docs).
   - Depends on: part 2.
   - Done when:
     1. `new` with an unknown `after` exits 1.
     2. The successor is `held` with the predecessor in `blocked-by` until `done`. `needs-input` keeps it held.
     3. `launch` of an after-held job exits 1 `after <id> is <state>`, with no traceback.
     4. A failed predecessor gives `after-state: failed`.
     5. `prune` keeps an expired predecessor of an open job.
     6. `pytest` and `scripts/lint-plugin.py` pass.

4. Split skill with tracker tickets
   - Issue: TBD
   - Scope: `cure:split` with `plan`, `apply` and `decline`; plan state files; estimation and trigger; GitHub tracker row; call from `cure:goal` job mode; dispatcher question round for a proposed split; lint keys.
   - Files: `skills/split/SKILL.md` (new, about 170), `skills/split/template.md` (new, about 50), `skills/goal/job.md` (about 25), `skills/goal/SKILL.md` (about 8), `agents/dispatcher.md` (about 25), `skills/dispatch/defaults.md` (about 4), `scripts/lint-plugin.py` (about 6), `README.md` (about 6), `plugin.json` (2), `cli/tests/test_handoff.py` (about 10).
   - Estimate: 305 changed lines in claude-plugins.
   - Depends on: part 3 (`after:`). Stacks after part 2, which edits the same sections of `agents/dispatcher.md` and `skills/goal/job.md`.
   - Done when:
     1. `scripts/lint-plugin.py` exits 0.
     2. From a session without `Agent`, `cure:split` runs forked. The main transcript has no Read of repository source.
     3. With a temporary `CURE_JOB_ROOT`, an over-limit fixture and tracker none: `split.md` is `proposed`, has n >= 2 parts each at or below the limit, and a 3-line Summary.
     4. `apply` creates n jobs in `cure-job list --json`. Part k > 1 has `after:` equal to part k-1's id. The original is `abandoned` with the reason in `dispatch.jsonl`.
     5. A second `apply` leaves the job count unchanged.
     6. CLI tests pass.
     7. The version is bumped.
     8. The GitHub ticket path is checked by hand as a PR-checklist item, with no scratch repository (A4).

5. Remove `capture-idea`, extend `cure:note`
   - Issue: TBD
   - Scope: the file list in [`capture-idea` removal](#capture-idea-removal) and the [design-note anatomy](#curenote-design-note-anatomy).
   - Files: `skills/capture-idea/SKILL.md` (deleted, 71), `skills/note/SKILL.md` (about 45), `README.md` (about 3), `plugin.json` (2).
   - Estimate: 121 changed lines in claude-plugins.
   - Depends on: none. It conflicts textually with other parts only in `plugin.json` and the README skills table.
   - Done when:
     1. `test ! -e plugins/cure/skills/capture-idea` succeeds.
     2. `git grep -n capture-idea` prints nothing.
     3. `skills/note/SKILL.md` contains `/note design` and the five design-note headings.
     4. `scripts/lint-plugin.py` exits 0.
     5. The version is bumped.
