#!/bin/bash
export LC_NUMERIC=C
input=$(cat)

# --- palette (256-color): grey chrome, color only on the numbers ---
# Every code here is picked for contrast against one background, and no single
# 256-color code reads on both dark and white, so the light set is opt-in:
# export CURE_STATUSLINE_THEME=light
C_RESET=$'\033[0m'
C_BOLD=$'\033[1m'
C_ITALIC=$'\033[3m'
C_SEP=$'\033[38;5;243m'       # mid grey — separators & empty bar track (both themes)
if [ "$CURE_STATUSLINE_THEME" = "light" ]; then
  C_LABEL=$'\033[38;5;241m'   # dark grey — labels
  C_DIM=$'\033[38;5;241m'     # dark grey — time left
  C_LOW=$'\033[38;5;23m'      # deep teal (< 50%)
  C_MID=$'\033[38;5;94m'      # brown     (50-79%)
  C_HIGH=$'\033[38;5;160m'    # red       (>= 80%)
  C_COST=$'\033[38;5;22m'     # dark green — dollar amounts
  C_BRANCH=$'\033[38;5;25m'   # blue
else
  C_LABEL=$'\033[38;5;249m'   # soft grey-white — labels
  C_DIM=$'\033[38;5;246m'     # grey — time left
  C_LOW=$'\033[38;5;73m'      # teal    (< 50%)
  C_MID=$'\033[38;5;179m'     # amber   (50-79%)
  C_HIGH=$'\033[38;5;209m'    # coral   (>= 80%)
  C_COST=$'\033[38;5;108m'    # sage green — dollar amounts
  C_BRANCH=$'\033[38;5;110m'  # soft blue — kept off the severity hues
fi

# Pick a severity color for a percentage; the top band is also bold, so it
# does not rest on hue alone
sev_color() {
  local p=${1%.*}
  if [ "$p" -ge 80 ]; then echo "${C_BOLD}${C_HIGH}"
  elif [ "$p" -ge 50 ]; then echo "$C_MID"
  else echo "$C_LOW"; fi
}

# Build a visual progress bar: filled blocks out of 10 total, colored by severity
make_bar() {
  local pct="$1"
  local color="$2"
  local filled=$(printf '%.0f' "$(echo "$pct * 10 / 100" | bc -l)")
  [ "$filled" -gt 10 ] && filled=10
  [ "$filled" -lt 0 ] && filled=0
  local empty=$((10 - filled))
  local fb="" eb=""
  local i
  for ((i = 0; i < filled; i++)); do fb+="▓"; done
  for ((i = 0; i < empty; i++)); do eb+="░"; done
  echo "${color}${fb}${C_RESET}${C_SEP}${eb}${C_RESET}"
}

# Format the time remaining until a unix epoch: hours below two days
# ("2h", "<1h"), whole days from there on ("6d")
format_left() {
  local epoch="$1"
  local now
  now=$(date +%s)
  local delta=$(( epoch - now ))
  if [ "$delta" -le 0 ]; then
    echo "now"
  elif [ "$delta" -lt 3600 ]; then
    echo "<1h"
  elif [ "$delta" -lt 172800 ]; then
    echo "$(( (delta + 3599) / 3600 ))h"
  else
    echo "$(( (delta + 43200) / 86400 ))d"
  fi
}

# Format a USD amount: no decimals when >= 100, else 2 decimals
format_cost() {
  awk -v x="${1:-0}" 'BEGIN{ if (x+0 >= 100) printf "$%.0f", x; else printf "$%.2f", x }'
}

# --- daily / weekly cost via ccusage: cached, refreshed in the background ---
# Rendering never blocks on ccusage; the status line reads a small cache file
# that a detached background job refreshes at most once per CACHE_TTL seconds.
# ccusage runs with --offline (bundled pricing, no network) and a pinned
# version (no npx version check), so nothing here touches the internet.
CACHE="$HOME/.claude/.usage-cache"
LOCK="$CACHE.lock"
CACHE_TTL=90                 # seconds before a background refresh is triggered
NPX_PKG="ccusage@20.0.30"    # pinned so npx uses its cache offline

refresh_usage() {
  local today lookback day wk
  today=$(date +%F)
  lookback=$(date -v-8d +%F 2>/dev/null || date -d '8 days ago' +%F 2>/dev/null)
  day=$(npx --yes "$NPX_PKG" daily --json --offline --since "$today" 2>/dev/null \
    | jq -r '(.daily // .) | map(select(.period=="'"$today"'")) | (.[0].totalCost // 0)')
  wk=$(npx --yes "$NPX_PKG" weekly --json --offline --since "$lookback" 2>/dev/null \
    | jq -r '(.weekly // .) | (.[-1].totalCost // 0)')
  printf '%s %s\n' "${day:-0}" "${wk:-0}" > "$CACHE.tmp" 2>/dev/null && mv "$CACHE.tmp" "$CACHE" 2>/dev/null
}

now_epoch=$(date +%s)
cache_mtime=0
[ -f "$CACHE" ] && cache_mtime=$(stat -c %Y "$CACHE" 2>/dev/null || stat -f %m "$CACHE" 2>/dev/null || echo 0)
# Drop a stale lock left by a refresh that died mid-run (older than 5 min)
if [ -d "$LOCK" ]; then
  lock_mtime=$(stat -c %Y "$LOCK" 2>/dev/null || stat -f %m "$LOCK" 2>/dev/null || echo 0)
  [ $((now_epoch - lock_mtime)) -ge 300 ] && rmdir "$LOCK" 2>/dev/null
fi
# Kick off a detached refresh only if the cache is stale and none is running.
# mkdir is atomic, so it doubles as the "refresh in progress" guard.
if [ $((now_epoch - cache_mtime)) -ge "$CACHE_TTL" ] && mkdir "$LOCK" 2>/dev/null; then
  ( refresh_usage; rmdir "$LOCK" 2>/dev/null ) >/dev/null 2>&1 &
  disown 2>/dev/null
fi
# Read whatever is cached right now (empty on the very first render, until the
# first background refresh completes — the cost segments simply omit until then)
day_cost=""; week_cost=""
[ -f "$CACHE" ] && read -r day_cost week_cost < "$CACHE"

# Session cost — from stdin, always current
sess_cost=$(echo "$input" | jq -r '.cost.total_cost_usd // empty')

# 5-hour rate limit
five_pct=$(echo "$input" | jq -r '.rate_limits.five_hour.used_percentage // empty')
five_reset=$(echo "$input" | jq -r '.rate_limits.five_hour.resets_at // empty')

# 7-day rate limit
week_pct=$(echo "$input" | jq -r '.rate_limits.seven_day.used_percentage // empty')
week_reset=$(echo "$input" | jq -r '.rate_limits.seven_day.resets_at // empty')

# Context window usage
ctx_pct=$(echo "$input" | jq -r '.context_window.used_percentage // empty')

# Current model
model=$(echo "$input" | jq -r '.model.display_name // empty')

# Current git branch (skip optional locks to avoid conflicts)
cwd=$(echo "$input" | jq -r '.cwd')
branch=$(git -C "$cwd" --no-optional-locks symbolic-ref --short HEAD 2>/dev/null)
dirty=""
if [ -n "$branch" ]; then
  # Mark a dirty working tree with a trailing '*', italicized
  [ -n "$(git -C "$cwd" --no-optional-locks status --porcelain 2>/dev/null)" ] && dirty="*"
  # The branch is the only segment of unbounded width
  [ "${#branch}" -gt 24 ] && branch="${branch:0:23}…"
fi

# One rate-limit segment: "<window> <used>% <time left>"
limit_part() {
  local name="$1" pct="$2" reset="$3"
  local c out
  c=$(sev_color "$pct")
  out="$(printf '%s%s%s %s%.0f%%%s' "$C_LABEL" "$name" "$C_RESET" "$c" "$pct" "$C_RESET")"
  [ -n "$reset" ] && out+="$(printf ' %s%s%s' "$C_DIM" "$(format_left "$reset")" "$C_RESET")"
  echo "$out"
}

# One cost segment: "<label> $<amount>", or the bare amount for an empty label
cost_part() {
  [ -n "$1" ] && printf '%s%s%s ' "$C_LABEL" "$1" "$C_RESET"
  printf '%s%s%s' "$C_COST" "$(format_cost "$2")" "$C_RESET"
}

# Four groups: rate-limit usage, then the context window, then cost, then
# where the session is. Usage and cost run narrowest scope to widest. Segments
# join with a dot, groups with a bar.
usage=() costs=() context=() place=()

if [ -n "$ctx_pct" ]; then
  c=$(sev_color "$ctx_pct")
  context+=("$(printf '%sctx%s %s %s%.0f%%%s' "$C_LABEL" "$C_RESET" "$(make_bar "$ctx_pct" "$c")" "$c" "$ctx_pct" "$C_RESET")")
fi
[ -n "$five_pct" ] && usage+=("$(limit_part 5h "$five_pct" "$five_reset")")
[ -n "$week_pct" ] && usage+=("$(limit_part 7d "$week_pct" "$week_reset")")

# The unlabeled amount is the session, live from stdin; 1d and 7d are cached
[ -n "$sess_cost" ] && costs+=("$(cost_part "" "$sess_cost")")
[ -n "$day_cost" ] && costs+=("$(cost_part 1d "$day_cost")")
[ -n "$week_cost" ] && costs+=("$(cost_part 7d "$week_cost")")

# Default foreground: the one color that reads on any theme
[ -n "$model" ] && place+=("$model")
# Branch last: the one segment whose width varies stays off the fixed columns
if [ -n "$branch" ]; then
  if [ -n "$dirty" ]; then
    place+=("${C_BRANCH}${C_ITALIC}${branch}${dirty}${C_RESET}")
  else
    place+=("${C_BRANCH}${branch}${C_RESET}")
  fi
fi

# Join the arguments with the in-group separator
join_group() {
  local dot="${C_SEP} · ${C_RESET}" out="" p
  for p in "$@"; do out+="$p$dot"; done
  echo "${out%"$dot"}"
}

bar="${C_SEP} | ${C_RESET}"
result=""
[ ${#usage[@]} -gt 0 ] && result+="$(join_group "${usage[@]}")$bar"
[ ${#context[@]} -gt 0 ] && result+="$(join_group "${context[@]}")$bar"
[ ${#costs[@]} -gt 0 ] && result+="$(join_group "${costs[@]}")$bar"
[ ${#place[@]} -gt 0 ] && result+="$(join_group "${place[@]}")$bar"
echo "${result%"$bar"}"
