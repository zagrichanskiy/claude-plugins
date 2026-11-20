# Split plan

Cut the whole PR diff (`git diff --numstat <base-ref>...<old-tip>`) into parts by the split rule of `skills/dispatch/split.md` section "Split rule", with part 1 = `<branch>`. Items are the packing units. Each part is a row:

| Column | Content |
|---|---|
| Part | k = 1 to n. Part k > 1 is a stacked branch named `<slug>` (2-4 words of the part; `<tid>_<slug>` under `pr`). |
| Items | Whole items, tests with their code. |
| Delivery requirements | What the repository's PR skill or `CLAUDE.md` demands per pull request (version bump, companion PRs, CI group tag), from `preflight` with the version paths. Build a companion in another repository only when it is the run's repository or listed in `repos`; otherwise it is a manual step in the report. |
| Sibling PRs | Each pull request `preflight` found on `<branch>` in another repository: assigned to a part, or the reason it stays. |
| Planned lines | Items plus the bump lines of the part. |

First the `implementer` answers Seam checks 2 and 3 for the plan; a "no" stops the skill with nothing changed. Then, for k = 1 to n:
1. `delivery` `scratch <k>` creates `split-tmp/<k>` and leaves it checked out.
2. The `implementer` edits it. Part 1: the removal of every later part. Part k: the cut of each file that parts k and later edit; the last part to edit a file takes it whole.
3. `delivery` `commit <k>` makes one commit and measures `git diff --shortstat <previous part>...<part>` (the previous part of part 1 is `<base-ref>`). After the last part it checks the tree against the old tip.

Compare every part's size with the cap.

| State | Action |
|---|---|
| Every part at or under the cap | Go to step 4. |
| A part over the cap, first time | Re-cut once: move the last whole item of the part to the next part, or cut one feature by layer. Delete the scratch branches and rebuild them. |
| A part over the cap after the re-cut, or one unit over the cap that cannot be cut (a caller left without its callee, tests that cannot move) | Stop with `<branch>` unchanged. `delivery` deletes the scratch branches. A job adds a `Wn` row that names the overrun and delivers its single branch. |
