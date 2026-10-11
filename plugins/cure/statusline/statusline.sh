#!/bin/bash
export LC_NUMERIC=C
input=$(cat)

# --- palette (256-color): warm neutral — grey chrome, color only on the numbers ---
C_RESET=$'\033[0m'
C_SEP=$'\033[38;5;240m'     # dim grey — separators
C_LABEL=$'\033[38;5;249m'   # soft grey-white — labels (5h/7d) & reset hours
C_LOW=$'\033[38;5;73m'      # teal    (< 50%)
C_MID=$'\033[38;5;179m'     # amber   (50-79%)
C_HIGH=$'\033[38;5;209m'    # coral   (>= 80%)
C_MODEL=$'\033[38;5;252m'   # soft grey-white
C_BRANCH=$'\033[38;5;73m'   # teal — ties to the low accent
C_ITALIC=$'\033[3m'
C_COST=$'\033[38;5;108m'    # sage green — dollar amounts

# Pick a severity color for a percentage
sev_color() {
  local p=${1%.*}
  if [ "$p" -ge 80 ]; then echo "$C_HIGH"
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
  echo "${C_LABEL}[${color}${fb}${C_LABEL}${eb}]${C_RESET}"
}

# Format hours remaining until a unix epoch (e.g. "2h" or "<1h")
format_hours() {
  local epoch="$1"
  local now
  now=$(date +%s)
  local delta=$(( epoch - now ))
  if [ "$delta" -le 0 ]; then
    echo "now"
  elif [ "$delta" -lt 3600 ]; then
    echo "<1h"
  else
    local hours=$(( (delta + 3599) / 3600 ))
    echo "${hours}h"
  fi
}

# Format a USD amount: no decimals when >= 100, else 2 decimals
format_cost() {
  awk -v x="${1:-0}" 'BEGIN{ if (x+0 >= 100) printf "%.0f$", x; else printf "%.2f$", x }'
}

# --- daily / weekly cost via ccusage: cached, refreshed in the background ---
# Rendering never blocks on ccusage; the status line reads a small cache file
# that a detached background job refreshes at most once per CACHE_TTL seconds.
# ccusage runs with --offline (bundled pricing, no network) and a pinned
# version (no npx version check), so nothing here touches the internet.
CACHE="$HOME/.claude/.usage-cache"
LOCK="$CACHE.lock"
CACHE_TTL=90                 # seconds before a background refresh is triggered
NPX_PKG="ccusage@20.0.17"    # pinned so npx uses its cache offline

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
[ -f "$CACHE" ] && cache_mtime=$(stat -f %m "$CACHE" 2>/dev/null || echo 0)
# Drop a stale lock left by a refresh that died mid-run (older than 5 min)
if [ -d "$LOCK" ]; then
  lock_mtime=$(stat -f %m "$LOCK" 2>/dev/null || echo 0)
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
# Mark a dirty working tree with a trailing '*', italicized
dirty=""
if [ -n "$branch" ] && [ -n "$(git -C "$cwd" --no-optional-locks status --porcelain 2>/dev/null)" ]; then
  dirty="$C_ITALIC"
  branch="${branch}*"
fi

parts=()

# 1. Current session cost (live, from stdin)
if [ -n "$sess_cost" ]; then
  parts+=("$(printf '%s%s%s' "$C_COST" "$(format_cost "$sess_cost")" "$C_RESET")")
fi

if [ -n "$five_pct" ]; then
  c=$(sev_color "$five_pct")
  label="$(printf '%s5h:%s %s%.0f%%%s' "$C_LABEL" "$C_RESET" "$c" "$five_pct" "$C_RESET")"
  [ -n "$five_reset" ] && label+="$(printf ' %s%s%s' "$C_LABEL" "$(format_hours "$five_reset")" "$C_RESET")"
  parts+=("$label")
fi

if [ -n "$week_pct" ]; then
  c=$(sev_color "$week_pct")
  label="$(printf '%s7d:%s %s%.0f%%%s' "$C_LABEL" "$C_RESET" "$c" "$week_pct" "$C_RESET")"
  [ -n "$week_reset" ] && label+="$(printf ' %s%s%s' "$C_LABEL" "$(format_hours "$week_reset")" "$C_RESET")"
  parts+=("$label")
fi

# Per-day cost (cached)
if [ -n "$day_cost" ]; then
  parts+=("$(printf '%stoday%s %s%s%s' "$C_LABEL" "$C_RESET" "$C_COST" "$(format_cost "$day_cost")" "$C_RESET")")
fi

# Per-week cost (cached)
if [ -n "$week_cost" ]; then
  parts+=("$(printf '%sweek%s %s%s%s' "$C_LABEL" "$C_RESET" "$C_COST" "$(format_cost "$week_cost")" "$C_RESET")")
fi

if [ -n "$ctx_pct" ]; then
  c=$(sev_color "$ctx_pct")
  parts+=("$(printf '%s %s%.0f%%%s' "$(make_bar "$ctx_pct" "$c")" "$c" "$ctx_pct" "$C_RESET")")
fi

[ -n "$model" ] && parts+=("$(printf '%sClaude %s%s' "$C_MODEL" "$model" "$C_RESET")")
[ -n "$branch" ] && parts+=("$(printf '%s%s%s%s' "$C_BRANCH" "$dirty" "$branch" "$C_RESET")")

sep="${C_SEP} | ${C_RESET}"
result=""
for p in "${parts[@]}"; do
  result+="$p$sep"
done
echo "${result%$sep}"
