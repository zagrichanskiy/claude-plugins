# Split tests and fix loop

Read this before step 4. Test `split-tmp/1`, then each later scratch part, in order.

| Result | Action |
|---|---|
| A part fails | `delivery` `old-tip clone` creates a clone, `qa` runs the same tests there, then `delivery` removes the clone. A failure there too is environment: report it, no roll back, no seam verdict. Otherwise run once more; a second failure rolls back, stops and reports. |
| All parts pass | Dispatch the `reviewer` on `git diff <old-tip> split-tmp/1`. Its brief adds checks 2 and 3 of section "Seam". A failed check is a MUST-FIX. |
| MUST-FIX or SHOULD-CONSIDER on a reference the removal exposes (comment, doc, name) | Fix loop of at most 2 rounds. `delivery` `fix <k>` (`open`) checks out the part. The `implementer` edits it. `delivery` `fix <k>` (`amend`) amends the paths into the part's single commit. `delivery` `restack` rebases the later scratch parts onto it. `qa` re-tests the changed parts and `reviewer` checks again. A finding still open after the loop: roll back, stop and report. |
| A restack conflict, or a failed tree check after a fix | No roll back for a reference fix. On a conflict, `restack` resolves it inside the rebase and continues; a conflict on any other path aborts the rebase and is reported. After a failed tree check no rebase is in progress, so nothing is aborted. The `implementer` restores the old-tip text of each file the fix touched (`git checkout <old-tip> -- <path>`) in the part that brings the referenced scope back, so the last part equals the old tip again. `delivery` wraps the restore in `fix <j>` `open` and `amend` for that part j. Then `restack` from the part after j, given the plan rows (the paths each part takes whole or cuts). An aborted restack ends the fix loop and rolls back before the ticket step. A second failure counts as a round of the loop. |
| Any other MUST-FIX or SHOULD-CONSIDER | Roll back, stop and report. |
