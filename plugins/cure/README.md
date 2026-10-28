# cure

Design and architecture advisors, review agents, and a job loop (`cure-job`) that runs implementation jobs through a dispatcher.

## Configuration

Config file: `${CURE_JOB_CONFIG:-${XDG_CONFIG_HOME:-~/.config}/cure/config.json}`. One file serves all jobs. Without it, every key has its built-in default.

Question policies: `${XDG_CONFIG_HOME:-~/.config}/cure/question-policies.md`, beside `config.json`. The dispatcher reads it before each question round and appends a policy when the user calls a question not needed. The CLI does not read it.

- The defaults live only in the key table of `config.py`.
- `skills/dispatch/config.example.json` is generated from that table, holds the defaults, is never read at runtime, and lists every key nested by group (`handoff`, `dispatcher`, `split`, `reviews`, `short-hold`, `prune`; `launch-grace-seconds` is top-level).
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
- `base` in the `handoff` group is the error `config.json: handoff: "base" is removed; a job's base is the base stated in the handoff, else the repository's default branch`.
- The dispatcher rewrites a file with only these problems to the nested layout.
- `config init` drops a `base` row of `defaults.md` with the note `defaults.md: handoff: "base" is removed; row dropped; ...`.

Branch and base:

- A job without `after` takes the handoff's `base`, else each repository's default branch (`origin/HEAD`, fallback `gh repo view --json defaultBranchRef -q .defaultBranchRef.name`).
- `handoff.branch` applies when a handoff omits `branch`. Default `new`: the job gets its own branch from the job's base, named `<ticket>_<slug>` (`issue-<N>` for a GitHub ticket `#N`), or `<slug>` without a ticket, the same in every repository.
- A job with `after` and no `branch` inherits the predecessor's branch.
- `current` uses the launch repository's checked-out branch. Any other value is a literal branch name.
