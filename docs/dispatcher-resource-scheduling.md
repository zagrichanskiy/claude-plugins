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
| Short holds acquired in a fixed order (`build:` before `device:`), enforced by the worker prompt only. | The CLI cannot check it. A worker that breaks it deadlocks two jobs for the full wait budget. |
| A `wait` event and a `claim-wait` field in `list --json`. | No claim waits while its run holds a short hold, and only short holds are waited for, so no wait cycle remains to show. The timeout exit names the resource and its holder. |
| Allow `after:` only with `delivery: pr`. | Stacking would not work with the default delivery. |
| Lock rank (not launched, not after-satisfied, not approved, id). | A ready job blocked on X still holds Y. Each new launch condition needs a new term. |
| Ready filter for lock holders without all or none. | A partial hold remains. |
| A reservation for every open job. | One unanswered question stops a repository's queue. |
| Lock order by approval time. | Re-approval reorders the queue. Approval stamps are local time. |
| Split apply re-queues each successor as a new job. | It drops origin and lock order, closes grandchildren and misses late successors. |
| A `cure-job after ID PRED` re-point event. | One write per successor; it misses late successors. |
| A generic `cure-job replace`, or a CLI `split`. | It needs a carry rule per event kind. Only `origin` carries for an unlaunched original, and the `origin:` key carries it atomically. A CLI split still cannot create n jobs atomically. |

## State model

### Current facts

- Every lock rule is derived from `dispatch.jsonl` and the job files (`state.py:1-6`). The CLI holds no lock (`providers/jobs.py:5-6`).
- A job with a `goal.md` derives `awaiting-approval` even when blocked (`state.py:154-156`). `held` means "blocked and no goal".
- `launch` accepts `awaiting-approval` (`state.py:45`). The approval exists only in the dispatcher prompt (`agents/dispatcher.md:65`).
- `resources` is the handoff set plus the claimed set. No command removes one (`job.py:62-65`).
- `device: bench` locks the bench from queue to job end (`handoff.py:34-39`).
- No agent or skill tells a worker to call `claim`.

### States

| State | Condition | Launchable |
|---|---|---|
| `queued` | Unlaunched, not blocked, no goal. Holds nothing. | no |
| `held` | Unlaunched, `blocked_by` non-empty or `after` not satisfied, with or without a goal. Holds nothing. | no |
| `awaiting-approval` | Unlaunched, not blocked, goal, no valid approval. Holds nothing. | no |
| `approved` | Unlaunched, not blocked, goal, valid approval, `after` satisfied. Holds every resource it names. New. | yes |
| `launched`, `running`, `stalled`, `blocked` | Session states. Unchanged. | no |
| `lost` | Unchanged. | yes |
| `needs-input` | Unchanged. | yes |
| `done`, `failed`, `abandoned` | Unchanged. | no |

`is_launchable` returns true for `approved`, `lost` and `needs-input`. `awaiting-approval` is no
longer launchable. `list --json` gains the fields `goal`, `approved`, `after`, `after-state` and `continued-by`.

### Events

Existing events: `launched`, `claim`, `closed`, `origin`, `reported`, `stopped`, `sessions-removed`
(`events.py:58-64`). New events:

| Event | Form | Writer |
|---|---|---|
| `approved` | `{"event":"approved","goal":"sha256:<hex>","by":"user"\|"auto","at":...}` | `cure-job approve` |
| `release` | `{"event":"release","resource":...}` | `cure-job release` |
| `claim` | Gains a `run` field. | `cure-job claim` |
| `closed` | Gains an optional `continued-by: <job id>`. Older versions read only `reason` (`events.py:101-102`). | `cure-job close --continued-by` |

### Approval

| Item | Decision | Reason |
|---|---|---|
| Valid approval | An `approved` event whose digest equals sha256 of the current `goal.md` bytes. | Re-drafting the goal revokes the approval mechanically. |
| Digest normalisation | None. Checked in `_prepare_run` before `rewrite_goal` (`providers/jobs.py:142-152`), only for run 1. | The plugin-path retarget runs only at launch, after the check. |
| `cure-job approve ID [--by user\|auto]` | Legal when the job is open, has no launched run, has no result, and `goal.md` exists. These are the states `held`, `awaiting-approval` and `approved`. The same digest again writes nothing. The dispatcher is the only caller. | One durable record answers "may this session open". |
| Order in a question round | `approve` is the last write of the round. Every answer goes into `goal.md` through `cure:goal` first. `approve --by auto` runs after the step 2 checks and after any `goal.md` edit they cause. | An edit after `approve` changes the digest and revokes the approval just given. |
| `launch` | Run 1 needs a valid approval, else exit 1 "approve first". Later runs need none: relaunch of `lost` or `stalled`, launch of `needs-input`. | The user's answer is the approval for a later run (`agents/dispatcher.md:84`). |
| Solo/Light rule (`agents/dispatcher.md:65`) | Becomes `approve --by auto`. Its condition "holds every resource" moves to launch time. | One approval path. |
| Lock holders | 1. A launched job holds every resource it names that no job ranked before it holds. This covers `launched` through `needs-input`, including `lost`. 2. An unlaunched job takes part only when ready: goal, valid approval, `after` satisfied. This is the run-1 launch test, one predicate in `state.py` for both uses. 3. A ready unlaunched job takes all its resources if none is taken, otherwise none. 4. Every other job holds nothing. 5. `lock_rank` stays (not launched, id) (`state.py:79-82`). | A job that cannot launch holds nothing. The ready test is the launch test, so a new launch condition leaves no holder behind. All or none, so a job blocked on one repository does not keep another idle. An invalid job may have a live session. |

### Derivation order

First match wins:

1. closed -> `abandoned`
2. result failed -> `failed`; result done with no unproven item -> `done`
3. any other result -> `needs-input`
4. a launched event exists -> session states, unchanged
5. `blocked_by` non-empty (a repository held by a launched job or an `approved` job), or `after` not satisfied -> `held`
6. no goal -> `queued`
7. valid approval -> `approved`
8. otherwise -> `awaiting-approval`

`derive` runs one pass in this order: terminal states (`state.py:100`); `satisfied`, true when the
predecessor's terminal state is `DONE`; holders, by the ready test and all or none; `blocked_by`,
the holders of the job's resources minus the job itself; open states; views. `After.state` comes
from the terminal and open states. A job in `invalid_ids` gives `invalid`; an absent one gives
`missing`. No step needs a later one, so no cycle exists.

### Locks of unlaunched jobs

| Reason an unlaunched job cannot launch | State | Holds locks |
|---|---|---|
| No goal, including a split original at `proposed` or `applying` | `queued` or `held` | No |
| Goal, no valid approval | `awaiting-approval` or `held` | No |
| `after` not satisfied: predecessor open, `failed`, `abandoned`, `missing` or `invalid` | `held` | No |
| Ready, but a resource is held by a launched job or a lower-id ready job | `held`, approved true | No (all or none) |
| Job invalid: the files do not read | `invalid` in `list` | Yes, every resource, through `_refuse_invalid` (`providers/jobs.py:8-12,354-358`). It may have a live session. |
| `approved`, the launch-time check raises a question | `approved` | Yes, gated by the dispatcher |

Every id in any `blocked_by` is a job in `launched`, `running`, `stalled`, `blocked`, `lost`,
`needs-input` or `approved`. `approved` means the job holds every resource it names.

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
| `queued`, `awaiting-approval`, `approved` | another unlaunched job naming one of its repos becomes `approved`; for `approved`, only a job with a lower id | `held` |
| `held` | no launched or `approved` job holds any of its repos, and the predecessor is `done`: the last blocker ends, or leaves `approved` without a launch (goal changed, or closed) | `queued`, `awaiting-approval` or `approved` by flags |
| `held`, after | predecessor `failed`, `missing`, or `abandoned` without `continued-by` | stays `held`; the dispatcher closes it |
| `held`, after | predecessor closed with `continued-by` | stays `held`; waits on the continuing job |
| `approved` | `launch` (dispatcher, no question) | `launched` |
| `awaiting-approval` | `launch` | refused, exit 1 |
| `launched` to `lost` | unchanged | unchanged |
| `needs-input` | `resume` or `launch`, no approval needed | `launched` |
| any open state without a session | `close` | `abandoned` |

### `cure-job release <id> <resource>`

| Item | Decision | Reason |
|---|---|---|
| Releasable | Only short holds: `device:*` and `build:*`. Releasing a repo path exits 1 "held until the job ends". | A repo tree holds uncommitted work. Unlaunched jobs are then blocked only by repos. |
| Caller | The job's single claimant (row Single claimant below), for its own job only. Never the dispatcher. | The CLI cannot authenticate callers; this is a stated contract. |
| Idempotence | Exit 0 whenever the job does not hold the resource after the call. Exit 1 only for an unknown or invalid job, or a repo name. | Retries are harmless. |
| Dispatcher rescans | No dispatcher wake on release. After its own `close`, and after a `goal.md` write that revokes an approval, the dispatcher runs `list` again in the same turn. Today it runs `list` once per wake (`agents/dispatcher.md:33-38`). | Unlaunched jobs name only repos. Repos free at `done` or `failed`, followed by the worker's message, or at `abandoned`, the dispatcher's own close. An `approved` job that loses its approval frees its repositories. Short-hold waiters use `claim --wait`. |

### Run-scoped claims

| Item | Decision | Reason |
|---|---|---|
| Claim scope | A short-hold claim counts only while its run is the latest run and no result exists. A `release` cancels it in event order. Repo claims are held to job end. A `claim` without `run`, written by an older version, counts for the whole job. | Finish, needs-input, resume or relaunch drop short holds with no write. A forgotten release is bounded by the run. The scope is derived, not stored (`state.py:1`). |
| Lost session | Keeps its claims until relaunch or close. | Bench state is unknown after a crash. |
| At finish | Short holds free when `result.md` exists. Repos stay held through `needs-input` and free at `done`, `failed` or `abandoned`. | A `needs-input` tree still holds edits. |
| Bench in handoff | `device: bench` no longer adds `device:bench` to `Handoff.resources` (`handoff.py:34-39`). It declares bench use and keeps the resource-risk scope (`skills/goal/job.md:17-18`). The goal writes claim and release around verify. | Otherwise the bench is held from launch. |

### Homes of the short-hold rules

| Rule | Home |
|---|---|
| Resource kind | `resource.py`: `Kind` (`REPO`, `DEVICE`, `BUILD`) and `kind(name)`. `resource.parse` accepts a repo path, `device:bench` or `build:<absolute path>`. |
| Short hold | `resource.is_short_hold(name)`: `Kind.DEVICE` or `Kind.BUILD`. `JobRecord.resources` and the `release` refusal both call it. |
| `build:` name | `resource.build(path)`: `"build:" + os.path.realpath(path)`; `ValueError` for a relative path. |
| Claim run | `events.Claim` gains `run: int \| None`. `None` marks a claim written before run-scoped claims. |
| Claim lock | `JobStore.locked()`, a context manager: `fcntl.flock` on the `jobs/` directory descriptor. `claim` runs its check and append inside it. |

Reason: one source of truth per fact. `JobStore` does every read and write under the state root
(`store.py:1`). A third short-hold kind then changes `resource.py` only.

### `claim` changes and `claim --wait`

| Item | Decision | Reason |
|---|---|---|
| Precondition | `claim` needs a launched run with no result and no close, checked on the record. | A claim outside a run never takes effect. |
| Several resources | `claim ID R1 [R2 ...]` grants every named resource or none. It appends one `claim` event per resource under one lock. | A step that needs a build and the bench takes both at once. |
| No hold and wait | A claim of any kind exits 1 "release <held> first" when the run holds a short hold and the request names a resource the run does not hold. `--wait` accepts only short holds; a repo claim with `--wait` exits 1. | A run that holds a short hold never waits, and only short holds are waited for, so no wait cycle can form. Covering only short-hold requests would let a bench holder `claim --wait` a repository whose holder waits for the bench. The CLI enforces it; the worker prompt does not need to. |
| `--wait SECONDS` | At most 540. Polls every 10 s until every named resource is free, then claims them and exits 0. On timeout exits 1 `ResourceHeld`, naming the resource and its holder. | Fits one foreground Bash call under the 600 s cap. The session stays busy, not `stalled` (`state.py:145-146`). |
| Atomicity | Check and append run inside `JobStore.locked()`. `claim` derives holders from the store snapshot and reads no session list. Each poll takes and drops the lock; no sleep runs under it. The docstring at `providers/jobs.py:5-6` changes. | The id tie-break in `holders()` (`state.py:85-92`) lets a lower-id claimant overtake a running build; the second bitbake fails on `bitbake.lock`. A directory flock creates no lock file. A session list starts `claude agents` (`providers/jobs.py:83`, `claude.py:70-76`) for up to 60 s; holders need only the records, and a `lost` holder keeps its holds anyway. |
| Wait order | Waiters are not ordered. The first poll after a release wins. | Holds per step make releases rare. A queue would need stored waiter state. |
| Wait budget | A worker waits for a short hold for at most 2 hours in total, through repeated `claim --wait` calls. Then it finishes `needs-input` with the question "short-hold timeout: <resource> held by <holder id>". | Bounds the polling cost. One request per 9 minutes. |
| Worker protocol | `skills/goal/worker.md` gains "Short holds". Before each bench step, and before each step that runs a command that takes `bitbake.lock` (`bitbake`, `devtool`, `kas`): `claim --wait` with every short hold the step needs, in one call. Hold them across the step's consecutive commands. At the end of the step, on success or failure: `release` each. | One protocol for every job worker. A release and re-claim between two bitbake commands would let a waiter in mid-step. |
| Single claimant | One claimant per job: the session that dispatches agents. That is the orchestrator in Light and Full, and the worker in Solo. It claims before it dispatches an agent and releases after the agent returns. A dispatched agent never runs `claim` or `release`. | Claims are a set, not a count. An agent's `release` would end the orchestrator's hold. |
| Foreign edits | Before each build claim, the claimant runs `git -C <repo> status --porcelain` for each repository that another open job names in `cure-job list --json`. It records each dirty one in the ledger with that job's id. | Early signal for the `EXTERNALSRC` risk below. A build failure on another job's edits is then named before fix rounds are spent on it. |

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
| View | `JobView` gains `after: After \| None`. `After` holds the predecessor id and its state: a `State`, or `PredecessorGone.MISSING` (no job directory) or `PredecessorGone.INVALID` (the files do not read). `After.satisfied` is true only for `State.DONE`. `blocked_by` keeps resource holders only. `derive` gains `invalid_ids`; its callers are `providers/jobs.py:88` and tests. When the predecessor is `abandoned` with `continued-by`, `After` follows `continued-by` until it reaches a job that is not, and holds that job's id and state. A job reached twice gives `PredecessorGone.INVALID`. | `blocked_by` has one meaning. `list` prints `blocked-by=` as holders (`commands/list.py:36-37,67`). An invalid predecessor is not in `records`, so without `invalid_ids` it would read as missing. Successors of a split job keep every piece of their state. |
| Leaves `held` | When the predecessor derives `done`. `needs-input`, including done with an unproven item, keeps it held. | The successor's branch base exists only after `done`; a successor never runs after a failure. |
| Locks | A job whose `after` is not satisfied holds nothing, whatever its approval. `satisfied` is computed from the terminal states before `holders`. | A predecessor at `needs-input` waits for the user; a successor on another repository must not stop that repository's queue. |
| `launch` while after-blocked | The `is_launchable` refusal (`providers/jobs.py:95-97`) runs before `_prepare_run`. For a `held` job with an unsatisfied `after` it exits 1 `after <pred> is <state>`. | A `held` job never reaches `_prepare_run`. `providers/jobs.py:144-147` names a held resource with `next()`; it stays correct when `blocked_by` holds only holders. |
| `list --json` | `after` is the resolved predecessor id. `after-state` is its state, `missing` or `invalid`. `continued-by` is the id a closed job names, else null. | The dispatcher's only input. |
| Predecessor failed, missing, or abandoned without `continued-by` | The CLI derives `held`. The dispatcher closes the successor without asking and sends the origin "closed: predecessor <id> <state>; re-dispatch" (as `skills/goal/job.md:94`). Successors of the closed job follow on the next scan. | A failed job is terminal (`state.py:45`). |
| Predecessor invalid | The dispatcher does nothing for the successor. The `invalid` row already asks the user to repair the predecessor. | Closing would be wrong while the user repairs the file. |
| `base` | For each repository R of the job, `cure:goal` job mode sets `base` to the branch of the nearest job on the resolved `after` chain that changes R. It reads that branch from the job's `goal.md`. The walk starts at the row's `after` in `cure-job list --json`, never the handoff's `after:`. Each step moves to the current job's row `after`, which `derive` resolves through `continued-by`. The walk stops at the first job that changes R. When no job on the chain changes R, `base` comes from the handoff as today. Every job the walk passes is `done`, because each link waits for the one before it. The dispatcher drafts a successor's goal only after the predecessor's row has `goal` true. | Handoff `branch` may be `current` (`skills/dispatch/defaults.md:12`). A branch exists only in its own repository. The last job of a chain may not change every repository of the successor. Split rule 7 puts an under-limit repository in the part that needs it, which need not be the last part. |
| Base check | For a base taken from a predecessor, work item 1 compares `<base>` with the local branch, not with `origin/<base>`. When `origin/<base>` exists, it checks `git merge-base --is-ancestor origin/<base> <base>`; a failure is a failure cause. Other bases keep the check of `skills/goal/rules.md:9-11`. | With `delivery: commit`, the default (`skills/dispatch/defaults.md:10`), the predecessor commits locally and nothing pushes. `origin/<base>` lacks its commits, and "base the work on `origin/<base>`" would drop them. |
| Base commit | Work item 1 records `git rev-parse <base>` as the base commit: in the ledger, or in the transcript for Solo. The diff cap (`skills/goal/job.md:127-128`) and the retrospective's changed lines measure against it. | With `branch: current` the successor commits on `<base>` itself. A cap against the branch name would count only uncommitted lines. |
| Cycles | No check at `new`: the predecessor must exist and the new id is fresh. `close ID --continued-by X` exits 1 when X is unknown, invalid, not open, ID itself, or its resolved `after` chain reaches ID. `derive` follows `after` one hop and `continued-by` any number of hops, and stops at a job reached twice. | Re-pointing through `continued-by` can build a cycle; `new` alone cannot. |
| Prune | `prune` keeps an expired job named by an open job's `after`, and every job on the `continued-by` chain from it (`providers/jobs.py:326-334`, `state.py:55-59`). | Otherwise a pruned predecessor closes its successor. |

### Dispatcher table changes

| Row | Action |
|---|---|
| `held`, no goal | Steps 1, 2 and 4: draft, checks, summary. Ask for approval in the question round. Step 3, the uncommitted-changes question (`agents/dispatcher.md:63`), waits for the `approved` row. |
| `held`, goal, not approved | Ask once. Record every answer in `goal.md`, then `approve` as the last write. |
| `queued` | Steps 1, 2 and 4, as for `held`, no goal. The condition "If the job holds its resources" (`agents/dispatcher.md:46`) is removed. |
| `held`, approved | Nothing. |
| `held`, `after-state` `failed`, `abandoned` or `missing` | `close` the successor, tell the origin, run `list` again. |
| `held`, `after-state` `invalid` | Nothing. |
| `approved` | Re-run steps 2 and 3, then `launch`. A question from either keeps the job `approved` and holding until the answer. |
| `needs-input` whose only question is a short-hold timeout | Ask the user, naming the resource and its holder. Never settle it as `(recommended)`. |

A held job's repository is held by a launched job, which edits that tree, or by an `approved` job
about to launch. Step 3 at draft time would ask about that job's edits. A dirty tree at launch stops the auto-launch for a question.

### Risks

| Risk | Impact | Early signal | Mitigation |
|---|---|---|---|
| Another job's in-progress edits enter this job's image build via `EXTERNALSRC`. | The build fails, or verify runs with foreign changes. | The foreign-edits check before each build claim. | Build own recipes where verify allows; name the cause in the retrospective. |
| Bench jobs lose the launch-time bench lock at the part 1 upgrade. | Two jobs on the bench. | `list` shows two running `device: bench` jobs. | Upgrade with no `device: bench` job open. The part 1 PR states this. |
| A worker forgets `release`. | The bench is held until the run ends. | A waiter's timeout names the holder. | Run-scoped claims. |
| A lost session keeps short holds. | Other workers wait. | `list` shows the holder `lost`. | Deliberate. |
| A wide multi-repo job starves: jobs on any one of its repositories, later ones included, keep launching. | It waits with no bound. | A `held` approved job whose `blocked-by` names a higher id. | None built. |
| An `approved` job's launch-time question stays unanswered. | It keeps its repositories. | It stays `approved` across wakes; the question round names the job. | None built. |

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
| `plan` (default) | `cure:goal` job mode | Return by `split.md` status; see [Plan by status](#plan-by-status). |
| `apply` | dispatcher, after the user chooses apply | Create tickets and jobs, close the original with `continued-by`. |
| `decline` | dispatcher, after the user chooses run as one | Set `status: declined`. |

`$ARGUMENTS` is `<job dir> [plan|apply|decline]`. The skill reads `<job>/handoff.md`. The job id
is the directory name (`skills/goal/job.md:8`). The skill reads
`${CURE_JOB_ROOT:-~/.claude/cure}/defaults.md` for the limit and tracker rows.

### Plan state files

| File | Content |
|---|---|
| `<job>/split.md` | Frontmatter: `status: proposed \| declined \| applying \| applied`, `original`, `limit`, `tracker`, `error`. Body: `## Estimate` (table), `## Parts` (table: k, slug, repos, outcome, estimate, after, ticket, job), `## Summary` (3 lines). |
| `<job>/part-<k>.md` | One handoff per part. |

`cure:split` is the only reader and writer of these files. The dispatcher reads only the skill's
return line, and prints the Summary lines from it. The store ignores files it does not name
(`store.py:5-6,28-31`). The plan survives between wakes.

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
| `ticket:`, `after:`, `origin:` | Empty until apply. Apply fills them in step 1.2. |
| `branch` | With `delivery: pr`: `<original branch>-part<k>`. With `delivery: commit`: the original branch; the parts stack as commits on it. |
| Slug | `<original slug>-part<k>`. It passes `_slug_arg` (`commands/new.py:42-47`). |

### Plan by status

| `split.md` | `plan` returns | `plan` writes |
|---|---|---|
| absent | `no split: ...`, or `split proposed: <path>` and the 3 Summary lines | the plan files, only when proposed |
| `proposed` | `split proposed: <path>` and the 3 Summary lines, read from the file | nothing |
| `declined` | `no split: declined, estimate ~N` | nothing |
| `applying` | `split applying: <path>; parts done <k...>, jobs <ids>; last error <error>` | nothing |
| `applied` | not reached: the original is `abandoned` | nothing |

On any `split ...` return, `cure:goal` writes no `goal.md`, skips its question round and reports
the line in place of the launch line (`skills/goal/job.md:148`). The job stays `queued` without a
goal (`state.py:154`) and cannot be launched. A fork starts on every wake for such a job; it reads
one file.

### Dispatcher, apply and decline

| Step | Decision | Reason |
|---|---|---|
| Dispatcher, `split proposed` | In step 1 (`agents/dispatcher.md:61`), print the 3 Summary lines from the return and ask in the question round: apply, or run as one job. A split is never auto-launched. `agents/dispatcher.md:120` allows `split.md` and `part-<k>.md` through `cure:split`. After apply, the dispatcher sends the origin the returned line and runs `cure-job list` again. A successor's origin is not told: the successor keeps its id. | The return line is the single interface; later wakes re-print from it. |
| Dispatcher, `split applying` | Show the last error and ask: retry apply, or abandon. Abandon closes the original and each part job the return line names. "Run as one" is not offered once a part job exists. | The parts already exist. |
| Decline | `status: declined`. The dispatcher then runs step 1 again. | The decision persists across wakes. |

#### Continuation through `continued-by`

The brief's "closed with pointers to the parts" is refined here. The `closed` event of the original
carries `continued-by: <last part id>`. `derive` resolves each successor's `after` through it.

| # | Decision | Reason |
|---|---|---|
| 1 | `cure-job close ID --continued-by X` writes `continued-by: X` in the `closed` event. | One append, and apply runs it last. No window between re-point and close. |
| 2 | The effective predecessor is the declared `after`, followed through every `abandoned` job with `continued-by`. | Successors keep id, origin, goal, approval and lock order. Grandchildren are untouched. Late successors resolve. |
| 3 | `close --continued-by X` exits 1 and writes nothing when X is unknown, invalid, not open, the job itself, or a job whose resolved `after` chain reaches the job. `derive` gives `PredecessorGone.INVALID` at a job reached twice. | Re-pointing makes a cycle possible. |
| 4 | Parts carry the original's origin in the handoff key `origin:`, filled from the original's `list --json` row. | `handoff.py:57-62` parses it and `job.py:60` falls back to it. It is written in the same rename as the handoff (`store.py:83-85`), so no crash window exists. |
| 5 | The skill reads every CLI-derived value of the original (`origin`, `after`, `state`, `goal`) from `cure-job list --json`, never from `handoff.md`. | A handoff does not hold derived values. |
| 6 | Apply proceeds only when the original's row is `queued` or `held` with `goal` false, or `abandoned` with `continued-by` equal to the recorded last part. | Then no goal, approval, run, claim or result exists. |
| 7 | No generic `cure-job replace` and no CLI `split`. | See [Rejected](#rejected). |

| Item at apply | Parts | Successors |
|---|---|---|
| Job id, lock order | Fresh id per part | Kept |
| `repos`, `device`, `outcome`, Work, Done when | Per part | Kept |
| `ticket` | New per part; with tracker none, the original's | Kept |
| `branch` | Per part | Kept |
| `base`, `delivery` | Copied; part k > 1 takes `base` per repository by the `after` chain walk (`base` row in `after: <id>`) | Kept; `base` per repository by the same walk |
| Settled, Resource risk, Tools | Copied | Kept |
| Open | First part it affects | Kept |
| `after` | Part 1: the original's row `after`; k > 1: part k-1's id | Kept; resolves to the last part |
| `origin` | `origin:` key from the original's row; omitted when null | Kept |
| `split-from` | Original id | n/a |
| `goal.md`, `approved`, `launched`, results | None exist (decision 6) | Kept |
| `claim`, `release` | None; the close frees the original's | Kept |
| `closed` | Written once on the original with `continued-by: <last part>` | Not written |
| `split.md`, `part-<k>.md` | Stay with the original, pruned with it | n/a |

The original's origin gets the apply return line. A successor's origin is told nothing.

#### Apply procedure

Apply first reads the original's row in `cure-job list --json`. It returns
`failed: <original> is <state>` unless the row is `queued` or `held` with `goal` false, or
`abandoned` with `continued-by` equal to the last part id in `split.md`. In that last case it goes
to step 4. Otherwise it sets `status: applying` and runs these steps. Each step records its result
in `split.md` before the next. Each create looks for an earlier result first.

1. Per part k in order:
   1. If a tracker is active and the row has no ticket: search the tracker for the title
      `<original id> part k/n` (GitHub: `gh issue list --search "<original id> part k/n in:title"
      --state all`). Record a match. Otherwise create the ticket with that title and record it.
   2. Fill `ticket:`, `after:` and `origin:` in `part-<k>.md`. Part 1 takes the original's row
      `after`. Part k > 1 takes part k-1's job id. Every part takes the original's row `origin`;
      omit the key when it is null.
   3. If the row has no job: search `${CURE_JOB_ROOT:-~/.claude/cure}/jobs/*/handoff.md` for the
      Settled line "Split: part k of n of <original id>". Record a match. Otherwise run
      `cure-job new --slug <slug> <job>/part-<k>.md` and record the id.
2. Comment the part tickets on the original ticket if it is in the same tracker.
3. Run `cure-job close <original> --continued-by <last part id> --reason "split into <id1>, <id2>, ..."`
   (`commands/close.py:18`).
4. Set `status: applied`. Run `cure-job list --json`. Return
   `job <original> closed: split into <ids>[; <ids> wait on <last part id>]`, naming each open row
   whose `after` is the last part id.

On a failure, apply stops before that part's `cure-job new`, writes `error:` and returns
`failed at part k: <error>`. The original is closed last. Until then its successors wait on it. From
then on `derive` resolves them to the last part. No successor is re-created. The fork has no
`SendMessage`.

The GitHub search index can lag a just-created issue by seconds. A crash inside that lag can still
create a second ticket.

### 3-line summary

| Line | Split job |
|---|---|
| 1 | `<id>: <outcome> -> split into <n> parts in <repo>; estimate ~<total>, limit <L>` |
| 2 | `1 <slug> ~<lines>; 2 <slug> ~<lines> after 1; ...` |
| 3 | `tickets: <n> new in <tracker> \| none: <reason>; original closed on apply[; <ids> wait on part <n>]` |

For an unsplit job, line 2 of the normal summary (`agents/dispatcher.md:64`) gains `~N lines`.

### Risks

| Risk | Mitigation |
|---|---|
| Unverified: a `context: fork` skill forks when the caller has no `Agent` tool and honours `allowed-tools`. | The fork probe runs before part 1 and its result is recorded here. Fallback when it fails: `cure:split plan` runs as `timeout 540 claude -p "/cure:split <job dir> plan"` in one foreground Bash call, under the 600 s cap. It passes no `--allowedTools` (`skills/goal/job.md:97`); the skill's `allowed-tools` grant its tools. On a timeout the dispatcher asks: retry, or run as one job. Only the return line enters the dispatcher context. The fallback needs no CLI change. Part 5 done-when 2 re-tests the chosen path. |
| The estimate may read a tree another job edits. | Accepted within the 2x margin. |
| The close reason is not in `cure-job list --json` (`commands/list.py:59-72`). | Pointers live in `dispatch.jsonl`, the origin message and the ticket. |

## Design note

### `capture-idea` removal

`~/.claude/ideas/` files lie outside the repository. Part 6 does not touch them.

| File | Change |
|---|---|
| `plugins/cure/skills/capture-idea/SKILL.md` | Delete the file and the directory. |
| `README.md:141` | Delete the `capture-idea` row. |
| `README.md:142` | The `note` row gains "and design notes (problem, decisions, rejected, open, next steps)". |
| `plugins/cure/skills/note/SKILL.md:2` | The description gains the trigger phrases of `capture-idea`: "save this idea", "capture this for later", "write this design down". |
| `plugins/cure/.claude-plugin/plugin.json:3` | Bump the version. |

`git grep -n -i "capture-idea\|capture_idea\|capture idea\|claude/ideas\|ideas/" --
':!docs/dispatcher-resource-scheduling.md'` finds no tracked mention outside these files.

### `cure:note` design-note anatomy

| Item | Decision | Reason |
|---|---|---|
| Place | A `## Design note` section in `skills/note/SKILL.md` after Anatomy (`:28-46`), with the template inline. A command row `/note design <title>` in Commands (`:48-55`). | About 40 lines. The sweep needs it too. |
| Frontmatter | The existing five keys. No `kind:` key. `supersedes_when` names the design document or the implementing PR. | Nothing would read `kind`. |
| Layout | `# <Title>`, `## Problem`, `## Decisions` (table Decision \| Reason), `## Rejected` (table Alternative \| Reason), `## Open decisions` (omitted when none), `## Next steps` (numbered). | The layout of the brief this document came from, with Decisions and Rejected as top-level sections. |
| Rules carried over | Write from the conversation. One idea per file. If `.notes/<slug>.md` exists, update it and do not overwrite agreed rows. | `capture-idea` `:25-28`, `:30-32`, `:65-71`. |
| Sweep | A design note is covered only when every Decisions, Rejected and Open decisions row is in the artifact. | Extends the sweep rule (`:64-65`) to the tables. |

## Decisions on the open questions

### Tracker detection and authentication

Decision: detect the tracker at plan time, first match wins. Authenticate only through a client
that is already logged in. Part 5 ships the GitHub row only.

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
| Tracker table | One row per tracker in `SKILL.md`: detect, auth check, search by title, create, comment. |
| Jira | A Jira key is detected and reported `tracker: none (no Jira client configured)`. A Jira row is added when the user names a client. |
| No tracker at plan | No tracker, an unsupported tracker or a failed auth check gives `tracker: none <reason>`. Summary line 3 states the reason and the fix, for example `gh auth login`. The user chooses apply without tickets, or run as one. Parts copy the original `ticket:`. |
| Failure during apply | Auth, search or create fails: stop before that part's `cure-job new`. `split.md` keeps progress. Return `failed at part k: <error>`. A later `apply` resumes. |

Reason: the ticket form and an explicit setting are direct evidence, and the repository fallback
spares a `defaults.md` row per repository. Credentials stay with the user's own client.

### Approval expiry for a `held` approved job

Decision: no expiry by time. Only a change of the `goal.md` digest revokes an approval. To
withdraw an approval, the user closes the job or the goal is re-drafted.

Reason: a time limit brings the user back on every long wait. Prelaunch checks re-run on every wake
before launch (`skills/goal/job.md:58`), followed by the uncommitted-changes question
(`agents/dispatcher.md:63`). Stale code facts fail in work item 1 (`skills/goal/rules.md:9-11`).

### Who fills `build:<dir>`

Decision: the worker fills it at claim time, from the directory the build runs in. The handoff
never names a `build:` resource.

Reason: a handoff resource is held from queue to job end and would block other jobs' edits and
reviews. The cost is that the dispatcher cannot foresee build contention; a worker resolves it by
waiting with `claim --wait`.

### More than one bench device name

Decision: `device:bench` stays the only name. `Device` stays a closed set (`handoff.py:19-21`,
`resource.py:6`). No second bench is assumed. When a second bench exists, names come from a
`<root>/devices` file, one name per line, and unknown names are refused. Name-to-address mapping
stays in `defaults.md`.

Reason: there is one bench. An open `device:<name>` grammar turns a typo into a resource that never
conflicts.

## Parts

All parts change claude-plugins only. Each part is one job and one PR. Each part that changes
`plugins/cure/` bumps the plugin version.

Order: fork probe, then parts 1-6. Reasons:

- The probe tests the largest unknown first. Its fallback needs no CLI change, so parts 1-4 do not
  wait on it.
- Part 1 ships one short-hold kind, so no two short holds can nest. Part 2 adds the second kind
  together with the all-or-none claim that prevents the deadlock. Together the two come to about
  790 lines, near the 800-line trigger.
- Parts 3-5 stack: approval, then `after:`, then the split, which uses `after:`.
- Part 6 is independent.

0. Fork probe, before part 1
   - Issue: #31 (Probe whether a context: fork skill forks from the dispatcher)
   - Estimate: 0 changed lines in claude-plugins (a manual session with a throwaway skill that is not committed).
   - No PR. One manual session.
   - Method: a throwaway skill of about 20 lines with `context: fork` and `allowed-tools: Read`,
     invoked from a session started with `--agent cure:dispatcher`.
   - Done when: the split risk row records whether the skill forked and whether `allowed-tools`
     held. It names the path part 5 takes.

1. Short holds: `release`, run-scoped claims, `claim --wait` for the bench
   - Issue: #32 (Add cure-job release and run-scoped short holds for the bench)
   - Scope: `release` command and event; `run` field on claims; `claim` precondition, `--wait`, `JobStore.locked()` and holders from the snapshot; `resource.Kind` and `is_short_hold`; `device: bench` no longer a handoff resource; worker "Short holds" protocol with the single claimant; dispatcher row for a short-hold timeout.
   - Files: `cli/src/cure_job/` `resource.py`, `events.py`, `job.py`, `handoff.py`, `store.py`, `providers/jobs.py`, `commands/claim.py`, new `commands/release.py`, `cli.py`; tests `test_events`, `test_jobs`, `test_state`, `test_cli`, `test_handoff` (about 44 bench references); `skills/goal/worker.md`, `skills/goal/job.md`, `skills/dispatch/SKILL.md:26`, `agents/dispatcher.md`; `plugin.json`.
   - Estimate: 525 changed lines in claude-plugins (195 code, 280 tests, 50 docs).
   - Depends on: none.
   - Done when:
     1. Two launched jobs: B's bench claim exits 1 naming A. After A's `release`, B's `claim --wait` exits 0 (fake clock).
     2. A run-1 claim is absent from `resources` after `finish` and after run 2 starts.
     3. `release` of a repo exits 1. A second `release` of a device exits 0.
     4. `device: bench` no longer blocks a second job at launch.
     5. A legacy `claim` without `run` still counts.
     6. `claim --wait` reads no session list, and no fake sleep runs while the lock is held.
     7. `skills/goal/worker.md` names the single claimant and states that a dispatched agent never claims.
     8. `pytest` and `scripts/lint-plugin.py` pass.

2. `build:<dir>` and the all-or-none claim
   - Issue: #33 (Add the build:<dir> resource and the all-or-none claim)
   - Scope: `build:<dir>` kind and `resource.build`; `claim ID R1 [R2 ...]`, all or none; the hold-and-wait refusal; worker protocol for build steps, holds across a step and the foreign-edits check.
   - Files: `resource.py`, `providers/jobs.py`, `commands/claim.py`; tests `test_jobs`, `test_cli`; `skills/goal/worker.md`; `plugin.json`.
   - Estimate: 265 changed lines in claude-plugins (105 code, 125 tests, 35 docs).
   - Depends on: part 1.
   - Done when:
     1. `claim ID build:<symlinked or ../ path>` stores the realpath.
     2. `claim ID build:/w device:bench` with the bench held writes no event.
     3. A run holding `device:bench` gets exit 1 for `claim --wait ID build:/w` and for `claim ID <repo>`. `claim --wait ID <repo>` exits 1.
     4. `skills/goal/worker.md` states one call per step and the foreign-edits check.
     5. `pytest` and `scripts/lint-plugin.py` pass.

3. Approval while held, auto-launch
   - Issue: #34 (Approve a held job and launch it when its resources free)
   - Scope: `approved` event bound to the goal digest; `cure-job approve`; state `approved`; `held` with or without a goal; run-1 launch needs approval; `holders` takes launched jobs and ready unlaunched jobs, all or none; `lock_rank` unchanged; `list --json` fields `goal` and `approved`; dispatcher table rows for `queued`, `held` and `approved`, with step 3 moved to `approved` and `approve` as the last write; Solo/Light rule as `approve --by auto`.
   - Files: `events.py`, `job.py`, `store.py`, `goal.py` or a digest helper, `state.py` (the ready predicate; `held[name]` at `:107` becomes `held.get(name)`), `providers/jobs.py` (`held[name]` at `:146` becomes `.get`; `Listing` may carry the holders map `derive` built), new `commands/approve.py`, `cli.py`, `commands/list.py`; tests (an approving builder helper; about 68 `launch` call sites); `agents/dispatcher.md`, the launch line in `skills/goal/job.md`, `README.md:107`; `plugin.json`.
   - Estimate: 615 changed lines in claude-plugins (175 code, 370 tests, 70 docs).
   - Depends on: part 2.
   - Done when:
     1. A blocked job with a goal lists `held` with `goal` true.
     2. `approve` then `launch` succeeds. `launch` without `approve` exits 1.
     3. Editing `goal.md` after `approve` returns `approved` to `awaiting-approval`, and `list` shows approved false.
     4. After the blocker is `done`, the held approved job lists `approved` with no new event.
     5. A `needs-input` launch or resume needs no approval.
     6. Of two unlaunched jobs on one repo, the approved higher id holds it. The unapproved lower id lists `held`, `blocked-by` naming it.
     7. An approved job on X and Y, with X held by a launched job, holds nothing. A later approved job on Y lists `approved`.
     8. No `blocked-by` names a job in `queued`, `held` or `awaiting-approval`.
     9. A job whose resources become unheld does not raise `KeyError` in `derive` or `launch`.
     10. `agents/dispatcher.md` runs step 3 only in the `approved` row and names `approve` as the last write of a round.
     11. `pytest` and `scripts/lint-plugin.py` pass.

4. `after:` ordering
   - Issue: #35 (Order stacked jobs with after: in the handoff)
   - Scope: handoff key `after:`; `JobView.after` and `PredecessorGone`; `derive` gains `invalid_ids`; `after` and `after-state` in `list`; launch refusal; the ready test excludes a job whose `after` is not satisfied; prune guard; `base` per repository from the nearest job on the resolved `after` chain that changes the repository, which `cure:goal` walks from the row's `after`, with the local base check and the base commit; dispatcher rows for the successor of a failed, abandoned, missing or invalid predecessor.
   - Files: `handoff.py`, `state.py`, `providers/jobs.py`, `commands/list.py`; tests; `skills/dispatch/SKILL.md`, `skills/dispatch/template.md`, `skills/goal/job.md`, `skills/goal/SKILL.md`, `skills/goal/rules.md`, `agents/dispatcher.md`; `plugin.json`.
   - Estimate: 400 changed lines in claude-plugins (115 code, 220 tests, 65 docs).
   - Depends on: part 3.
   - Done when:
     1. `new` with an unknown `after` exits 1.
     2. The successor is `held` with an empty `blocked-by` and `after-state` set until the predecessor is `done`. `needs-input` keeps it held.
     3. `launch` of an after-held job exits 1 `after <id> is <state>` from the `is_launchable` refusal (`providers/jobs.py:95-97`), with no traceback.
     4. A failed predecessor gives `after-state: failed`. An invalid predecessor gives `invalid`; a removed one gives `missing`.
     5. `prune` keeps an expired predecessor of an open job.
     6. `skills/goal/rules.md` states the local base check and the base commit for a predecessor's base.
     7. An approved successor on Y, whose predecessor names only X and is `needs-input`, holds nothing. A later approved job on Y lists `approved`.
     8. The split case: jobs P1 on A and B, P2 on A after P1, and P3 on A after P2, then S on B after P3. S's stacked B commits are in P1, an earlier part, not the last part. S takes P1's branch as `base` for B.
     9. `pytest` and `scripts/lint-plugin.py` pass.

5. Split skill with tracker tickets
   - Issue: #36 (Add the cure:split skill with tracker tickets)
   - Scope: `cure:split` with `plan`, `apply` and `decline`; plan state files; plan by status; look-first apply; `close --continued-by` and `after` resolution through it; `continued-by` in `list --json`; part handoffs carry `origin:`; the apply precondition; estimation and trigger; GitHub tracker row; call from `cure:goal` job mode; dispatcher rows for `split proposed` and `split applying`; lint keys.
   - Files: `events.py` (about 8), `state.py` (about 20), `providers/jobs.py` (about 20), `commands/close.py` (about 5), `commands/list.py` (about 2); tests `test_events` (about 15), `test_state` (about 50), `test_jobs` (about 40), `test_cli` (about 15); `skills/split/SKILL.md` (new, about 190), `skills/split/template.md` (new, about 55), `skills/goal/job.md` (about 25), `skills/goal/SKILL.md` (about 8), `agents/dispatcher.md` (about 30), `skills/dispatch/defaults.md` (about 4), `scripts/lint-plugin.py` (about 6), `cli/tests/test_lint_plugin.py` (about 15), `README.md` (about 6), `plugin.json` (2), `cli/tests/test_handoff.py` (about 10).
   - Estimate: 525 changed lines in claude-plugins (60 code, 145 tests, 320 skill and doc).
   - Depends on: part 4 (`after:`).
   - Done when:
     1. `scripts/lint-plugin.py` exits 0.
     2. From a session without `Agent`, `cure:split` runs on the path the fork probe chose. The main transcript has no Read of repository source.
     3. With a temporary `CURE_JOB_ROOT`, an over-limit fixture and tracker none: `split.md` is `proposed`, has n >= 2 parts each at or below the limit, and a 3-line Summary.
     4. `apply` creates n jobs in `cure-job list --json`. Part k > 1 has `after:` equal to part k-1's id. Each part's row has the original's `origin`. The original is `abandoned`, its row has `continued-by` equal to the last part's id, and the reason is in `dispatch.jsonl`.
     5. A second `apply` leaves the job count unchanged.
     6. With `split.md` at `applying` and part 1's job present but not recorded, `apply` creates no second job for part 1.
     7. Jobs S (`after: <original>`) and T (`after: S`), queued before apply, keep their ids, origins and states. S lists `after` equal to the last part's id. T is open after the next dispatcher scan. A job queued with `after: <original>` after apply also lists the last part.
     8. `plan` on `proposed` and on `applying` writes no file.
     9. CLI tests pass.
     10. The version is bumped.
     11. The GitHub ticket path, with the title search, is checked by hand as a PR-checklist item, with no scratch repository.
     12. `close --continued-by X` exits 1 and writes nothing when X is unknown, not open, the job itself, or a job whose `after` chain reaches the job.
     13. `prune` keeps an expired original while an open job's `after` chain passes through it.
     14. With `split.md` at `applying` and the original `abandoned` with `continued-by` equal to the last part's id, `apply` writes no event and sets `applied`.

6. Remove `capture-idea`, extend `cure:note`
   - Issue: #37 (Remove capture-idea and add the design note to cure:note)
   - Scope: the file list in [`capture-idea` removal](#capture-idea-removal) and the [design-note anatomy](#curenote-design-note-anatomy).
   - Files: `skills/capture-idea/SKILL.md` (deleted, 71), `skills/note/SKILL.md` (about 45), `README.md` (about 3), `plugin.json` (2).
   - Estimate: 121 changed lines in claude-plugins.
   - Depends on: none. It conflicts textually with other parts only in `plugin.json` and the README skills table.
   - Done when:
     1. `test ! -e plugins/cure/skills/capture-idea` succeeds.
     2. `git grep -n capture-idea -- ':!docs/dispatcher-resource-scheduling.md'` prints nothing.
     3. `skills/note/SKILL.md` contains `/note design` and the five design-note headings.
     4. `scripts/lint-plugin.py` exits 0.
     5. The version is bumped.
