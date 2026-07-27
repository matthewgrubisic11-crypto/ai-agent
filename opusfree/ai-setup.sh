#!/usr/bin/env bash
# Set up a FREE, LOCAL AI brain for opusfree — no account, no API key, no
# region/age restrictions. Installs Ollama and a compact model that runs well
# on a laptop, then points opusfree at it. Run once:  bash ai-setup.sh
set -e
cd "$(dirname "$0")"

MODEL="llama3.2"   # ~2GB, fast on laptops; good enough for clip selection

echo "== Setting up a free local AI brain (Ollama) =="

# 1. Install Ollama if missing.
if ! command -v ollama >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    echo "Installing Ollama via Homebrew..."
    brew install ollama
  else
    echo "Please install Ollama from https://ollama.com/download , then re-run this."
    exit 1
  fi
fi

# 2. Make sure the Ollama server is running (and stays running).
if ! curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
  echo "Starting the Ollama server..."
  # brew services keeps it alive across reboots / closed terminals.
  brew services start ollama >/dev/null 2>&1 || (ollama serve >/tmp/ollama.log 2>&1 &) || true
  sleep 4
fi

# 3. Download the model (one time; a couple of GB).
echo "Downloading the AI model '$MODEL' (one time, a few minutes)..."
ollama pull "$MODEL"

# 4. Point opusfree at it.
[ -f .env ] || cp .env.example .env 2>/dev/null || touch .env
if ! grep -q '^OPUSFREE_LLM_MODEL=' .env 2>/dev/null; then
  echo "OPUSFREE_LLM_MODEL=$MODEL" >> .env
fi
if ! grep -q '^OPUSFREE_LLM_PROVIDER=' .env 2>/dev/null; then
  echo "OPUSFREE_LLM_PROVIDER=ollama" >> .env
fi

echo ""
echo "✓ Local AI brain ready — no account, no keys, fully free."
echo "  Now start opusfree with:  bash update.sh"
