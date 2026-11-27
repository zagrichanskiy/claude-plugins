#!/bin/sh
# PreToolUse: deny a write in the main workspace of a repo tool workspace from a session that does not
# hold the claim main. cure-job main-check reads the payload and prints the deny decision.
exec "${CLAUDE_PLUGIN_ROOT}/bin/cure-job" main-check
