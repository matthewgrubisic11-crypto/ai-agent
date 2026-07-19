#!/usr/bin/env bash
# opusfree one-click setup + run for macOS / Linux.
# Double-click it (or run: bash setup_and_run.sh). It installs what's missing,
# then starts the web app and opens it in your browser.
set -e
cd "$(dirname "$0")"

echo "== opusfree setup =="

# 1. Python check
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 is not installed. Get it from https://python.org/downloads then re-run this."
  exit 1
fi

# 2. ffmpeg check (+ auto-install)
# Bring Homebrew onto PATH if it's installed but not yet exported (Apple Silicon).
if ! command -v brew >/dev/null 2>&1; then
  if [ -x /opt/homebrew/bin/brew ]; then eval "$(/opt/homebrew/bin/brew shellenv)";
  elif [ -x /usr/local/bin/brew ]; then eval "$(/usr/local/bin/brew shellenv)"; fi
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "ffmpeg not found — attempting to install it..."
  if [ "$(uname)" = "Darwin" ]; then
    # macOS: need Homebrew first; install it if missing (asks for your password).
    if ! command -v brew >/dev/null 2>&1; then
      echo "Homebrew is required to install ffmpeg. Installing Homebrew now..."
      echo ">> It will ask for your Mac password. Nothing shows as you type — that's normal."
      echo ">> If it says 'Press RETURN to continue', press Enter."
      /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
      if [ -x /opt/homebrew/bin/brew ]; then eval "$(/opt/homebrew/bin/brew shellenv)";
      elif [ -x /usr/local/bin/brew ]; then eval "$(/usr/local/bin/brew shellenv)"; fi
    fi
    if command -v brew >/dev/null 2>&1; then
      brew install ffmpeg
    else
      echo "Homebrew install did not finish. Open a NEW Terminal window and run this script again."
      exit 1
    fi
  elif command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update && sudo apt-get install -y ffmpeg
  else
    echo "Could not auto-install ffmpeg. Install it from https://ffmpeg.org/download.html then re-run."
    exit 1
  fi
fi

# 3. Python dependencies
echo "Installing Python packages (first time only)..."
python3 -m pip install --quiet --upgrade pip
python3 -m pip install --quiet -r requirements.txt

# 4. Launch + open browser
URL="http://localhost:8500"
echo "Starting opusfree at $URL  (close this window to stop it)"
( sleep 3; (command -v open >/dev/null && open "$URL") || (command -v xdg-open >/dev/null && xdg-open "$URL") ) >/dev/null 2>&1 &
python3 webrun.py
