# Direct run

The user invokes `/cure:goal` in a working session and runs the goal in a session of their own.

## Where it goes

`.notes/goal-<slug>.md` in the repository the work happens in, `.notes/` excluded through
`$(git rev-parse --git-dir)/info/exclude` as the `note` skill describes.

A goal file is a working file. Its end is the merge of the work it describes. Say so in the report,
and delete it when that lands.

## Questions

In the question round, ask with `AskUserQuestion` and wait for the answer.

Record a fork with no user-visible effect as an assumption.

## Template text

The template's mode slots take the text below. Delete the slot text that stays unused. The
read-first line is the template's, naming `rules.md` only.

Exits, in the template's exits slot. There is no closing done-when item.

```markdown
Also done when (a) <turns> turns have passed, or <rounds> rounds ended on a measured failure, or
<review cause>, or the diff passes <lines> lines (insertions plus deletions of `git diff --shortstat <base commit>` (the commit the session started on, recorded at work item 1), plus the lines of untracked files (`git ls-files -z --others --exclude-standard | xargs -0 cat | wc -l`)), or a consult's line estimate plus the lines already changed passes <lines> lines, or `git fetch` or
a tool check failed, or a Settled statement is false or the title's outcome is unachievable, or an
asked question was dismissed or left unanswered; and (b) the retrospective's summary, naming the
cause, is in the transcript and the `stats.md` row is appended with outcome `failed`; and (c) the final message starts with `failed:`.
```

Wait exit, when the user asked the session to wait. A wait request is not a dismissed question.

```markdown
Also done when the user asked the session to wait; the final message starts with `waiting:`. `/goal @.notes/goal-<slug>.md` resumes.
```

A Solo exit has (a) without `<rounds>` and `<review cause>`, then "(b) the `stats.md` row is appended with outcome `failed`", then the final-message clause as (c).

## Launch line

```
/goal @.notes/goal-<slug>.md
```

Say once when handing it over:

- Run it in the mode its Rules state. A mode other than auto mode, including the one a Permission mode line names, stops the goal at every unapproved tool call.
- A rate limit does not clear a goal. Claude Code waits and continues. An exhausted credit balance,
  an auth failure, an unrecoverable context overflow and an unavailable model do clear it, with a
  warning; `/goal` again resumes.
