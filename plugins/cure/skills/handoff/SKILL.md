---
name: handoff
description: Hand a task from the current working session to the dispatcher as a queued job. Fills a handoff file from the session's context, writes it with `cure-job new`, and sends the `dispatcher` session the job id. Use when the user says "hand this off", "queue this as a job", "send this to the dispatcher", or "/cure:handoff".
allowed-tools: Read, Bash, Grep, Glob, SendMessage
---

# Handoff

The session is busy. Ask nothing that the context answers. Do not do the task. Queue it.

## Steps

Plugin root: `${CLAUDE_PLUGIN_ROOT}`. Only this file has the variable expanded. Write its value in place of `<plugin-root>` in every command below.

1. Read `${CLAUDE_PLUGIN_ROOT}/skills/handoff/template.md`.
2. Fill the template from the session's context (table below).
3. Write the handoff with `cure-job new` (below). Keep the printed job id.
4. Send the dispatcher the job id (below).
5. Tell the user the job id and whether the dispatcher was reached or started.

## Fields

| Field | Fill with |
|---|---|
| `repos` | Absolute git toplevels, from `git -C <dir> rev-parse --show-toplevel`. The first is the launch directory. |
| `device` | `bench` when the work needs the hardware bench, else `none`. |
| `outcome` | One sentence. |
| `ticket`, `branch`, `base`, `delivery` | Only when the user stated them. Otherwise omit the key; `defaults.md` supplies it. `delivery` is `commit` or `pr`. |
| `## Settled` | Decisions taken in the session, each with its reason. |
| `## Work` | The steps, in order. |
| `## Done when` | Numbered checks that the job can run and show. |
| `## Tools` | The repository's build, review and verify agents and its PR skill. Take them from its `CLAUDE.md` and `.claude/`. |
| `## Open` | Questions only the user can answer. Omit the section when there are none. |

Omit `id` and `created`. `cure-job new` sets them.

Frontmatter grammar: `key: scalar` on one line, `key: [a, b]` inline lists, and block lists of
`  - item` lines. Nothing else parses. Put no comma in an item of an inline list.

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

Send one cross-session message with `SendMessage` to the session named `dispatcher`. The text is
`job <id>` and nothing else.

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
