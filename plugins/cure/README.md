# cure

Design and architecture advisors, review agents, and a job loop (`cure-job`) that runs implementation jobs through a dispatcher.

## Configuration

Config file: `${CURE_JOB_CONFIG:-${XDG_CONFIG_HOME:-~/.config}/cure/config.json}`. One file serves all jobs. Without it, every key has its built-in default.

Question policies: `${XDG_CONFIG_HOME:-~/.config}/cure/question-policies.md`, beside `config.json`. The dispatcher reads it before each question round and appends a policy when the user calls a question not needed. The CLI does not read it.

- The defaults live only in the key table of `config.py`.
- `skills/dispatch/config.example.json` is generated from that table, holds the defaults, is never read at runtime, and lists every key nested by group (`handoff`, `dispatcher`, `split`, `reviews`, `short-hold`, `prune`, `band`, `dashboard`, `worktree`, `slots`; `launch-grace-seconds` is top-level).
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
- `jira-url` in the `band` group is the error `config.json: band: "jira-url" is removed; write it as "tracker-url": "<jira-url>/browse/<key>"`. The dispatcher's rewrite writes that `band.tracker-url`.
- The dispatcher rewrites a file with only these problems to the nested layout.
- `config init` drops a `base` row of `defaults.md` with the note `defaults.md: handoff: "base" is removed; row dropped; ...`.

Branch and base:

- A job without `after` takes the handoff's `base`, else under `current` the branch checked out in the user's checkout of each repository, else each repository's default branch (`origin/HEAD`, fallback `gh repo view --json defaultBranchRef -q .defaultBranchRef.name`).
- `handoff.branch` applies when a handoff omits `branch`. Default `new`: the job gets its own branch from the job's base, named `<ticket>_<slug>` (`issue-<N>` for a GitHub ticket `#N`), or `<slug>` without a ticket, the same in every repository.
- A job with `after` and no `branch` inherits the predecessor's branch, unless its handoff Settled has `Stacked on <id>: overlapping files`; that job gets its own branch by `handoff.branch`.
- `current` gives the job its own branch as `new` does, from the job's base. Any other value is a literal branch name.

Worktrees: every job runs in its own git worktrees, so jobs on one repository run in parallel and the user's checkout is never edited. A job claims no repository. `worktree.root` (default `~/work/yocto/worktrees`, `~` expanded) holds one worktree per repository of the handoff at `<worktree.root>/<repo name>/<job id>`. `<repo name>` is the basename of the repository's git toplevel.

`cure-job launch` creates each missing worktree detached at the repository's HEAD, or for a job with `after` at the HEAD of the predecessor's worktree of that repository where it exists. It records `worktree.root` at the first launch and uses that root afterwards. The session starts in the worktree directory of the first repository. The run session creates or switches the job's branch. A relaunch and `resume` reuse the worktrees. `finish` keeps them. `cure-job prune` removes a pruned job's worktrees with `git worktree remove` and keeps its branches.

Slots: a job whose first repository is inside a `repo` tool workspace runs in a workspace slot instead of worktrees. The workspace is the nearest ancestor of that repository that holds `.repo/`. In a Yocto workspace the build reads the workspace's `sources/` through `EXTERNALSRC`, so a worktree does not separate one job's build from another's. A slot is a full copy of the workspace with its own `sources/` and build directories.

- `slots.root` (default `~/work/yocto/slots`, `~` expanded) holds the slots; slot `N` is `<slots.root>/<N>`.
- `slots.count` (default 5, 1 to 20) is the number of slots. Each slot has its own build directory, so `slots.count` also caps the parallel bitbake builds of jobs on the machine.
- The first use of a slot creates it with `repo init` from the workspace's manifest URL, manifest file and branch, with `--reference` to the workspace, then `repo sync -c`. It first checks the free disk space under `slots.root` and refuses with the free and needed sizes. It copies the `conf/` of each build directory with paths under the workspace root rewritten to the slot, so downloads and sstate stay shared. It links to the workspace's `CLAUDE.md`, `.claude/`, `sources/CLAUDE.md` and `sources/CLAUDE.local.md`, and copies `.repo/local_manifests/`.
- `cure-job launch` takes the lowest numbered free slot as the resource `slot:<path>`. A reused slot discards the uncommitted changes and untracked files of every project (`git reset --hard`, `git clean -fd`), returns it to its manifest revision, deletes each local branch whose tip is the same branch on the project's remote or an ancestor of it, and runs `repo sync -c`. Local-only branches and branches ahead of or diverged from the remote stay with their commits. For an `after` job, launch then copies every local branch of the predecessor's slot into the job's slot, in each project of the job's repositories. Launch then checks out the handoff's branch in each repository; an `after` job's branch starts from the predecessor's branch in the predecessor's slot. Without a handoff branch the run session creates it. The session starts in the slot copy of the first repository.
- With no free slot, `launch` exits 1 with `error: no free slot: ...` and the job stays unlaunched. The dispatcher launches it again when a job in a slot becomes `done`, `failed` or `abandoned`.
- A job holds its slot until it is `done`, `failed` or `abandoned`. A `needs-input` job keeps it, and `resume` runs in it. A released slot keeps its build directory for the next job.

The main workspace is the `repo` tool workspace outside `slots.root`. No job takes it. An interactive session runs `cure-job main-claim <session id>` before its first write there: an Edit or Write, a `git` command that writes, a `repo` command, or `bitbake`. Reads need no claim: the `git` subcommands that only read, `git fetch` without a refspec that names a destination (`main:main`), `git remote` with `-v`, `get-url` or `show`, `git tag` alone or with `-l` or other list options, `git worktree list`, and `repo status`, `info`, `list`, `manifest`, `diff` and `branches`. A target under `slots.root` or `worktree.root` is never in the main workspace, even when that root lies inside it. One session holds the claim `main` at a time; `main-claim` exits 1 naming the holder and `cure-job main-release <holder>`, which releases the claim of a holder that no longer runs. A `PreToolUse` hook denies a write under the main workspace from a session that does not hold `main`, and its reason gives the `main-claim` command and, while another session holds `main`, that `main-release` command. A `SessionEnd` hook runs `cure-job main-release <session id>`.

## Job band

The hooks module `hooks/register.tsx` draws a band above the prompt. It reads `cure-job list --json` on each draw and calls no tracker.

| Session | Band |
|---|---|
| Job session (`CURE_JOB_ID` set by `cure-job launch` and `resume`) | The job's ticket as a link, its summary, its PR links, its branch and the session's working directory. No buttons. |
| Dispatcher (main agent `cure:dispatcher`) | One entry per `awaiting-approval` job: the ticket link, summary, PR links, the handoff branch and the workspace, with Approve (`cure-job approve <id> --by user`) and Reject (`cure-job close <id>`). Nothing when no job awaits approval. |
| Any other session | Nothing. |

Ticket links:

- A tracker key (`ABC-12`, a Jira key or a ClickUp custom id) links to `band.tracker-url` with `<key>` replaced by the key. `band.tracker-url` defaults to `https://ienso-team.atlassian.net/browse/<key>`; for ClickUp it is `https://app.clickup.com/t/<workspace-id>/<key>`.
- `owner/repo#N` links to that GitHub issue. `#N` links to an issue of the workspace's GitHub `origin`, else shows as text.
- An http(s) URL links to itself.

A job session without a handoff `branch` shows `git branch --show-current` of its working directory.

## Work dashboard

The same module opens a pane titled Work in an interactive session that is neither a job session nor the dispatcher. It shows the user's open tracker tasks, their open GitHub pull requests and the cure jobs. The data is fetched once at session start and then every `dashboard.refresh-seconds`, without a model call. The pane is placed at once from 144 terminal columns; narrower, it waits until the terminal widens. Closing the pane stops the refresh; `/cure-work` reopens it and restarts the refresh, and in a job session or the dispatcher it answers that the pane is not available there.

| Source | Fetched with |
|---|---|
| Pull requests | One `gh api graphql` search for open PRs authored by `@me` and one for those whose review is requested from `@me`, narrowed to the `dashboard.github-owners` entries when the list is set; each returns the head branch, review decision and last commit's check state |
| Jobs | `cure-job list --json`, narrowed to `dashboard.job-states` and, under `dashboard.job-scope` `workspace`, to the jobs whose `workspace` is the session's project root (where it started, or where `/cd`, a host directory change or a worktree move took it; a shell `cd` does not move it) |
| Tasks, `split.tracker` `github` | `gh search issues --assignee @me --state open`, once per `dashboard.github-owners` entry with `--owner`, once without when the list is empty |
| Tasks, any other `split.tracker` | One call of the MCP tool `dashboard.tasks-mcp-tool` on server `dashboard.tasks-mcp-server` with `dashboard.tasks-mcp-args`; the list at `dashboard.tasks-field-items` in its reply gives one task per item. While the server, the tool or `dashboard.tasks-field-key` is empty, the pane says tasks are unavailable |

Each task is one group with the PRs and jobs that belong to it. A PR belongs to a task by its head branch: `ABC-12_…` to the tracker key `ABC-12`, `issue-5-…` or `issue-5_…` to issue 5 of the PR's repository. A job belongs to a task by its `ticket`: a tracker key, an issue reference, or a URL equal to the task's `dashboard.tasks-field-url` value. A PR or job that matches no task is listed under Unlinked.

A source whose refresh fails keeps its last data and the pane shows how old the data is and the error. When a PR search returns some PRs together with an error, the pane shows those PRs and the line `PRs incomplete: <reason>`. A source with no data yet shows why it is unavailable; PRs and jobs still show without tasks.

| Key | Default | Value |
|---|---|---|
| `dashboard.refresh-seconds` | `120` | Seconds between refreshes, 30 to 3600; read at session start and by `/cure-work` |
| `dashboard.github-owners` | `[]` | GitHub owners whose issues count as tasks and whose PRs are shown; empty means every owner |
| `dashboard.tasks-mcp-server` | `""` | MCP server whose tool lists the tasks when `split.tracker` is not `github`, named as `/mcp` lists it |
| `dashboard.tasks-mcp-tool` | `""` | Name of that tool |
| `dashboard.tasks-mcp-args` | `{}` | JSON object passed to the tool as its arguments |
| `dashboard.tasks-field-items` | `""` | Dotted path to the task list in the tool's reply; empty means the reply is the list |
| `dashboard.tasks-field-key` | `""` | Dotted path, within one item, to the task key; an item without a key is skipped |
| `dashboard.tasks-field-title` | `""` | Dotted path to the task title; empty shows no title |
| `dashboard.tasks-field-status` | `""` | Dotted path to the task status; empty shows no status |
| `dashboard.tasks-field-url` | `""` | Dotted path to the task URL, by which a job whose `ticket` is that URL joins the task |
| `dashboard.job-states` | `["launched", "running", "blocked", "stalled", "lost", "needs-input", "failed"]` | Job states the pane lists, each a state `cure-job list` reports (`invalid` included) |
| `dashboard.job-scope` | `"workspace"` | `workspace` lists the jobs started in the session's project root; `all` lists every job |
