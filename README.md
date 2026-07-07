# Personal Agentic Assistant

A personal agent powered by Claude (`claude-opus-4-8`) with two interfaces: **Telegram** and a **web console** (browser chat + live dashboard of the agent's memory and scheduled tasks). Not just a chatbot — an agent with an agentic loop:

- **Tool use** — Claude decides when to act, your code executes, results feed back until the task is done
- **Web search** — answers with current information (server-side tool, no setup)
- **Permanent memory** — stores durable facts about you (name, timezone, preferences, projects) in SQLite and recalls them in every conversation
- **Self-scheduling** — tell it *"every morning at 8am, send me the top AI news"* and it schedules itself; jobs persist across restarts

## Architecture

```
agent.py      Entry point: Telegram interface + starts web console & scheduler
web.py        Web console: browser chat + memory/tasks dashboard (aiohttp)
brain.py      Claude agent loop + tool definitions/execution
memory.py     SQLite: conversation history, facts, scheduled jobs
scheduler.py  Background loop that fires scheduled tasks autonomously
```

## Web console

The same process serves a web UI on `PORT` (default 8080) — open `http://localhost:8080` locally, or your app's public URL once deployed. It shows the chat, everything the agent remembers, and its scheduled tasks (with one-click cancel). Set `WEB_PASSWORD` to protect it — **strongly recommended before deploying**, otherwise anyone with the URL can talk to your agent. The web chat and Telegram chat are separate conversations but share the same brain and scheduler.

## Setup

1. Create a Telegram bot with [@BotFather](https://t.me/BotFather) → get `TELEGRAM_BOT_TOKEN`
2. Get an Anthropic API key at [platform.claude.com](https://platform.claude.com) → `ANTHROPIC_API_KEY`
3. Install and run:

```bash
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN=...
export ANTHROPIC_API_KEY=...
python agent.py
```

Or put the two variables in a `.env` file (loaded automatically).

## Deploy

The `Procfile` (`web: python agent.py`) works on Railway/Heroku-style platforms; the `web` process type gets a public URL for the console (on Railway, click "Generate Domain" in service Settings → Networking). Set the two environment variables in the platform dashboard. Note: SQLite (`memory.db`) is stored on local disk — mount a persistent volume (Railway: Volumes) or memory and scheduled jobs will reset on redeploy.

## Configuration

| Env var | Default | Purpose |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | — (required) | Telegram bot token |
| `ANTHROPIC_API_KEY` | — (required) | Anthropic API key |
| `CLAUDE_MODEL` | `claude-opus-4-8` | Model override (e.g. `claude-sonnet-5` for lower cost) |
| `DB_PATH` | `memory.db` | SQLite database location |
| `PORT` | `8080` | Web console port (set automatically by most hosts) |
| `WEB_PASSWORD` | — (open!) | Password for the web console — set this before deploying |

## Notes

- Scheduling times are handled in UTC internally; tell the bot your timezone once ("my timezone is Sydney") and it will store that as a fact and convert for you.
- The agent loop is capped at 12 iterations per turn and scheduled jobs at 5 per poll cycle to keep costs bounded.
- Never paste secrets into the chat — the agent is instructed not to store them, but conversation history is persisted.
