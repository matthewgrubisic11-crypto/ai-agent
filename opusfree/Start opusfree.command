#!/usr/bin/env bash
# macOS double-click launcher. Finder runs .command files in Terminal on
# double-click. This just hands off to the setup+run script (which installs
# anything missing the first time, then launches fast on repeat runs).
cd "$(dirname "$0")"
exec bash setup_and_run.sh
