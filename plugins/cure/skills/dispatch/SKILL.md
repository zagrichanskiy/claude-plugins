---
name: dispatch
description: Hand a task from the current working session to the dispatcher as a queued job. Fills a handoff file from the session's context, writes it with `cure-job new`, and sends the `dispatcher` session the job id. Use when the user says "hand this off", "queue this as a job", "send this to the dispatcher", "dispatch this", or "/cure:dispatch".
allowed-tools: Read, Bash, Grep, Glob, SendMessage, AskUserQuestion
---

# Dispatch

The session is busy. Ask nothing that the context answers. Do not do the task. Queue it.

## Steps

Plugin root: `${CLAUDE_PLUGIN_ROOT}`. Only this file has the variable expanded. Write its value in place of `<plugin-root>` in every command below.

1. Read `${CLAUDE_PLUGIN_ROOT}/skills/dispatch/template.md`.
2. Fill the template from the session's context (table below).
3. Estimate and split (section "Estimate and split"). It yields drafts and the user's choice: one handoff, or one per part.
4. Create the tickets of a split (section "Estimate and split"). Write each handoff with `cure-job new` (below), the parts in order. Keep the printed job id.
5. Send the dispatcher each job id (below).
6. Tell the user the job ids, the tickets of a split, and whether the dispatcher was reached or started.

## Fields

| Field | Fill with |
|---|---|
| `repos` | Absolute git toplevels, from `git -C <dir> rev-parse --show-toplevel`. The first is the launch directory: the repository the change is made in, also when the session runs in another repository. When the change edits several repositories, the first is the one the job delivers to, by its branch or PR. |
| `device` | `bench` when the work needs the hardware bench, else `none`. It declares the use. The job claims the bench for each step at run time; the handoff does not hold it from launch. |
| `outcome` | One sentence. |
| `ticket`, `branch` | A small change: the session's current work branch and its ticket. Other work: only when the user stated them. Other work with no stated branch: omit the key; `handoff.branch` (default `new`) gives the job its own branch. A job with `after` and no `branch` inherits the predecessor's branch. |
| `base`, `delivery` | Only when the user stated them, or, for `base`, when the job is stacked on a predecessor's branch without `after` (see `after`). Otherwise omit the key; the configuration supplies it. `delivery` is `commit` or `pr`. |
| `after` | Only when this job builds on the result of an open job of the same stack (any state other than `done`, `failed` or `abandoned`): that job's id, one only. Otherwise omit the key. A job stacked only because it edits the same files gets no `after`. Its `base` is the predecessor's branch. The repository resource runs the jobs in order, and a failed predecessor does not close it. `cure-job new` refuses an id with no job. The successor stays `held` until the predecessor is `done`. |
| `## Settled` | Decisions taken in the session, each with its reason. |
| Resource risk | One Settled line per resource the user rated in the session, in the user's words, for example "Resource risk: bench is a test stand; any action on it is approved". Omit when the user said nothing. |
| `## Work` | The steps, in order. No review-round cap: the goal skill's tier rule sets it. |
| `## Done when` | Numbered checks that the job can run and show. |
| `## Tools` | The repository's build, implement, review and verify agents and its PR skill. Take them from its `CLAUDE.md` and `.claude/`. Implement names an agent, never only "implementer". |
| `## Open` | Questions only the user can answer. Omit the section when there are none. |

A small change does not affect customers: a fix, a small refactoring, a doc edit.

The configuration file is `${CURE_JOB_ROOT:-~/.claude/cure}/config.json`. A missing file means the
built-in defaults. Read a value with `<plugin-root>/bin/cure-job config get <key>`; it prints JSON.
Never read the file. `${CLAUDE_PLUGIN_ROOT}/skills/dispatch/config.example.json` is an example of it.

| Key | Used for |
|---|---|
| `handoff.delivery` | `delivery`, when the user did not state it. |
| `handoff.base` | `base`, when the user did not state it. |
| `handoff.branch` | Values: `new` (default), `current`, or a literal branch name. Not applied by dispatch: it omits `branch` unless the `ticket`, `branch` rule above sets it. `cure:goal` applies it when the handoff omits `branch` (see `skills/goal/job.md` Input). |

| `split.limit` | Changed lines per repository above which the task is split (default 800). |

Omit `id` and `created`. `cure-job new` sets them.

Frontmatter grammar: `key: scalar` on one line, `key: [a, b]` inline lists, and block lists of
`  - item` lines. Nothing else parses. Put no comma in an item of an inline list.

## Estimate and split

Runs after the template is filled and before any handoff is written. It ends with the drafts and the user's choice. The main list writes the handoffs and reports.

The effective `delivery` is the stated value, else the output of `cure-job config get handoff.delivery`. The rules below use it.

| # | Step |
|---|---|
| 1 | Estimate the change per repository (below). |
| 2 | No repository above `split.limit`: add the Settled line "Estimate: ~N changed lines" (N is the largest repository sum) and write one handoff. Done. |
| 3 | Otherwise cut the work into parts by the split rule and draft one handoff per part. |
| 4 | With the effective `delivery: pr` on GitHub, run `gh auth status` and `gh repo view <owner/repo> --json hasIssuesEnabled` first (see Tickets). Then ask in one `AskUserQuestion`. The question lists each part with slug, repos and estimate. Options: split as proposed, or queue as one job. With `delivery: pr` and no tracker the skill can write to, the same round asks for one ticket id per part. When the work cannot be cut, the question gives the reason and offers queue as one job, or stop. |
| 5 | Keep the drafts and the answer. Write nothing yet. |

Estimate:

1. From Work and Done when, list every file each step changes: new, edited, deleted, tests, docs. Read each file to be edited.
2. Per file, estimate added plus deleted lines with a one-phrase basis. Estimate tests apart from code by the rule in the goal skill, section "Sizing a goal".
3. Sum per repository. The unit is insertions plus deletions of `git diff --shortstat <base>`.
4. Run `grep '| <repo> |' ~/.claude/retros/stats.md`. If a row is a similar goal, check the sum against its `lines`.

Split rule:

1. Cut only the repository over `split.limit`.
2. Order by layer: types and interfaces, implementation, callers and wiring, removal of what was replaced, docs.
3. Use the fewest parts, each at or below `split.limit`.
4. Tests go with the code they test.
5. No part leaves a caller of something that does not exist yet. Each part builds and passes its tests alone.
6. A repository under the limit stays whole and goes with the part that needs it. That part lists both repos, the delivering repo first.
7. With two repositories over the limit, the provider repository parts come first.
8. The parts form one linear chain.

Part handoffs:

| Field | Value |
|---|---|
| `outcome`, `## Work`, `## Done when`, `device` | Per part. `device: bench` only if the part needs the bench. |
| `## Settled` | The applicable lines, plus "Estimate: ~N changed lines" (N is the part's largest repository sum) and "Split: part k of n". |
| `Resource risk:` lines, `## Tools` | Copied verbatim. |
| `## Open` | Each item goes into the first part it affects. |
| `after` | Part 1: the `after` of the unsplit draft, if any. Part k > 1: the job id of part k-1, printed by `cure-job new`. |
| `ticket` | `delivery: pr`: the part own ticket. `delivery: commit`: the session ticket. |
| `branch` | `delivery: pr`: `<ticket>_<slug>`, or `<slug>` without a ticket. `delivery: commit`: one branch, the same explicit `branch:` value in every part; the parts stack as commits on it. |
| Slug | `<slug>-part<k>`. |

Part spec rules. Each part's handoff and ticket body, including any list of events or scope items in the ticket body, follow them:

1. List only the items this part owns. Mark each item an earlier part delivers as "delivered by part j" and do not list it as work. The marked items go in a separate list, not under work.
2. For each config key the spec cites, say whether it exists at the base of this part. A key that a later part adds is marked "not yet".
3. Name each line a downstream reader parses, with its exact form: the file, the line text and the parser.
4. A part that creates a file format includes the format's frontmatter block in the spec.
5. A state whose action a later part adds gets an interim procedure in this part: what the user or dispatcher does meanwhile.
6. A "no references" check excludes migration code. Name the paths it excludes.
7. Name fields as they are in the file: handoff `repos`, not the row field `resources`.

Writing a split: queue as one job writes the unsplit handoff with the Estimate line. Split creates the tickets, then runs `cure-job new` for each part in order, each with `after` set as in the table above.

Tickets, only with the effective `delivery: pr` and only after the user chose split. `<owner/repo>` comes from an `owner/repo#N` or URL ticket, else from the remote of the delivering repository. Pass it as `--repo` to every `gh` command:

| Case | Action |
|---|---|
| The session ticket is `#N`, `owner/repo#N` or a github.com issue URL, or there is none and `gh repo view <owner/repo> --json hasIssuesEnabled` is true for the delivering repository | `gh issue create --repo <owner/repo> --title "<outcome of the part>"`. The body names the parent ticket. |
| Another tracker | The split question asks for one ticket id per part. The user creates them. |
| `gh auth status` fails | Run before the question. Report it. The question asks for the ticket ids; the user gives the ticket ids. The skill never logs in and never reads or stores a token. |
| A create or `cure-job new` fails | Stop. Tell the user the ids of the tickets and jobs already created. Part 1 is queued and the dispatcher may launch it on its next wake or at once. Parts after part 1 wait on their `after:` chain. The user closes the created jobs with `cure-job close <id>`; for a running job, `cure-job stop <id>` first. |

## Writing the handoff

Run `<plugin-root>/bin/cure-job new --slug SLUG [FILE]`. It queues the handoff and prints the
job id. `FILE` is the handoff file; `-` or no `FILE` reads standard input. `--slug` is a short task
label in `[a-z0-9-]`.

```sh
<plugin-root>/bin/cure-job new --slug fps-clamp - <<'HANDOFF'
---
repos:
  - /home/user/src/video-core
device: none
outcome: Clamp the frame rate to the sensor maximum.
---

## Settled
...
HANDOFF
```

Write the handoff only through this command. Never create files under the state root yourself. When
the command fails, show its error to the user and stop. Do not retry with a changed slug.

## Waking the dispatcher

Send one cross-session message per job with `SendMessage` to the session named `dispatcher`. The text is
`job <id>` and nothing else. A split sends one message per part, in order.

The dispatcher takes the sender address from the message and records it as the job's origin. The handoff carries no `origin`.

When `SendMessage` succeeds, do nothing more. Do not start a dispatcher.

A message does not reach a stopped session. When `SendMessage` fails:

1. Run `claude agents --json`. If an entry named `dispatcher` is live (it has a `pid`), start nothing. Tell the user the message failed and the job is queued.
2. Otherwise start the dispatcher in the working directory of this session:

```sh
claude --bg --name dispatcher --agent cure:dispatcher --settings '{"crossSessionInbound":"accept","autoCompactWindow":200000}'
```

3. Send `job <id>` again with `SendMessage`, so the dispatcher records the origin. If this send fails, tell the user the job will not report back.

Tell the user in one line: job queued, dispatcher started, pin it with ctrl+t in the agents view.
