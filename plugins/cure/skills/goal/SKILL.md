---
description: Write the goal file that `/goal @<file>` runs from — a self-contained brief a fresh session can execute unattended, either for a direct run in the current session or for a job run launched by the dispatcher from a handoff file. Chooses an agent tier from size and risk, asks every open question in one round, then writes the orchestrator-led work items with an agent per step and a closing retrospective, the measurable done-when list and the standing rules. Use when the user says "write a goal", "create a goal md", "capture this as a goal", or "/cure:goal", or when the dispatcher passes a handoff path or a job directory.
allowed-tools: Read, Write, Edit, Grep, Glob, Bash, AskUserQuestion
---

# Goal

`/goal <condition>` is a built-in command. It sets a completion condition, and a small fast model
re-reads it after every turn: not yet met starts another turn, met or impossible clears it. The
evaluator runs no tools and reads no files — it judges only what the session has already put in the
transcript.

This skill writes the file behind `/goal @<file>`. The file is the condition, not a design document.
Everything in it is read by the evaluator on every turn and must be something the session's own
output can demonstrate.

## Mode

| Given | Mode | Read exactly one file |
|---|---|---|
| A handoff path or a job directory | Job run: a worker session runs the goal and ends through `done`, `failed:` or `needs-input:` | `${CLAUDE_PLUGIN_ROOT}/skills/goal/job.md` |
| Neither | Direct run: the user runs the goal in a session | `${CLAUDE_PLUGIN_ROOT}/skills/goal/direct.md` |

Plugin root: `${CLAUDE_PLUGIN_ROOT}`. Only this file has the variable expanded. The mode files use
a `<plugin-root>` slot. Write this value into it when writing the goal file.

Read the file for the chosen mode before the question round. Never read both. The sections below
apply to both modes. The mode file adds what is specific to its mode.

## The question round comes first

**Ask every open question before writing the file, in one round.** The mode file says how. This is
the point of the whole skill. The user answers once, then leaves; a goal that stops on turn six to
ask which subnet to use has wasted the time it was meant to save.

Before asking, settle everything you can yourself — read the code, the recipe, the ticket. What
survives is a real fork: two readings that produce different work. For each, give the options you
would actually recommend between, each an action the session or the tools it runs can take (in job
mode, `cure-job` is one such tool). Each question carries its own context: the situation, the
options, the consequence of each, and a recommendation, for a reader who has not followed the run.

A question is a choice that changes behaviour the user would see, or a place where the source
(conversation, handoff or design document) is silent or contradictory on such a choice. Never decide
a question silently. A mechanical choice that the code or the conventions determine is decided by
the session and recorded as an assumption. A fork whose options differ in nothing the user would see
is not a question: take the recommended option and record it as the mode file says.

Print the chosen agent tier and its reason as part of the round (see "Agent tier"). When there is
no question, print the tier decision alone and ask nothing. The user can override the tier.

When a docs review may find two files that state one rule differently, no rule is known at question time. One question asks for an ownership policy: the file whose topic the rule is, or an ordered list of files. The answer goes under Settled.

Then, and only then, write the file. The mode file says where it goes.

## What goes in it

**The goal file carries the context. The ticket stays thin.** A fresh session opens with `/goal
@<file>` and nothing else, so whatever it needs to act must be in the file or reachable from it.

Keep it short: the evaluator re-reads the whole file every turn. No `/goal` length limit was
observed. Goals of 4317-5871 characters ran under `/goal @<file>` on Claude Code 2.1.301, and one of
4532 characters on 2.1.302. Measure the file with `wc -c <file>` after writing it and report the
count. Reference rather than restate:
the repository's `CLAUDE.md` already covers conventions, layout and working style, and the code and
recipes say what they contain. Name the file to read; do not summarise it. What the file must hold
outright is what reading the repository will not tell you — the decisions taken in conversation and
the reasoning that would otherwise be re-litigated.

## Anatomy

```markdown
# <What is true when this is done>

## Context

<Where the work happens. Settled: the decisions and facts.>

## Work

Before work item 1, read `<plugin-root>/skills/goal/rules.md` and follow it. Read it again after a
context compaction and before an exit.

1. Fact check: `<base>` equals `origin/<base>` (for a base taken from a predecessor, the check of `rules.md`); <ticket, branch, named files>; <each tool Done-when
   runs>; <each Settled fact marked verify>.
2. <One step, its agent, its files.>
N-2. (Light and Full) Write the retrospective to `~/.claude/retros/<date>-<repo>-<slug>.md`; print
     its summary.
N-1. Append the `stats.md` row with the command of `rules.md`. `<date> | <repo> | <slug>` is filled
     in here.
N. Delete `<ledger path>` and `<each working file>`. Keep the goal file, the retrospective,
   `.notes/<slug>-backlog.md`. The failure path skips this item.

## Done when

1. <Measured by a command this session runs.>
N-2. (Light and Full) The retrospective has "Outcome", "Where it went wrong" and "Proposed changes" sections; its summary is printed.
N-1. `grep -cF '| <date> | <repo> | <slug> |' ~/.claude/retros/stats.md` prints `1`.
N. `ls <ledger path> <working files>` reports "No such file" for each.

<Mode file: the closing done-when item, if any.>

<Exits: the mode file's text. It holds the failure exit, with <review cause> from "Agent tier".>

## Rules

- Tier: <Solo, Light or Full>. <Agent plan: steps, agents, parallel work, advisor.>
- Stops: this goal overrides the user's "run one step and stop" rule; it stops only at its exits.
- Permission mode: <acceptEdits for a goal that edits skill, agent or other plugin files; omit otherwise>.
- Waiting: <job mode: the mode file's Waiting line. Direct mode: takes the `waiting:` exit of direct.md>.
```

## Writing the done-when list

The evaluator cannot check a claim the transcript does not contain. `The gadget works` fails; `ip
addr show usb0 reports 192.168.140.1/24` passes, because running it puts the answer where the
evaluator can read it.

Each item needs one measurable end state and the check that demonstrates it. Add the constraints
that must survive the work — what must not change, what must keep passing — as their own items;
those are the ones a goal quietly breaks.

Rules for the items:

- Every outcome named in the title has an item that measures it. An outcome with no item passes
  unproven. An outcome is measured with its qualifiers: "one PR against `main`" needs an item that
  compares both the count and the base, not the count alone.
- An outcome stated as a value (a version, a count) is compared with that value, not only printed.
- Each command states its preconditions (a venv, a tool, a login, a running service), or a work item
  sets them up, or work item 1 checks them. Work item 1 checks every executable a done-when command
  starts with, except one that a work item builds or installs, one check each (`gh auth status`,
  `claude --version`, `python3 --version`), not only these examples.
- An item that measures replies to a fixed prompt set never asks about state the run changes, such
  as the branch's commits.
- An item that measures a model's replies to a fixed prompt set states samples per prompt and the
  pass threshold, for example 3 runs, all pass.
- Write the repository's base branch in the fact check. For base `main` the file says `main` equals
  `origin/main`.
- The gate and every device check run after the last code change, or the goal says "re-run the device check after any code change".
- An item that counts text states the unit, the grep root, whether the match is case-sensitive and
  whether blank lines count.
- A command that can run over 120 s states its Bash timeout in its work item; the tool default is 120000 ms.
- An item that claims a reboot proves it with `/proc/uptime` after the cycle below 120 s.
- An item about a skill's question round names a non-interactive test path that shows it unattended.
  For a manual check, see "Verification".
- A static criterion is an expected value, threshold or prompt set that does not depend on the run's
  output. It is written once, in the briefs file, before measurement round 1. Changing it restarts the
  measurement round count. It does not reset the review-round cap in "Review-then-fix split".
- A measurement that runs `claude -p`:
  - The fact check makes one test write to a scratch directory outside `~/.claude/`.
  - A done-when item with a turn limit checks that `subtype` is not `error_max_turns` and
    `num_turns` is at most N.
  - The run command allows `Bash` whole, with the scratch directory as its working directory.

Always end with the exits in the mode file. The `/goal` Stop hook blocks every stop that is not a
met condition, so a cap that only says "stop" blocks every stop after it. The failure exit is a
conjunction: a failure cause holds, the retrospective's summary naming the cause is in the
transcript, and the final message starts with `failed:`. A Solo goal has no retrospective clause; its failure exit has the `stats.md` clause.
The evaluator reads the transcript only, so the summary is printed, not just written to a file. No
exit clause depends on text that exists only in a shipped file.

The clean-up work item and its done-when item are copied from the template with only the path slots
filled. Never shorten or merge them to save characters. Write the ledger path in full in both
(Light and Full), even when Context names it, and write out each deleted working file. Every
temporary file or directory a work item creates outside version control (a temporary copy, a run
directory, a worktree, a prompt or briefs file, a fixture) is written as a path in that work item,
and the same path is in the clean-up item and in its done-when `ls`. This excludes the kept files
and what the goal builds or delivers. The work item says the goal file, the retrospective and the
backlog are kept. Save characters in Context or the work steps.

A Settled statement is a decision or fact the goal rests on. A false one fails the run.
A Settled statement that adds a step to the dispatcher names the `next` state rows that must reach it.
A Settled fact copied from a note (a device or system fact) is marked "verify". Work item 1's fact
check verifies it against the device, code or document the note cites, not against the note.
A mismatch in ticket, branch or base commit is recorded and corrected.
When writing a backlog-fix goal, check each backlog item against the document at `<base>`.
List the items already fixed under Settled.
For a backlog row that defines a term, the goal quotes the definition.
An analysis goal that reads a design document names the document's branch or commit under Settled
when the checkout that holds the document is not on its default branch.

## Name the tools, not the intention

A goal file is written for one repository, so it names that repository's own agents, skills and
commands. `verify it works` gets satisfied by reasoning about the code; `prove it on the device with
<the project's hardware agent>` does not. The same holds for the build command, the review agent,
and the skill that opens the pull requests.

Take the names from the session's own agent and skill list (a handoff's `## Tools` section, when
the mode file names one), and prefer the project's plugin over a general one wherever both offer
something. A general plugin's reviewer named for work a project
agent covers proposes a tool the project does not use.

A goal for an issue that changes how a job is launched or resumed names `agents/dispatcher.md` in the
work item that makes the change. A goal that changes a format a run session follows names `rules.md` or `worker.md`, and its copy in `agents/orchestrator.md`, in the work item that makes the change. All tiers follow these rules.

## Delegate, then reflect

Every Light and Full goal has this structure. A Solo goal has the session alone. The user runs goals
unattended and pays for the orchestrator's context on every turn.

| Part | What the goal file states |
|---|---|
| Orchestrator | The main session dispatches, tracks and checks. It does not read source or edit code. |
| Branch and commits | Branch creation and every commit are orchestrator work items, committed with explicit paths. No work item or agent brief assigns them to `implementer`, `test-author` or `skill-author`, because these agents refuse to create a branch or commit. The orchestrator's commit messages omit attribution trailers (`Co-Authored-By`, `Claude-Session:`, "Generated with") when the user's `CLAUDE.md` forbids them, because that file overrides a session attribution reminder. Trailers the repository requires, such as `Signed-off-by:`, stay. |
| Agent per step | Each work item names its agent. Items with disjoint files run in parallel. Two writing agents that share a CLI or a file format get its command names, run semantics and format in both briefs; otherwise the docs agent runs after the CLI. |
| Review-then-fix split | Round 1 produces a triaged fix list, not fixes. Fixes ship as small PRs per component, each with at most 3 review rounds, the cap counted per PR and not across the whole effort, and a round ended by a measured failure counts apart from a round spent on review findings. A measured-failure round is one that ended on a failed test or check, not on review findings. The round cap is a failure exit in the template. A `MUST-FIX` or `SHOULD-CONSIDER` still open after a PR's round 3 takes the failure exit; no round 4 starts. Round 3 only re-checks findings that round 2's fixes introduced or left open and raises no new topic. The orchestrator commits each round's fixes with explicit paths, new files included, before the re-check runs. One doc-only edit pass is allowed after the last review round. A doc-only pass changes no file that the build, the tests, or a loaded skill or agent reads. |
| Consultation | Which advisor answers a hard implementation question: `designer` for class level, `architect` for component level. The answer is recorded before the implementer starts. A class flagged in 2 consecutive review rounds gets a `designer` consult before an implementer touches it again; the round-1 triage and the PR's first review round count as consecutive for this gate. The orchestrator never writes the class-level decision itself. |
| Review loop | Review, fix, re-review stops at the severity floor: done when no `MUST-FIX` or `SHOULD-CONSIDER` finding is open. `NITPICK` and `enhancement`-tagged findings go to a backlog, not into another round; the backlog never holds a `MUST-FIX` or `SHOULD-CONSIDER`; a `SHOULD-CONSIDER` that needs only an owner decision on behaviour a fix introduced is asked before its round closes; see the `review-change` skill for the triage words. A ledger file holds every finding and its status, every assumption and every question with its answer. State a token budget per agent per round in the goal. |
| Verification | `qa` runs the suite after each fix. Its pass count is a done-when item. Before merge, a live-verification gate also runs: the `verifier` agent's output is the done-when item. An unattended session cannot prove a manual check, so a manual check goes into the PR checklist, never into the done-when list. A green test suite alone does not clear this gate. |
| Retrospective | A work item and a done-when item before the stats row item. |
| Stats row | The second-last work item and the done-when item before the clean-up item, in every tier. |
| Implementer brief | When the repository ships a versioned plugin or package, the brief states: bump the version once per branch, not per commit, and points to the repository's version rule where its `CLAUDE.md` has one. |

## Agent tier

Choose the tier by judgement from size and risk, not size alone. A small change that is crucial
(security, data loss, a public interface, hard to reverse) takes a higher tier.

| Tier | Choose when | Agents |
|---|---|---|
| Solo | A small, low-risk change | None. The session running the goal does the task itself and runs the done-when checks. |
| Light | A modest change with contained risk | Implementer, `qa`, one reviewer, retrospective. |
| Full | A large or risky change | `designer` or `architect` consult, implementer, `test-author`, `qa`, `review-change`, `verifier`, retrospective. |

There is no tier without a goal file. The work items name the tier's agents. The review-loop and
verification rows above describe Full. Light has one review round by one reviewer, except as stated below, and no
live-verification gate.

A Light goal that changes both `agents/dispatcher.md` and a worker prompt (`skills/goal/rules.md`,
`worker.md`, `job.md` or `agents/orchestrator.md`) has two review rounds. The second round re-checks
only the first round's fixes.

A Solo goal differs from the template as follows:

- Work: the read-first line, item 1, the task, and a clean-up item only when the task creates a
  working file. The clean-up item and its done-when item carry at least one path. With no working
  file, write neither; never write an empty path list. Its clean-up item reads "Delete `<each working file>`. Keep the goal
  file."
- No retrospective work item or done-when item, no ledger, no backlog. The stats row work item and
  done-when item stay, with `<date> | <repo> | <slug>` filled in.
- Exits: drop `<rounds>`, `<review cause>` and the retrospective clause from the failure exit.
- Rules: the lines "Tier: Solo.", Stops, Permission mode (when the goal edits plugin files) and Waiting.

The review-round cap and failure cause come from this tier rule, or from the user's own statement
in a direct run. A cap in a handoff or a design source is never copied into the goal. The failure cause in the exit text, by tier:

| Tier | `<review cause>` |
|---|---|
| Light | a `MUST-FIX` or `SHOULD-CONSIDER` is open after `qa` re-checks the review round's fixes |
| Light, two review rounds | a `MUST-FIX` or `SHOULD-CONSIDER` is open after `qa` re-checks round 2's fixes |
| Full | a `MUST-FIX` or `SHOULD-CONSIDER` is open after a PR's review round 3 |
| Solo | none |

## The retrospective

A Solo goal writes none. The format below is copied into `rules.md` "Light and Full", which the session reads. A retrospective lives in `~/.claude/retros/`, not in `.notes/`. It is a short-lived inbox item: the user runs `/cure:retro`, which turns its proposals into issues and deletes it. A working note is deleted when its work merges, and a retrospective there is deleted with it before anyone acts on it.

It holds these sections, in this order, and no others:

| Section | Content |
|---|---|
| Outcome | "met", or "failed: <cause>, what is left". |
| Where it went wrong | One row per event, `W1…Wn`, with its evidence: the turn, agent, finding id or command. Rework, stale facts in the goal file, a stop, a permission prompt, a round that found only `NITPICK`. |
| Proposed changes | The table below. |

Proposed changes table: `| Target | Change | Evidence (Wn) | Expected effect |`. One row per change. Target forms:

| Form | Meaning |
|---|---|
| `<plugin>:<path>` | A file in a plugin, for example `cure:skills/goal/rules.md` |
| `repo:<path>` | A file in the goal's own repository |
| `user:CLAUDE.md` | The user's global instructions |

A proposal with no `Wn` evidence is not made. The retrospective holds no measurements: the `stats.md` row is their only copy. Assumptions and answered questions stay in the ledger, and the printed summary lists them. The session writes proposals only; it never edits a plugin or a skill. The user applies them through `/cure:retro`.

## Sizing a goal

Bound a goal by deliverables, not by lines: one reviewable concern, one PR, and a done-when list the
user can re-run. The changed-line cap in the failure exit is a stop signal, not the scope. A goal that
reaches it takes the failure exit instead of growing.

- Count changed lines as the failure exit states: `git diff --shortstat <base>` plus the lines of untracked files. Do not use `git add -N`; its entries break `git stash` and `git rebase`.
- Estimate tests apart from code. Tests of a state-machine change are estimated at 2x its code. Validator tests are estimated per key. A legacy parser is estimated separately.
- The test-author brief states a line budget beside the list of behaviours to cover. The budget is the test estimate above.
- A goal with a test-author step has a work item between the implementer item and the test-author item. It measures the diff as the failure exit states and prints the count.
- The cut line is the point where a change is divided into a delivered part and a rest. The goal writer plans it, or the session that writes the follow-up goal after a failure exit at the cap applies it. Under `delivery: pr`, it rewords the ticket to the delivered part and opens a new ticket for the rest. Each ticket has one PR per repository, and the PR does not reference the split.

Size a goal from `~/.claude/retros/stats.md`: `grep '| <repo> |' ~/.claude/retros/stats.md` lists
the earlier goals of the repository with their turns, tokens and lines. Do not read the retrospectives for this.

## Running it

Report the launch line the mode file gives. A job run of tier Light or Full starts with `--agent cure:orchestrator`, which carries `rules.md` and `worker.md` in its system prompt. A Solo job run and a direct run start as plain sessions.

## Notes

- One goal, one file. A brief covering two unrelated outcomes converges on neither.
- Carry every work item inline, by id and text. Do not point at another note by `file:line`. Notes
  are deleted and edited, and the reference goes stale without an error.
- Write the goal just before it runs. A goal written days ahead carries facts that have drifted.
  Work item 1 catches some of them, not all.
- Keep rejected options out. The evaluator re-reads this file every turn and a rejected option in it
  reads as work to do. If the rationale is worth keeping, it goes in the ticket or the design
  document.
- Do not start implementing. Write the file, report the path and the command, and stop.
