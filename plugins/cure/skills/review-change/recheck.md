# Re-check mode (review-change step 1a)

| Agents | Condition |
|---|---|
| Resumed from the previous round | None on diff size. A resumed agent re-checks a diff range of any size. |
| Freshly dispatched | The diff since the last round touches 5 files or fewer and 200 changed lines or fewer (`git diff --stat <last-round-ref>..HEAD`). |

The per-leg budget of step 1 still applies.

- Give each resumed agent the ledger ids still open, from `.notes/<slug>-ledger.md`, and a diff range
  (`git diff <last-round-ref>..HEAD`) instead of a digest.
- Give a fresh agent the diff range only, with no ledger ids (they would be a topic brief).
- Add the caller's brief `Round:` line, if it has one, to every agent, resumed or fresh.
- Do not re-run the collector. `<last-round-ref>`: see step 5.
- For a C++ change, the previous round's gating stands. Skipped agents stay skipped and are listed
  again in the report. Resume every gated-in `cg-*` agent of the previous round, not only those that
  raised the round's ids.
