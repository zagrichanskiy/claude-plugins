# cure

Design and architecture advisors, review agents, and a job loop (`cure-job`) that runs implementation jobs through a dispatcher.

## Configuration

Config file: `${CURE_JOB_CONFIG:-${XDG_CONFIG_HOME:-~/.config}/cure/config.json}`. One file serves all jobs. Without it, every key has its built-in default.

Question policies: `${XDG_CONFIG_HOME:-~/.config}/cure/question-policies.md`, beside `config.json`. The dispatcher reads it before each question round and appends a policy when the user calls a question not needed. The CLI does not read it.

- The defaults live only in the key table of `config.py`.
- `skills/dispatch/config.example.json` is generated from that table, holds the defaults, is never read at runtime, and lists every key nested by group (`handoff`, `dispatcher`, `split`, `reviews`, `short-hold`, `prune`, `worktree`, `slots`; `launch-grace-seconds` is top-level).
- Lookup names stay dotted: `cure-job config get handoff.delivery`.

| Command | Effect |
|---|---|
| `cure-job config get [<key>]` | Prints the effective value as JSON (the nested object without a key). |
| `cure-job config check` | Validates the file; exit 1 with `config.json: <key>: <problem>`. |
| `cure-job config init` | Writes `config.json` from the defaults and from an old `defaults.md` in the same directory, renamed to `defaults.md.bak`. First moves an old `${CURE_JOB_ROOT:-~/.claude/cure}/config.json` to the new path when the new path does not exist. Refuses when `config.json` exists. |

After updating cure, run `cure-job config init` once.

Safe mode: a config error puts `cure-job` in safe mode. A config error is a bad value, an unknown key, a removed key, an unparsable file, or a `config.json` at the old location `${CURE_JOB_ROOT:-~/.claude/cure}/config.json` while the new path is missing (`config.json found at the old location <path>; run cure-job config init`).

| Command | In safe mode |
|---|---|
| `config check` | Exits 1. |
| `next` | Exits 0 and appends a `config-error` element. |
| `prune` | Removes no job and exits 1 (`config.json: <key>: <problem>; no job removed`). |
| `approve --by auto` | Exits 1. |

A bad key takes its default; an unparsable file gives all defaults. An unknown key's message ends with `unknown to cure <version>; restart the dispatcher after an update`.

Old layouts:

- A flat dotted key is the error `config.json: handoff.delivery: flat key; write it as {"handoff": {"delivery": ...}}`.
- `base` in the `handoff` group is the error `config.json: handoff: "base" is removed; a job's base is the base stated in the handoff, else resolved by cure:goal`.
- The dispatcher rewrites a file with only these problems to the nested layout.
- `config init` drops a `base` row of `defaults.md` with the note `defaults.md: handoff: "base" is removed; row dropped; ...`.

Branch and base:

- A job without `after` takes the handoff's `base`, else under `current` the branch checked out in the user's checkout of each repository, else each repository's default branch (`origin/HEAD`, fallback `gh repo view --json defaultBranchRef -q .defaultBranchRef.name`).
- `handoff.branch` applies when a handoff omits `branch`. Default `new`: the job gets its own branch from the job's base, named `<ticket>_<slug>` (`issue-<N>` for a GitHub ticket `#N`), or `<slug>` without a ticket, the same in every repository.
- A job with `after` and no `branch` inherits the predecessor's branch, unless its handoff Settled has `Stacked on <id>: overlapping files`; that job gets its own branch by `handoff.branch`.
- `current` gives the job its own branch as `new` does, from the job's base. Any other value is a literal branch name.

Worktrees: every job runs in its own git worktrees, so jobs on one repository run in parallel and the user's checkout is never edited. A job claims no repository. `worktree.root` (default `~/dev/worktrees`, `~` expanded) holds one worktree per repository of the handoff at `<worktree.root>/<repo name>/<job id>`. `<repo name>` is the basename of the repository's git toplevel.

`cure-job launch` creates each missing worktree detached. A job with `after` starts at the HEAD of the predecessor's worktree of that repository where it exists. For a new worktree without a predecessor worktree, launch fetches the branch checked out in the user's checkout and starts at `origin/<branch>` when the fetch succeeds and the local branch is behind or equal to it. Otherwise it starts at the local HEAD and prints one stderr line with the reason: the fetch failed or timed out, HEAD is detached, origin lacks the branch, or the local branch has commits not on origin. It records `worktree.root` at the first launch and uses that root afterwards. The session starts in the worktree directory of the first repository. The run session creates or switches the job's branch. A relaunch and `resume` reuse the worktrees. `finish` keeps them. `cure-job prune` removes a pruned job's worktrees with `git worktree remove` and keeps its branches. A worktree git refuses to remove, for example one with modified files, stays on disk for the user; `prune` reports it once on stderr and removes the job.

Slots: a job whose first repository is inside a `repo` tool workspace runs in a workspace slot instead of worktrees. The workspace is the nearest ancestor of that repository that holds `.repo/`. In a Yocto workspace the build reads the workspace's `sources/` through `EXTERNALSRC`, so a worktree does not separate one job's build from another's. A slot is a full copy of the workspace with its own `sources/` and build directories.

- `slots.root` (default `~/work/slots`, `~` expanded) holds the slots; slot `N` is `<slots.root>/<N>`.
- `slots.count` (default 5, 1 to 20) is the number of slots. Each slot has its own build directory, so `slots.count` also caps the parallel bitbake builds of jobs on the machine.
- The first use of a slot creates it with `repo init` from the workspace's manifest URL, manifest file and branch, with `--reference` to the workspace, then `repo sync -c`. It first checks the free disk space under `slots.root` and refuses with the free and needed sizes. It copies the `conf/` of each build directory with paths under the workspace root rewritten to the slot, so downloads and sstate stay shared. It links to the workspace's `CLAUDE.md`, `.claude/`, `sources/CLAUDE.md` and `sources/CLAUDE.local.md`, and copies `.repo/local_manifests/`.
- `cure-job launch` takes the lowest numbered free slot as the resource `slot:<path>`. A reused slot first stops the sessions of the jobs that held it before and waits until they are down. It then discards the uncommitted changes and untracked files of every project (`git reset --hard`, `git clean -fd`), returns it to its manifest revision, deletes each local branch whose tip is the same branch on the project's remote or an ancestor of it, and runs `repo sync -c`. Local-only branches and branches ahead of or diverged from the remote stay with their commits. A reused slot made from another workspace gets the `conf/` copies and links of the launch workspace, as a new slot does. For an `after` job, launch then copies every local branch of the predecessor's slot into the job's slot, in each project of the job's repositories. A branch of the job's slot that has the name of the predecessor's branch and is not contained in it is first renamed `<branch>-backup-<short sha>`. Launch then checks out the handoff's branch in each repository; an `after` job's branch starts from the predecessor's branch in the predecessor's slot, else on a remote, else at the manifest revision. Without a handoff branch the run session creates it. The session starts in the slot copy of the first repository.
- With no free slot, `launch` exits 1 with `error: no free slot: ...` and the job stays unlaunched. The dispatcher launches it again when a job in a slot becomes `done`, `failed` or `abandoned`.
- A job holds its slot until it is `done`, `failed` or `abandoned`. A `needs-input` job keeps it, and `resume` runs in it. A released slot keeps its build directory for the next job.

The main workspace is the `repo` tool workspace outside `slots.root`. Interactive sessions work there. No job takes it, and nothing guards it.

## Job ledger

`cure-job finish` appends one job record to `ledger.jsonl` in the job directory, one JSON object per line, after it writes `result.md`. A job that runs again finishes again, and each record holds the totals of every run so far, so the last record of a job holds the job's totals. Only `cure-job` writes a ledger, and nothing truncates or rotates one. When `cure-job prune` removes a job, it first appends the job's ledger to `${CURE_JOB_ROOT:-~/.claude/cure}/ledgers/<id>.jsonl`, unless that file already ends with it.

| Field | Value |
|---|---|
| `job`, `date`, `repo`, `slug` | The job id, the time of `finish`, the basename of the first repository, the slug of the id |
| `tier`, `outcome` | The goal's Rules tier and the `finish` status |
| `est_lines` | N of the handoff's Settled line `Estimate: ~N changed lines` |
| `lines` | For the first handoff repository in each git toplevel, the insertions plus deletions of the job's commits since the commit its worktree or slot checkout started at; `null` when no start commit is recorded |
| `turns` | The orchestrator's assistant messages |
| `orchestrator_tokens`, `subagent_tokens` | `input`, `output`, `cache_creation` and `cache_read` tokens, summed over the job's session transcripts and, separately, over their subagent transcripts |

The transcripts are found by the session id `claude agents` lists for each session of the job, under `${CURE_JOB_PROJECTS:-~/.claude/projects}`. A message streamed over several transcript lines counts once, and a sidechain line is skipped. A value that `finish` cannot read is `null`, never 0.

`cure-job stats` reads the last record of each job from the current and the kept ledgers. It prints one line per repository and tier with the job count and the median of each token type, of turns and of changed lines. A job's tokens of one type are its orchestrator's and its subagents' tokens added, and its changed lines are the sum over its repositories. A `null` value is left out of a median, and a column with no value prints `-`, as does a missing tier. `--repo <repo>` prints only that repository.
