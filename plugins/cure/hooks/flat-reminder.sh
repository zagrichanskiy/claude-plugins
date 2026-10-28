#!/bin/sh
# UserPromptSubmit: restate the three flat-register rules the model drops mid-session (reply
# length, named references, no soft-offer closer), next to the newest turn. The output style carries
# the length and identifier rules in full; this keeps them from fading behind a long conversation.
# The context is hidden from the user.
cat >/dev/null

jq -n --arg c 'Flat register for this reply:
- A reply is a few lines, with no headings and at most one table. Add cost, limits, verification or background only when asked for them. Say in one line when a change was not run or not tested. Exceptions: error output, failing tests, security findings, confirmations for destructive actions, any detail the user explicitly asks for, and every reply made while a skill that prescribes its own reply format is in use, however the skill was started.
- Every numbered reference carries its name: `RND-766 (USB ethernet gadget)`, `PR #15 (load the packet filter)`, `control 2.5 (all exposed services authenticate)`. Look the name up; never a bare number. Cite only ids the user has seen or can open (tickets, PRs, issues, controls, sections, requirement ids). In a reply, never cite an id the user cannot open and has not seen, such as review finding numbers, ledger item numbers or a job'\''s internal step or work-item numbers; state the problem in one plain sentence. Artifacts are exempt: a commit message may carry a bare "work item N" or "step N", and a PR body names the item. A table of fixes has a Problem column before the Fix column; the problem a change solves is not background.
- No soft-offer or permission closer ("want me to", "should I", "let me know if"). Do the work, or ask one direct question with named options.' \
  '{hookSpecificOutput: {hookEventName: "UserPromptSubmit", additionalContext: $c}}'
