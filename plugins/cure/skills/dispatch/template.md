---
repos:
  - /absolute/path/to/git/toplevel
device: none
outcome: One sentence naming the result the job delivers.
ticket: ABC-123
branch: feature/name
base: main
delivery: commit
after: <job id of the predecessor; omit when the job has none; part k of a split: part k-1>
---

## Settled

- Decision taken in the session, with the reason in one clause.
- Resource risk: <resource>: <the user's words>. Omit when the user said nothing.
- Branch: <why this branch>. Omit for other work.
- Estimate: ~N changed lines. A split part also has "Split: part k of n".

## Work

1. First step of the work, in the order it runs.

## Done when

1. A check the job can run and show the output of.

## Tools

- Build: the repository's build agent or command.
- Implement: the agent that writes the change.
- Review: the repository's review agent.
- Verify: the repository's verify agent or command.
- PR: the repository's pull request skill.

## Open

- A question only the user can answer, with the options and the consequence of each.
