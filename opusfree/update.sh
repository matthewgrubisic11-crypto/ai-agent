#!/usr/bin/env bash
# opusfree updater: force-sync to the latest pushed version and relaunch.
# Safe because all code comes from the remote -- no local edits to preserve.
# Run this (in ONE terminal) whenever you want the newest version:
#     bash update.sh
set -e
cd "$(dirname "$0")"

BRANCH="claude/question-eqvx2c"

echo "== Stopping any running opusfree =="
lsof -ti:8500 | xargs kill -9 2>/dev/null || true

echo "== Syncing to the latest version (discarding local divergence) =="
git fetch origin "$BRANCH"
git reset --hard "origin/$BRANCH"

echo "== Launching =="
exec bash setup_and_run.sh
