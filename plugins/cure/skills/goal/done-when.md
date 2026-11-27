# Writing the goal's done-when list, exits, clean-up and Settled

## Done-when items

The evaluator cannot check a claim the transcript does not contain. `The gadget works` fails; `ip
addr show usb0 reports 192.168.140.1/24` passes.

- Each item has one measurable end state and the check that demonstrates it. Constraints that must
  survive the work (what must not change, what must keep passing) are their own items.
- Every outcome named in the title has an item that measures it, with its qualifiers: "one PR against
  `main`" compares the count and the base.
- An outcome stated as a value (a version, a count) is compared with that value, not only printed.
- Each command states its preconditions (a venv, a tool, a login, a running service), or a work item
  sets them up, or work item 1 checks them. Work item 1 checks every executable a done-when command
  starts with, except one that a work item builds or installs, one check each (`gh auth status`,
  `claude --version`, `python3 --version`).
- Work item 1 runs each done-when check on the base, where it must fail. The goal marks a check of a
  state the base already meets on the item itself, for example "holds on the base".
- An item that measures replies to a fixed prompt set never asks about state the run changes, such as
  the branch's commits. It states samples per prompt and the pass threshold, for example 3 runs, all
  pass.
- Write the repository's base branch in the fact check: for base `main`, `main` equals `origin/main`.
- The gate and every device check run after the last code change, or the goal says "re-run the device
  check after any code change".
- An item that counts text states the unit, the grep root, whether the match is case-sensitive and
  whether blank lines count.
- A command that can run over 120 s states its Bash timeout in its work item (the default is
  120000 ms).
- An item that claims a reboot proves it with `/proc/uptime` after the cycle below 120 s.
- Every template, Solo included, has an item that the job created or appended no
  `.notes/*backlog*.md`: `ls -l --time-style=full-iso <repo>/.notes/*backlog*.md` shows no file
  with an mtime after `<start>`, the timestamp work item 1 printed.
- An item about a skill's question round names a non-interactive test path that shows it unattended.
- A static criterion (an expected value, threshold or prompt set that does not depend on the run's
  output) is written once, in the briefs file, before measurement round 1. Changing it restarts the
  measurement round count. It does not reset the review-round cap.
- A measurement that runs `claude -p`: the fact check makes one test write to a scratch directory
  outside `~/.claude/`; a turn-limit item checks that `subtype` is not `error_max_turns` and
  `num_turns` is at most N; the run command allows `Bash` whole, with the scratch directory as its
  working directory.

## Exits

End with the exits of the mode file. The failure exit is a conjunction: a failure cause holds, the
retrospective's summary naming the cause is in the transcript, and the final message starts with
`failed:`. A Solo goal has no retrospective clause.
Print the summary; the evaluator reads the transcript only. No exit clause depends on text that
exists only in a shipped file.

## Clean-up

- Copy the clean-up work item and its done-when item from the template and fill only the path slots.
  Never shorten or merge them.
- Light and Full: write the ledger path in full in both, even when Context names it, and write out
  each deleted working file.
- Write every temporary file or directory a work item creates outside version control (a copy, a run
  directory, a worktree, a prompt or briefs file, a fixture) as a path in that work item. The same
  path goes in the clean-up item and in its done-when `ls`. The kept files and what the goal builds
  or delivers are excluded.
- The work item says the goal file and the retrospective are kept.
- Save characters in Context or the work steps.

## Settled

- A Settled statement is a decision or fact the goal rests on.
- An analysis goal that reads a design document names the document's branch or commit under Settled
  when the checkout that holds it is not on its default branch.
- A work item that runs a fresh-reader check over a document set cites `fresh-reader.md`.
  Its passes share the round limit N with the reviewer pass. Round 1 reads each whole
  document, one pass per document. Rounds 2..N re-check the previous round's findings and the lines
  changed since.
