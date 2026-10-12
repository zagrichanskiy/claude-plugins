#!/bin/sh
# UserPromptSubmit: restate the three flat-register rules the model drops mid-session (reply
# length, named references, no soft-offer closer), next to the newest turn. The output style carries
# the full rules; this keeps them from fading behind a long conversation. The context is hidden from
# the user.
cat >/dev/null

jq -n --arg c 'Flat register for this reply:
- A reply is a few lines: at most six short bullets or one table. No headings, no second table. Add cost, limits, verification or background only when asked for them. Exceptions: error output, failing tests, security findings, confirmations for destructive actions, and detail the user explicitly asked for.
- Every numbered reference carries its name: `RND-766 (USB ethernet gadget)`, `PR #15 (load the packet filter)`, `control 2.5 (all exposed services authenticate)`. Look the name up; never a bare number.
- No soft-offer or permission closer ("want me to", "should I", "let me know if"). Do the work, or ask one direct question with named options.' \
  '{hookSpecificOutput: {hookEventName: "UserPromptSubmit", additionalContext: $c}}'
