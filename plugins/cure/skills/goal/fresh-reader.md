# Fresh-reader check

A fresh-reader check has a reader with no context read a document set and report each element it
cannot explain. Each such element counts as a `SHOULD-CONSIDER` finding.

- Review round k holds the reviewer pass and the fresh-reader passes. Both share the limit N.
- Round 1 runs one pass per document. Each pass reads the whole document, not the diff.
- The changed lines of round k (k ≥ 2) are those of `git diff <commit round k-1 read>..HEAD` over
  the document set.
- Rounds 2..N run one pass per document that has a changed line or a finding of the previous round.
- The reader reads whole documents and gets no briefing on earlier findings.
- The orchestrator sorts the findings by line. A finding of the previous round and a finding on a
  changed line belong to the round.
- Any other finding is a new topic: it belongs to the round only when it is a behaviour defect. The
  orchestrator drops a new topic that is not one.
- The reader's brief carries no Settled list. The orchestrator drops a reader finding that a Settled
  decision answers.
