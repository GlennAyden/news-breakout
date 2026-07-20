#!/usr/bin/env bash
# Reliably trigger the price-fetch GitHub Actions workflow.
#
# GitHub's own scheduled cron is unreliable (runs are frequently throttled or
# dropped — in production it fired ~1x/day instead of every 30 min), which left
# the breakout scanner reading stale prices. A VPS cron is reliable, so we drive
# the fetch from here via the workflow_dispatch API. The fetch itself still runs
# on GitHub's clean IP (Yahoo blocks the VPS datacenter IP).
#
# Setup on the VPS:
#   1. Create a fine-grained GitHub PAT with "Actions: write" on this repo.
#   2. Add it to the repo .env:   GH_DISPATCH_TOKEN=github_pat_xxx
#   3. chmod +x scripts/trigger_fetch.sh
#   4. crontab -e (system clock is CST/UTC+8; market 09:00-16:00 WIB = 10:00-17:00 CST):
#        */30 10-17 * * 1-5 /home/ubuntu/news-breakout/scripts/trigger_fetch.sh >> /home/ubuntu/news-breakout/data_cache/trigger.log 2>&1
set -euo pipefail

MODE="${1:-intraday}"
REPO="GlennAyden/news-breakout"
WORKFLOW="price-fetch.yml"

cd "$(dirname "$0")/.."

# Read the token from .env without sourcing it (avoids executing arbitrary lines).
TOKEN="$(grep -E '^GH_DISPATCH_TOKEN=' .env 2>/dev/null | head -1 | cut -d= -f2- | tr -d '\r"'"'"' ')"
if [ -z "${TOKEN:-}" ]; then
  echo "$(date -u +%FT%TZ) ERROR: GH_DISPATCH_TOKEN not set in .env" >&2
  exit 1
fi

code="$(curl -sS -o /tmp/trigger_fetch_resp -w '%{http_code}' -X POST \
  -H "Authorization: Bearer ${TOKEN}" \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  "https://api.github.com/repos/${REPO}/actions/workflows/${WORKFLOW}/dispatches" \
  -d "{\"ref\":\"main\",\"inputs\":{\"mode\":\"${MODE}\"}}")"

if [ "$code" = "204" ]; then
  echo "$(date -u +%FT%TZ) dispatched ${WORKFLOW} (mode=${MODE})"
else
  echo "$(date -u +%FT%TZ) ERROR: dispatch failed (HTTP ${code}): $(cat /tmp/trigger_fetch_resp)" >&2
  exit 1
fi
