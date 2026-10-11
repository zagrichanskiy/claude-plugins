#!/bin/sh
# UserPromptSubmit: restate the two flat-register rules the model drops mid-session, next to the
# newest turn. The output style carries the full rules; this keeps them from fading behind a long
# conversation. The context is hidden from the user.
cat >/dev/null

jq -n --arg c 'Flat register for this reply:
- Every numbered reference carries its name: `RND-766 (USB ethernet gadget)`, `PR #15 (load the packet filter)`, `control 2.5 (all exposed services authenticate)`. Look the name up; never a bare number.
- No soft-offer or permission closer ("want me to", "should I", "let me know if"). Do the work, or ask one direct question with named options.' \
  '{hookSpecificOutput: {hookEventName: "UserPromptSubmit", additionalContext: $c}}'
