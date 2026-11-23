# Sizing a goal and the retrospective

## Sizing a goal

Bound a goal by deliverables: one reviewable concern, one PR, and a done-when list the user can
re-run. The changed-line cap in the failure exit is a stop signal, not the scope. A goal that reaches
it takes the failure exit instead of growing.

- Count changed lines as the failure exit states: `git diff --shortstat <base commit>` (work item 1's
  record) plus the lines of untracked files. Do not use `git add -N`; its entries break `git stash`
  and `git rebase`.
- When Settled has an estimate, record the cap in Settled at draft time: read
  `<plugin-root>/bin/cure-job config get split.limit` and write "Split cap: <limit> changed lines".
  The size check reads the cap from there.
- Estimate tests apart from code. Tests of a state-machine change are estimated at 2x its code.
  Validator tests are estimated per key. A legacy parser is estimated separately.
- The test-author brief states a line budget, the test estimate, beside the list of behaviours to
  cover.
- A goal with a test-author step has a work item between the implementer item and the test-author
  item. It measures the diff as the failure exit states and prints the count.
- The cut line divides a change into a delivered part and a rest. The goal writer plans it, or the
  session that writes the follow-up goal after a failure exit at the cap applies it. Under
  `delivery: pr`, it rewords the ticket to the delivered part and opens a new ticket for the rest.
  With no usable tracker it applies no cut. Each ticket has one PR per repository, and the PR does
  not reference the split.
- To size a goal from earlier ones, run `grep '| <repo> |' ~/.claude/retros/stats.md`: turns, tokens
  and lines. Do not read the retrospectives for this.

## Size-check item

Write the item directly before the push item (K), after the last review round and commit. Under
`delivery: commit` there is no push item: it sits directly before the retrospective item. Copy this
text into the item, with `<plugin-root>` filled in:

```markdown
Size check, as `<plugin-root>/skills/goal/size-check.md` states. A diff past `split.factor` × the
estimate adds a `Wn` row and a proposal to the retrospective file. The item runs `cure:split` only
when the PR diff (`size-check.md` defines it) also passes the cap (`split.limit`). Actions it may
run, directly or through `delivery` and `tracker`: those of `skills/split/SKILL.md`,
`agents/delivery.md` and `agents/tracker.md`. Under `delivery: commit` it pushes nothing and creates
no ticket or pull request.
```

## The retrospective

A Solo goal writes none. The format is the retrospective bullet of `rules.md` "Light and Full".

- It lives in `~/.claude/retros/`, never in `.notes/`. The user runs `/cure:retro`, which turns its
  proposals into issues and deletes it.
- "Where it went wrong" rows (`W1…Wn`) cite the turn, agent, finding id or command: rework, stale
  facts in the goal file, a stop, a permission prompt, a round that found only `NITPICK`.
- It holds no measurements; the `stats.md` row is their only copy. Assumptions and answered questions
  stay in the ledger, and the printed summary lists them.
- The session writes proposals only. It never edits a plugin or a skill.
