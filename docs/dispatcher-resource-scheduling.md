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
| Add `cure-job next --json`. It returns each job that needs a dispatcher action, with the action. The dispatcher prompt maps actions to procedures; the CLI computes the conditions. | The dispatcher prompt shrinks. Conditions become tested code. |
| Add `config.json` under the state root. It replaces `defaults.md`. The CLI reads and validates it; skills and agents read values through `cure-job config get`. | One validated file for the handoff defaults and the tunable values of the CLI, the dispatcher and the skills. |
| Split in `cure:dispatch`, in the working session, before the handoff is written. Each part is a plain job, chained to the previous part with `after:`. | The working session holds the context and the user. The dispatcher and the CLI need no split logic. |
| Split trigger: estimated change in one repository above `split.limit` (default 800). | Reviewable PR size. A model estimate can be off by about 2x, so the value is a trigger, not a hard limit. |
| Split rule: each part builds, passes its tests and is reviewable alone. Cut at interfaces or layers. A cross-repo job splits only in the repo that exceeds the limit. | Each part is a mergeable PR. |
| With `delivery: pr`, each part has its own ticket. | One PR per repository per ticket. |
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
| `kind:` frontmatter key for design notes. | Nothing reads it. |
| Short holds acquired in a fixed order (`build:` before `device:`), enforced by the worker prompt only. | The CLI cannot check it. A worker that breaks it deadlocks two jobs for the full wait budget. |
| A `wait` event and a `claim-wait` field in `list --json`. | No claim waits while its run holds a short hold, and only short holds are waited for, so no wait cycle remains to show. The timeout exit names the resource and its holder. |
| Allow `after:` only with `delivery: pr`. | Stacking would not work with the default delivery. |
| Lock rank (not launched, not after-satisfied, not approved, id). | A ready job blocked on X still holds Y. Each new launch condition needs a new term. |
| Ready filter for lock holders without all or none. | A partial hold remains. |
| A reservation for every open job. | One unanswered question stops a repository's queue. |
| Lock order by approval time. | Re-approval reorders the queue. Approval stamps are local time. |
| Split as a `context: fork` skill run by the dispatcher through `cure:goal`. | It needs plan state files, apply and decline modes, `close --continued-by` and a probe of fork behaviour without the `Agent` tool. The dispatcher cannot ask the user during the estimate. |
| A separate long-lived scheduler session. | Scheduling is deterministic and lives in the CLI. A second session adds a context, a message protocol between sessions and turn costs. |
| Keep `defaults.md` and add a second file for tunable values. | Two files for one purpose. A markdown table has no validator, and the CLI cannot read it. |
| Ask for every part's ticket even with `delivery: commit`. | Parts with `delivery: commit` stack as commits on one branch and open no PR. |

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
longer launchable. `list --json` gains the fields `goal`, `approved`, `after` and `after-state`.

### Events

Existing events: `launched`, `claim`, `closed`, `origin`, `reported`, `stopped`, `sessions-removed`
(`events.py:58-64`). New events:

| Event | Form | Writer |
|---|---|---|
| `approved` | `{"event":"approved","goal":"sha256:<hex>","by":"user"\|"auto","at":...}` | `cure-job approve` |
| `release` | `{"event":"release","resource":...}` | `cure-job release` |
| `claim` | Gains a `run` field. | `cure-job claim` |

### Approval

| Item | Decision | Reason |
|---|---|---|
| Valid approval | An `approved` event whose digest equals sha256 of the current `goal.md` bytes. | Re-drafting the goal revokes the approval mechanically. |
| Digest normalisation | None. `derive` compares the digest when it computes the state. `launch` reads the state before `_prepare_run` rewrites `goal.md` (`providers/jobs.py:152`). | The plugin-path retarget runs only at launch, after the check. A failed run-1 launch after a plugin update re-asks approval: the rewrite comes before `claude.start` (`providers/jobs.py:162`), and a `ClaudeError` (`providers/jobs.py:167-172`) leaves `goal.md` rewritten with no `launched` event. A digest over the text retargeted to a fixed placeholder is not used: a checkout plugin root does not match the cache pattern (`goal.py:22`). |
| `cure-job approve ID [--by user\|auto]` | Legal when the job is open, has no launched run, has no result, and `goal.md` exists. These are the states `held`, `awaiting-approval` and `approved`. The same digest again writes nothing. The dispatcher is the only caller. | One durable record answers "may this session open". |
| Order in a question round | `approve` is the last write of the round. Every answer goes into `goal.md` through `cure:goal` first. `approve --by auto` runs after the step 2 checks and after any `goal.md` edit they cause. | An edit after `approve` changes the digest and revokes the approval just given. |
| `launch` | Run 1 needs the state `approved`. The `is_launchable` refusal (`providers/jobs.py:95-97`) is the only check. For `awaiting-approval` its message names `cure-job approve <id>`. `_prepare_run` has no approval check. Later runs need none: relaunch of `lost` or `stalled`, launch of `needs-input`. | The user's answer is the approval for a later run (`agents/dispatcher.md:84`). |
| Solo/Light rule (`agents/dispatcher.md:65`) | Becomes `approve --by auto` for a tier in `dispatcher.auto-approve-tiers`. Its condition "holds every resource" moves to launch time. | One approval path. |
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
| No goal | `queued` or `held` | No |
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
| `held`, after | predecessor `failed`, `missing` or `abandoned` | stays `held`; the dispatcher closes it (`next` action `close-successor`) |
| `approved` | `launch` (dispatcher, no question) | `launched` |
| `awaiting-approval` | `launch` | refused, exit 1 naming `cure-job approve <id>` |
| `launched` to `lost` | unchanged | unchanged |
| `needs-input` | `resume` or `launch`, no approval needed | `launched` |
| any open state without a session | `close` | `abandoned` |

### `cure-job release <id> <resource>`

| Item | Decision | Reason |
|---|---|---|
| Releasable | Only short holds: `device:*` and `build:*`. Releasing a repo path exits 1 "held until the job ends". | A repo tree holds uncommitted work. Unlaunched jobs are then blocked only by repos. |
| Caller | The job's single claimant (row Single claimant below), for its own job only. Never the dispatcher. | The CLI cannot authenticate callers; this is a stated contract. |
| Idempotence | Exit 0 whenever the job does not hold the resource after the call. Exit 1 only for an unknown or invalid job, or a repo name. | Retries are harmless. |
| Dispatcher rescans | No dispatcher wake on release. The wake loop of `cure-job next` re-runs `next` after each state-changing action. Today the dispatcher runs `list` once per wake (`agents/dispatcher.md:33-38`). | Unlaunched jobs name only repos. Repos free at `done` or `failed`, followed by the worker's message, or at `abandoned`, the dispatcher's own close. An `approved` job that loses its approval frees its repositories. Short-hold waiters use `claim --wait`. |

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
| Wait budget | A worker waits for a short hold for at most `short-hold.wait-total-minutes` (default 120) in total, through repeated `claim --wait` calls. Then it finishes `needs-input` with the question "short-hold timeout: <resource> held by <holder id>". | Bounds the polling cost. One request per 9 minutes. |
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
| View | `JobView` gains `after: After \| None`. `After` holds the predecessor id and its state: a `State`, or `PredecessorGone.MISSING` (no job directory) or `PredecessorGone.INVALID` (the files do not read). `After.satisfied` is true only for `State.DONE`. `blocked_by` keeps resource holders only. `derive` gains `invalid_ids`; its callers are `providers/jobs.py:88` and tests. | `blocked_by` has one meaning. `list` prints `blocked-by=` as holders (`commands/list.py:36-37,69`). An invalid predecessor is not in `records`, so without `invalid_ids` it would read as missing. |
| Leaves `held` | When the predecessor derives `done`. `needs-input`, including done with an unproven item, keeps it held. | The successor's branch base exists only after `done`; a successor never runs after a failure. |
| Locks | A job whose `after` is not satisfied holds nothing, whatever its approval. `satisfied` is computed from the terminal states before `holders`. | A predecessor at `needs-input` waits for the user; a successor on another repository must not stop that repository's queue. |
| `launch` while after-blocked | The `is_launchable` refusal (`providers/jobs.py:95-97`) runs before `_prepare_run`. For a `held` job with an unsatisfied `after` it exits 1 `after <pred> is <state>`. | A `held` job never reaches `_prepare_run`. `providers/jobs.py:144-147` names a held resource with `next()`; it stays correct when `blocked_by` holds only holders. |
| `list --json` | `after` is the predecessor id. `after-state` is its state, `missing` or `invalid`. | The dispatcher's only input. |
| Predecessor failed, missing or abandoned | The CLI derives `held`. `next` gives `close-successor`; the dispatcher closes the successor without asking and sends the origin "closed: predecessor <id> <state>; re-dispatch" (as `skills/goal/job.md:94`). Successors of the closed job follow on the next scan. | A failed job is terminal (`state.py:123-124`). |
| Predecessor invalid | The dispatcher does nothing for the successor. The predecessor's `repair` action already asks the user to repair the predecessor. | Closing would be wrong while the user repairs the file. |
| `base` | For each repository R of the job, `cure:goal` job mode sets `base` to the branch of the nearest job on the `after` chain that changes R. It reads that branch from the job's `goal.md`. The walk starts at the row's `after` in `cure-job list --json`, never the handoff's `after:`. Each step moves to the current job's row `after`. A job changes R when R is in its row's `resources` from its handoff `repos`. A repository added only by `claim` does not count. The walk stops at the first job that changes R. When no job on the chain changes R, `base` comes from the handoff as today. A passed job whose row has `after-state` `missing` or `invalid` stops the walk. `cure:goal` asks the user for the base of each repository not yet resolved. The walk needs a `goal.md` in each job it passes. The dispatcher drafts a successor's goal only after the predecessor's row has `goal` true, so each job on the chain has one. A passed job need not be `done` at draft time. Every passed job is `done` when the successor launches, and the Base check row tests the branch then. | Handoff `branch` may be `current` (`skills/dispatch/defaults.md:12`). A branch exists only in its own repository. The last job of a chain may not change every repository of the successor. A split puts an under-limit repository in the part that needs it, which need not be the last part. |
| Base check | For a base taken from a predecessor, work item 1 compares `<base>` with the local branch, not with `origin/<base>`. When `origin/<base>` exists, it checks `git merge-base --is-ancestor origin/<base> <base>`; a failure is a failure cause. Other bases keep the check of `skills/goal/rules.md:9-11`. | With `delivery: commit`, the default (`skills/dispatch/defaults.md:10`), the predecessor commits locally and nothing pushes. `origin/<base>` lacks its commits, and "base the work on `origin/<base>`" would drop them. |
| Base commit | Work item 1 records `git -C <repo> rev-parse <base>` for each repository as that repository's base commit: in the ledger, or in the transcript for Solo. The diff cap (`skills/goal/job.md:127-128`) and the retrospective's changed lines are measured per repository against it. | With `branch: current` the successor commits on `<base>` itself. A cap against the branch name would count only uncommitted lines. The repositories of one successor can have different bases. |
| Cycles | None possible. `new` needs an existing predecessor and gives a fresh id, so no job can precede itself. `derive` follows `after` one hop. | |
| Prune | `prune` keeps an expired job named by an open job's `after` (`providers/jobs.py:326-334`, `state.py:55-59`). | Otherwise a pruned predecessor closes its successor. |

### `cure-job next --json`

| Item | Decision | Reason |
|---|---|---|
| Output | A JSON array. One element per job that has at least one action: the job's `list --json` row plus `actions`, an ordered list of action names, and `args`, an object keyed by action. A job with no action is absent. | The dispatcher needs one call per wake. The row fields (`session`, `prs`, `origin`) stay available. |
| Home | `actions.py`: `actions(view, row) -> list[Action]`, a pure function of the derived view. `commands/next.py` prints it. `list --json` is unchanged. | Tested without sessions. `list` stays the user's view. |
| Order | Jobs in `lock_rank` order. Within a job, the order of the table below. | The dispatcher works top to bottom. |
| Wake loop | The dispatcher runs `prune`, then `next --json`, and acts on each element. After an action that changes state (`close`, `launch`, `approve`, a `goal.md` write), it runs `next --json` again in the same turn, and stops when an array repeats. | Replaces the rescans of the `release` row. |

Actions, in their order within one job:

| Action | Condition | `args` | Dispatcher procedure |
|---|---|---|---|
| `repair` | Job `invalid`. | the file `list` names | Print the id and the file. Ask the user to repair it or delete the job directory. |
| `report` | `done`, `failed` or `needs-input`, and `reported` false. | none | Send the finish message, then `cure-job reported`. |
| `remove-sessions` | `done` or `abandoned`, and `sessions-removed` false. | none | `cure-job remove-sessions`; on error, show it and continue. |
| `ask-timeout` | `needs-input` and the only question of `result.md` starts with `short-hold timeout:`. | resource, holder id | Ask the user, naming the resource and its holder. Never settle it as `(recommended)`. |
| `ask-input` | `needs-input`, not `ask-timeout`. | none | Read `result.md`. Settle each `question` item as in "Asking"; ask the rest and each `unproven` item. Then "Answer and resume". |
| `confirm-stalled` | `stalled`. | `config.dispatcher.stalled-confirm-seconds` | Run `next --json` again after that many seconds. If the job still has `confirm-stalled`, ask: relaunch or abandon. |
| `ask-relaunch` | `lost`. | none | Ask: relaunch or abandon. |
| `tell-blocked` | `blocked`. | `waiting-for` | Tell the user the id, the session and `waiting-for`; ask them to attach in `claude agents`. |
| `close-successor` | `held`, and `after-state` is `failed`, `abandoned` or `missing`. | predecessor id, its state | `cure-job close --reason "predecessor <id> <state>"`, tell the origin "closed: predecessor <id> <state>; re-dispatch". No question. |
| `draft` | `queued`, or `held` with `goal` false, and no `close-successor`. | none | "Goal and approval": draft through `cure:goal`, run the checks, print the summary, then `approve --by auto` or ask for approval. |
| `ask-approval` | `awaiting-approval`, or `held` with `goal` true and `approved` false, and no `close-successor`. | none | Ask once. Record answers in `goal.md` through `cure:goal`, then `approve` as the last write. |
| `launch` | `approved`. | none | Re-run the checks and the uncommitted-changes question. With no question, `cure-job launch`. A question keeps the job `approved` until the answer. |
| `note-starved` | `held`, `approved` true, and a `blocked-by` id higher than its own. | the higher ids | Print `<id> waits on later <ids>`. Ask nothing. |

No action: `launched`, `running`, `held` approved with only lower-id blockers, `held` with
`after-state` `invalid` (the predecessor's `repair` covers it), and terminal jobs with nothing left
to report or remove.

`agents/dispatcher.md` replaces its States table with a table of these actions and their
procedures. "Goal and approval" step 5 becomes `approve --by auto` when the tier is in
`dispatcher.auto-approve-tiers`, the handoff has no `## Open` item, and every check passed.

A held job's repository is held by a launched job, which edits that tree, or by an `approved` job
about to launch. The uncommitted-changes question therefore runs in `launch`, not in `draft`.

### Risks

| Risk | Impact | Early signal | Owner | Mitigation |
|---|---|---|---|---|
| Another job's in-progress edits enter this job's image build via `EXTERNALSRC`. | The build fails, or verify runs with foreign changes. | The foreign-edits check before each build claim. | The single claimant | Build own recipes where verify allows; name the cause in the retrospective. |
| Bench jobs lose the launch-time bench lock at the part 1 upgrade. | Two jobs on the bench. | `list` shows two running `device: bench` jobs. | The user who upgrades | Upgrade with no `device: bench` job open. The part 1 PR states this. |
| A worker forgets `release`. | The bench is held until the run ends. | A waiter's timeout names the holder. | The dispatcher, short-hold timeout row | Run-scoped claims. |
| A lost session keeps short holds. | Other workers wait. | `list` shows the holder `lost`. | The dispatcher, `lost` row | Deliberate. |
| A wide multi-repo job starves: jobs on any one of its repositories, later ones included, keep launching. | It waits with no bound. | A `held` approved job whose `blocked-by` names a higher id. | The dispatcher, through the `note-starved` action | None built. |
| An `approved` job's launch-time question stays unanswered. | It keeps its repositories. | It stays `approved` across wakes; the question round names the job. | The user | None built. |

## Configuration

| Item | Decision | Reason |
|---|---|---|
| File | `${CURE_JOB_ROOT:-~/.claude/cure}/config.json`. A missing file means every built-in default. | One home next to `jobs/`. |
| Reader | `config.py` in the CLI loads and validates it. Skills and agents run `cure-job config get <key>`, which prints the effective value as JSON. They never parse the file. | One validator, one source of defaults. |
| Validation | An unknown key, a wrong type, a value out of range or an unreadable file is a config error. `cure-job config check` and `cure-job next` exit 1 with `config.json: <key>: <problem>`. Every other command uses the built-in default for each key in error, prints `config.json: <key>: <problem>; using default <value>` on stderr, and runs. | `next` failing stops the dispatcher's wake, and the dispatcher shows the error to the user. A typo never stops a running job's `finish`, `claim` or `release`. |
| `cure-job config get` | No key: the whole effective configuration. A key: that value. An unknown key exits 1. | |
| `cure-job config init` | Writes `config.json` from the built-in defaults and, when `defaults.md` exists, from its rows. Renames `defaults.md` to `defaults.md.bak`. Refuses when `config.json` exists. | One-time move from `defaults.md`. |
| Example | `skills/dispatch/config.example.json` replaces `skills/dispatch/defaults.md`. | |

| Key | Type and range | Default | Reader |
|---|---|---|---|
| `handoff.delivery` | `commit` or `pr` | `commit` | `cure:dispatch`, `cure:goal` |
| `handoff.base` | branch name | `main` | `cure:dispatch`, `cure:goal` |
| `handoff.branch` | branch name or `current` | `current` | `cure:dispatch`, `cure:goal` |
| `handoff.resource-risk` | list of `{"scope": "all" \| "device: <name>" \| "repo: <path>", "text": "<risk>"}` | `[]` | `cure:goal` |
| `dispatcher.auto-approve-tiers` | subset of `Solo`, `Light`, `Full` | `["Solo", "Light"]` | dispatcher |
| `dispatcher.stalled-confirm-seconds` | 10-600 | 60 | `cure-job next` (passed in `args`) |
| `split.limit` | 100-5000 | 800 | `cure:dispatch` |
| `short-hold.wait-seconds` | 10-540 | 540 | worker, per `claim --wait` call |
| `short-hold.wait-total-minutes` | 10-1440 | 120 | worker |
| `prune.done-days` | 1-365 | 14 | `cure-job prune` |
| `prune.failed-days` | 1-365 | 30 | `cure-job prune` |
| `prune.abandoned-days` | 1-365 | 30 | `cure-job prune` |
| `launch-grace-seconds` | 10-600 | 60 | `state.py` |

The 540-second ceiling of `short-hold.wait-seconds` stays fixed: one foreground Bash call is capped
at 600 seconds. `claude.py` `TIMEOUT_SECONDS` and `STOP_TIMEOUT_SECONDS` stay constants; they bound
CLI calls, not behaviour.

## Split in `cure:dispatch`

`cure:dispatch` runs in the working session, which holds the task's context and can ask the user.
The split happens there, before any handoff is written. The dispatcher, `cure:goal` and the CLI see
only plain jobs chained with `after:`.

### Steps

`skills/dispatch/SKILL.md` gains these steps between "Fill the template" and "Write the handoff":

| # | Step |
|---|---|
| 1 | Estimate the change per repository (table Estimate). |
| 2 | No repository above `split.limit`: write one handoff with Settled line "Estimate: ~N changed lines". Done. |
| 3 | Otherwise cut the work into parts by the split rule and write one handoff draft per part. |
| 4 | Ask the user in one `AskUserQuestion`: split as proposed (the question lists each part with slug, repos and estimate), or queue as one job. With `delivery: pr` and no tracker the skill can write to, the same round asks for one ticket per part. |
| 5 | Split: create the tickets, then run `cure-job new` for each part in order, each with `after:` set to the previous part's job id. Send the dispatcher `job <id>` for each part. |
| 6 | Tell the user the part job ids and tickets in one line. |

`allowed-tools` gains `AskUserQuestion`.

### Estimate

| Item | Decision |
|---|---|
| Method | 1. From Work and Done when, list every file each step changes: new, edited, deleted, tests, docs. Read each file to be edited. 2. Per file, estimate added plus deleted lines with a one-phrase basis. 3. Sum per repository. 4. If `~/.claude/retros/` has a similar goal, check the sum against its Measurements row (`skills/goal/SKILL.md:235-236`). |
| Unit | Insertions plus deletions of `git diff --shortstat <base>`, the unit of the goal's cap (`skills/goal/job.md:127-128`). |
| Trigger | `split.limit`, default 800, the lower edge of 800-1000, because the estimate can be 2x low. |
| Goal cap | `cure:goal` reads the "Estimate:" line under Settled and sets `<lines>` to 2 x N rounded up to 100. Without the line, the cap is set as today. The retrospective's "Changed lines against the cap" (`skills/goal/SKILL.md:221`) also reports the estimate. |
| Cannot cut | Tell the user the reason in the split question; the options are queue as one job, or stop. |

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
| `outcome`, `## Work`, `## Done when`, `device` | Per part. `device: bench` only if the part needs the bench. |
| Settled | Applicable lines, plus "Split: part k of n; estimate ~N changed lines". |
| `Resource risk:` lines, `## Tools` | Copied verbatim. |
| `## Open` | Each item goes into the first part it affects. |
| `after:` | Part 1: the `after:` of the unsplit draft, if any. Part k > 1: part k-1's job id. |
| `ticket:` | `delivery: pr`: the part's own ticket. `delivery: commit`: the session's ticket. |
| `branch` | `delivery: pr`: `<ticket>_<slug>` per the repository's branch convention. `delivery: commit`: one branch; the parts stack as commits on it. |
| Slug | `<slug>-part<k>`. It passes `_slug_arg` (`commands/new.py:42-47`). |

### Tickets

| Rule | Decision |
|---|---|
| When | Only with `delivery: pr`, and only after the user chose split. |
| GitHub | The session's ticket is `#N`, `owner/repo#N` or a github.com issue URL, or it has none and `gh repo view --json hasIssuesEnabled` is true for the delivering repo: `gh issue create --title "<outcome of the part>"`. The body names the parent ticket. |
| Other trackers | The split question asks for one ticket id per part. The user creates them. |
| Credentials | The skill never logs in, never reads or stores a token. A failed `gh auth status` is reported, and the user gives the ticket ids instead. |
| Failure | A failed create or `cure-job new` stops the split. The skill tells the user the tickets and jobs already created. Created part jobs wait on their `after:` chain and stay safe to close. |

## Design note

### `capture-idea` removal

`~/.claude/ideas/` files lie outside the repository. Part 8 does not touch them.

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

### Tracker

Decision: see [Tickets](#tickets). GitHub issues are created through `gh`. Every other tracker
gets ticket ids from the user in the split question.

Reason: the user is present in the working session, so no detection chain and no client per tracker
is needed.

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
`resource.py:6`). No second bench is assumed. When a second bench exists, a `devices` key in `config.json` maps each name to its address, and
unknown names are refused.

Reason: there is one bench. An open `device:<name>` grammar turns a typo into a resource that never
conflicts.

## Parts

All parts change claude-plugins only. Each part is one job and one PR. Each part that changes
`plugins/cure/` bumps the plugin version.

Order: parts 1-8. Reasons:

- Part 1 ships one short-hold kind, so no two short holds can nest. Part 2 adds the second kind
  together with the all-or-none claim that prevents the deadlock.
- Part 3 moves the existing dispatcher conditions into `cure-job next`. Parts 4 and 5 then add
  their conditions as actions, not as prompt rows.
- Parts 4 and 5 stack: approval, then `after:`.
- Part 6 moves the defaults and constants into `config.json`. Part 7 reads `split.limit` from it
  and uses `after:` from part 5.
- Part 8 is independent.

Parts 1 and 4 carry a cut line. A 2x low estimate puts each above the 800-line trigger. When
the diff of such a part passes 800 lines during work, the part ends at its cut line and the rest
becomes the next part. The handoff of such a part names the cut line under Settled and sets the
line cap to 800. At the cap the worker delivers the first half with that half's Done when items, and
the second half is queued as the next part.

1. Short holds: `release`, run-scoped claims, `claim --wait` for the bench
   - Issue: #32 (Add cure-job release and run-scoped short holds for the bench)
   - Scope: `release` command and event; `run` field on claims; `claim` precondition, `--wait`, `JobStore.locked()` and holders from the snapshot; `resource.Kind` and `is_short_hold`; `device: bench` no longer a handoff resource; worker "Short holds" protocol with the single claimant; dispatcher row for a short-hold timeout.
   - Files: `cli/src/cure_job/` `resource.py`, `events.py`, `job.py`, `handoff.py`, `store.py`, `providers/jobs.py`, `commands/claim.py`, new `commands/release.py`, `cli.py`; tests `test_events`, `test_jobs`, `test_state`, `test_cli`, `test_handoff` (about 44 bench references); `skills/goal/worker.md`, `skills/goal/job.md`, `skills/dispatch/SKILL.md:26`, `agents/dispatcher.md`; `plugin.json`.
   - Estimate: 525 changed lines in claude-plugins (195 code, 280 tests, 50 docs).
   - Cut line: 1a `release`, the `run` field, run-scoped claims, `resource.Kind` and `is_short_hold`. 1b the `claim` precondition, `--wait`, `JobStore.locked()`, `device: bench` no longer a handoff resource, the worker protocol and the dispatcher row. Done when: 1a items 2, 3, 5, 8; 1b items 1, 4, 6, 7, 8.
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

3. `cure-job next` for the existing states
   - Scope: `actions.py` with the actions `repair`, `report`, `remove-sessions`, `ask-timeout`, `ask-input`, `confirm-stalled`, `ask-relaunch`, `tell-blocked`, and `draft` for `queued`; `commands/next.py`; the dispatcher wake loop on `next --json`; the States table of `agents/dispatcher.md` replaced by the action table.
   - Files: new `actions.py`, new `commands/next.py`, `cli.py`, `result.py` (the short-hold timeout question); tests, new `test_actions`, `test_cli`; `agents/dispatcher.md`, `README.md`; `plugin.json`.
   - Estimate: 430 changed lines in claude-plugins (120 code, 200 tests, 110 docs).
   - Depends on: part 2.
   - Done when:
     1. For each state in the action table, `actions()` returns the listed actions in the listed order (one test per row).
     2. A `done` job with `reported` and `sessions-removed` true is absent from `next --json`.
     3. A `needs-input` job whose only question is `short-hold timeout: device:bench held by <id>` gets `ask-timeout` with the resource and the holder in `args`.
     4. `agents/dispatcher.md` has no States table. Each action of `next` has one procedure row.
     5. `pytest` and `scripts/lint-plugin.py` pass.

4. Approval while held, auto-launch
   - Issue: #34 (Approve a held job and launch it when its resources free)
   - Scope: `approved` event bound to the goal digest; `cure-job approve`; state `approved`; `held` with or without a goal; run-1 launch needs approval; `holders` takes launched jobs and ready unlaunched jobs, all or none; `lock_rank` unchanged; `list --json` fields `goal` and `approved`; `next` actions `draft` for `held` without a goal, `ask-approval`, `launch` and `note-starved`; the uncommitted-changes question moved to `launch`; `approve` as the last write of a round; Solo/Light rule as `approve --by auto`.
   - Files: `events.py`, `job.py`, `store.py`, `goal.py` or a digest helper, `state.py` (the ready predicate; `held[name]` at `:107` becomes `held.get(name)`), `providers/jobs.py` (`held[name]` at `:146` becomes `.get`; `Listing` may carry the holders map `derive` built), new `commands/approve.py`, `cli.py`, `commands/list.py`, `actions.py`; tests (an approving builder helper; about 68 `launch` call sites); `agents/dispatcher.md`, the launch line in `skills/goal/job.md`, `README.md:107`; `plugin.json`.
   - Estimate: 600 changed lines in claude-plugins (185 code, 370 tests, 45 docs).
   - Cut line: 4a the `approved` event, the digest, `cure-job approve` and the `list --json` fields `goal` and `approved`, with no state change. 4b the state `approved`, the run-1 launch refusal, `holders` and the `next` actions. Done when: 4a items 11, 12; 4b items 1-11.
   - Depends on: part 3.
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
     10. `next` gives `draft` for a `held` job without a goal, `ask-approval` for a `held` job with an unapproved goal, `launch` for an `approved` job, and `note-starved` for a `held` approved job blocked by a higher id. `agents/dispatcher.md` names `approve` as the last write of a round.
     11. `pytest` and `scripts/lint-plugin.py` pass.
     12. `approve` writes one `approved` event with the goal digest. The same digest again writes nothing. `list --json` shows `goal` and `approved`.

5. `after:` ordering
   - Issue: #35 (Order stacked jobs with after: in the handoff)
   - Scope: handoff key `after:`; `JobView.after` and `PredecessorGone`; `derive` gains `invalid_ids`; `after` and `after-state` in `list`; launch refusal; the ready test excludes a job whose `after` is not satisfied; prune guard; `base` per repository from the nearest job on the `after` chain that changes the repository, which `cure:goal` walks from the row's `after`, with the local base check and the base commit; `next` action `close-successor`.
   - Files: `handoff.py`, `state.py`, `providers/jobs.py`, `commands/list.py`, `actions.py`; tests; `skills/dispatch/SKILL.md`, `skills/dispatch/template.md`, `skills/goal/job.md`, `skills/goal/SKILL.md`, `skills/goal/rules.md`, `agents/dispatcher.md`; `plugin.json`.
   - Estimate: 380 changed lines in claude-plugins (110 code, 210 tests, 60 docs).
   - Depends on: part 4.
   - Done when:
     1. `new` with an unknown `after` exits 1.
     2. The successor is `held` with an empty `blocked-by` and `after-state` set until the predecessor is `done`. `needs-input` keeps it held.
     3. `launch` of an after-held job exits 1 `after <id> is <state>` from the `is_launchable` refusal (`providers/jobs.py:95-97`), with no traceback.
     4. A failed predecessor gives `after-state: failed`. An invalid predecessor gives `invalid`; a removed one gives `missing`.
     5. `prune` keeps an expired predecessor of an open job.
     6. `skills/goal/rules.md` states the local base check and the base commit for a predecessor's base.
     7. An approved successor on Y, whose predecessor names only X and is `needs-input`, holds nothing. A later approved job on Y lists `approved`.
     8. Jobs P1 on A and B, P2 on A after P1, and P3 on A after P2, then S on B after P3. S takes P1's branch as `base` for B.
     9. `pytest` and `scripts/lint-plugin.py` pass.
     10. A walk that reaches a row with `after-state` `missing` or `invalid` stops there, and `cure:goal` asks for the base of each repository not yet resolved.
     11. `next` gives `close-successor` for an approved successor whose predecessor failed, and no `launch`.

6. `config.json`
   - Scope: `config.py` with the key table, defaults and validation; `cure-job config get`, `check` and `init`; `state.py` and `commands/prune.py` read the prune and grace values; `next` passes `stalled-confirm-seconds`; `cure:dispatch`, `cure:goal`, `skills/goal/worker.md` and `agents/dispatcher.md` read values through `config get` in place of `defaults.md`; `skills/dispatch/config.example.json` replaces `skills/dispatch/defaults.md`.
   - Files: new `config.py`, new `commands/config.py`, `cli.py`, `state.py`, `commands/prune.py`, `actions.py`; tests, new `test_config`; `skills/dispatch/SKILL.md`, `skills/dispatch/defaults.md` (deleted), new `skills/dispatch/config.example.json`, `skills/goal/job.md`, `skills/goal/worker.md`, `agents/dispatcher.md`, `README.md`; `plugin.json`.
   - Estimate: 380 changed lines in claude-plugins (150 code, 160 tests, 70 docs).
   - Depends on: part 5.
   - Done when:
     1. With no `config.json`, `config get` prints every key with its default.
     2. An unknown key, a wrong type and an out-of-range value each make `config check` and `next` exit 1 naming the key. With the same file, `list`, `claim`, `release` and `finish` exit 0 and print the key and the default used on stderr.
     3. `config init` with a `defaults.md` holding `delivery: pr` and one resource-risk row writes both into `config.json` and renames `defaults.md`. A second `config init` exits 1.
     4. `prune.done-days: 1` prunes a `done` job after one day.
     5. `git grep -n "defaults.md" -- plugins/` prints nothing.
     6. `pytest` and `scripts/lint-plugin.py` pass.

7. Split in `cure:dispatch`
   - Scope: the steps, estimate, split rule, part handoffs and tickets of [Split in `cure:dispatch`](#split-in-curedispatch); the "Estimate:" line read by `cure:goal` for the cap.
   - Files: `skills/dispatch/SKILL.md`, `skills/dispatch/template.md`, `skills/goal/job.md`, `README.md`; `plugin.json`.
   - Estimate: 130 changed lines in claude-plugins (all skill and doc).
   - Depends on: part 6.
   - Done when:
     1. `skills/dispatch/SKILL.md` names `split.limit`, the split question with its two options, and `after:` per part.
     2. `allowed-tools` of `skills/dispatch/SKILL.md` includes `AskUserQuestion`.
     3. In a manual session with a temporary `CURE_JOB_ROOT`, `split.limit: 100` and a task estimated above it, choosing split queues n >= 2 jobs. Part k > 1 lists `after` equal to part k-1's id.
     4. `skills/goal/job.md` sets the cap from the "Estimate:" line.
     5. `scripts/lint-plugin.py` passes.

8. Remove `capture-idea`, extend `cure:note`
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
