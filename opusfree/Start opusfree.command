#!/usr/bin/env bash
# macOS double-click launcher for opusfree.
# Auto-updates to the latest version, then installs (if needed) and runs.
# Grouped block + exec so the script is fully read before it updates itself.
cd "$(dirname "$0")" || exit 1
{
  echo "Updating opusfree to the latest version..."
  git fetch origin claude/question-eqvx2c >/dev/null 2>&1
  git reset --hard origin/claude/question-eqvx2c >/dev/null 2>&1
  lsof -ti:8500 | xargs kill -9 >/dev/null 2>&1
  exec bash setup_and_run.sh
}
