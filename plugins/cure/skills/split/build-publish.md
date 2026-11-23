# Split build and publish

## Build the chain

`delivery` `apply` makes the user's branches once, from the scratch branches, with the final names and messages. It deletes the scratch branches.

| Latest commit of `<branch>` | Part 1 |
|---|---|
| Unpublished (`git log origin/<branch>..<branch>` lists it; every commit is unpublished when `origin/<branch>` does not exist) | `git commit --amend --no-edit` with the tree of `split-tmp/1`. The removal joins that commit. |
| Published, Rewrite `no` or a job | A new commit "Move <items> to their own branches". No history rewrite, no force push. |
| Published, Rewrite `yes`, pull request unmerged | One squashed commit with the tree of `split-tmp/1`. Pushed in "Publish". |

Each stacked branch is created from the previous part with the commit of its scratch branch, committed with its final message (`<ticket>: <part as one sentence>` under `pr`, else the sentence; the message names no split).
`apply` then checks that each stacked tree equals its scratch tree and that the last part equals the old tip. Check each version path on its own: `git diff <old-tip> <last part> -- <version path>` may differ only in the version lines that the PR skill or `CLAUDE.md` names; every other path prints nothing. Otherwise roll back.

## Publish

`delivery` runs the brief `publish`. Order: push `<branch>`, then each stacked branch, then the pull requests in the same order. Each `git push` is its own Bash call, starting with `git -C <repo> push -u origin <name>`.
Only here, a branch already pushed is pushed again after an amend or a squash with `--force-with-lease`; a job never does.

| Branch | Pull request |
|---|---|
| `<branch>` | Reuse an `OPEN` pull request (dispatch part 1 may have created it). Otherwise create one against `<base>`. |
| Each stacked branch | Against the previous part, with the repository's PR skill when it names one. Body: 2-4 bullet items, including "Stacked on <previous PR>" and the ticket id. |

After the push `delivery` reads the tree of the last part on `origin` and compares it with the old tip as step 6 does. A failed push of `<branch>` rolls back. A failure after `<branch>` is pushed switches to `<branch>`, stops and reports what was pushed and opened. It does not roll back and pushes nothing further.

## Tickets

- Title and description state the part's scope: what it does, its commands, options, files, formats and acceptance criteria. No "Split from" line, no reference to the original ticket.
- Fields and links are copied from `<orig>` as the `tracker` prompt lists. The previous part's ticket blocks this one.
- If a create fails, or any stop rolls back after the tickets exist, the report names every ticket already created (ids and URLs).
- After the push of `<branch>` succeeds, `tracker` links the tickets (including `<orig>` to part 2) and rewrites `<orig>` to the remaining scope. Skip both with no ticket. Report a failed link or rewrite and continue.
