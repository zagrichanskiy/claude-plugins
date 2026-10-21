#!/bin/sh
# PreToolUse: deny writing a commit message, pull request, issue or ClickUp task whose text has an
# identifier without its name or a soft-offer closer. These texts outlive the session, so this is
# where a check can stop the text before anyone reads it. Code spans and fenced blocks are skipped,
# so quoting a pattern is not a violation.
payload=$(cat)

tool=$(printf '%s' "$payload" | jq -r '.tool_name // ""')

case "$tool" in
  Bash)
    command=$(printf '%s' "$payload" | jq -r '.tool_input.command // ""')
    printf '%s' "$command" | grep -Eq 'git([[:space:]]+-[Cc][[:space:]]+[^[:space:]]+)*[[:space:]]+commit|gh[[:space:]]+(pr|issue)[[:space:]]+(create|edit|comment)' \
      || exit 0
    text=$command
    # A message passed by file: `git commit -F <file>`, `gh ... --body-file <file>`.
    for file in $(printf '%s' "$command" | perl -ne 'print "$1\n" while /(?:\s-F|--body-file|--file)[=\s]+(\S+)/g'); do
      [ -f "$file" ] && text="$text
$(cat "$file")"
    done
    ;;
  mcp__*[Cc]lick[Uu]p*)
    printf '%s' "$tool" | grep -Eiq 'create|update|comment' || exit 0
    text=$(printf '%s' "$payload" | jq -r '[.tool_input | .. | strings] | join("\n")')
    ;;
  *)
    exit 0
    ;;
esac

findings=$(printf '%s' "$text" | perl -0777 -ne '
  s/```.*?```//gs;
  s/`[^`\n]*`//g;
  # A work-item or step number is a reference, not an identifier.
  s/\bwork\s+items?\s+#?\d+(?:\.\d+)?//gi;
  # An identifier with a number must carry its name in parentheses right after it.
  while (/\b((?:item|task|control|question|section|requirement|epic|milestone)s?\s+#?\d+(?:\.\d+)?|(?:RND|OPS|SEC)-\d+|(?:PR|issue)\s+#\d+)(?![\d.])(?!\s*\()/gi) {
    print "bare identifier: $1\n";
  }
  # Soft offers and permission-asking closers.
  while (/((?:want me to|would you like|do you want me|should i|shall i|say if you want|let me know if|if you want,? i)\b[^.?!\n]{0,60})/gi) {
    print "soft offer: $1\n";
  }
' | sort -u | head -12)

[ -n "$findings" ] || exit 0

reason="Flat register, fix and retry:
$findings
Write each identifier with its name in parentheses; drop soft offers."

jq -n --arg r "$reason" \
  '{hookSpecificOutput: {hookEventName: "PreToolUse", permissionDecision: "deny", permissionDecisionReason: $r}}'
