#!/bin/bash
# run_lane.sh <lane> : one unattended pass of a lane with Claude Code.
#   lanes: opportunity (apply), opportunity-hunt, opportunity-followup, opportunity-cull
#
# Minimal standalone runner. It checks the STOP file, tops up the queue from the ATS feed
# (hunt/apply lanes), builds the engine packet, and hands the lane spec + packet to
# `claude -p`. Schedule it with cron/launchd, e.g. hourly for apply and hunt.
# The original deployment ran these lanes from a larger loop runner with browser leases,
# recovery cooldowns and per-run receipts; this script keeps only the core path.
set -euo pipefail
LANE="${1:?usage: run_lane.sh <lane>}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export OPPORTUNITY_ROOT="$ROOT"
export OPPORTUNITY_RUNNER_DIR="${OPPORTUNITY_RUNNER_DIR:-$ROOT/.runner}"
SPEC="$ROOT/loop-specs/$LANE.md"
[ -f "$SPEC" ] || { echo "no spec for lane $LANE" >&2; exit 2; }
[ -e "$ROOT/STOP" ] && { echo "STOP file present; not running"; exit 0; }
[ -e "$OPPORTUNITY_RUNNER_DIR/loops/paused/$LANE" ] && { echo "lane $LANE paused"; exit 0; }

mkdir -p "$OPPORTUNITY_RUNNER_DIR/loops/receipts/$LANE"
RUN_ID="$(date +%Y%m%d-%H%M%S)"; export RUN_ID
PACKET="$OPPORTUNITY_RUNNER_DIR/loops/receipts/$LANE/$RUN_ID.packet.json"
RECEIPT="$OPPORTUNITY_RUNNER_DIR/loops/receipts/$LANE/$RUN_ID.md"

case "$LANE" in opportunity|opportunity-hunt) python3 "$ROOT/engine/ats_feed.py" || echo "ats feed failed; continuing" >&2 ;; esac
python3 "$ROOT/engine/opportunity_engine.py" prepare --lane "$LANE" --output "$PACKET"

# Strip the YAML front matter; the body is the lane prompt.
PROMPT="$(awk 'f>=2{print} /^---$/{f++}' "$SPEC")"
cd "$ROOT"
claude -p "$PROMPT

Compact packet (from engine prepare): $PACKET" \
  --permission-mode "${CLAUDE_PERMISSION_MODE:-acceptEdits}" | tee "$RECEIPT"
python3 "$ROOT/scripts/build_dashboard.py" >/dev/null || true
