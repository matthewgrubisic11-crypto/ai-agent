# Personal Agentic Assistant

A Telegram-based personal agent powered by Claude (`claude-opus-4-8`). Not just a chatbot — an agent with an agentic loop:

- **Tool use** — Claude decides when to act, your code executes, results feed back until the task is done
- **Web search** — answers with current information (server-side tool, no setup)
- **Permanent memory** — stores durable facts about you (name, timezone, preferences, projects) in SQLite and recalls them in every conversation
- **Self-scheduling** — tell it *"every morning at 8am, send me the top AI news"* and it schedules itself; jobs persist across restarts

## Architecture

```
agent.py      Telegram interface (entry point)
brain.py      Claude agent loop + tool definitions/execution
memory.py     SQLite: conversation history, facts, scheduled jobs
scheduler.py  Background loop that fires scheduled tasks autonomously
```

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

The `Procfile` (`worker: python agent.py`) works as-is on Railway/Heroku-style platforms. Set the two environment variables in the platform dashboard. Note: SQLite (`memory.db`) is stored on local disk — mount a persistent volume (Railway: Volumes) or memory and scheduled jobs will reset on redeploy.

## Configuration

| Env var | Default | Purpose |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | — (required) | Telegram bot token |
| `ANTHROPIC_API_KEY` | — (required) | Anthropic API key |
| `CLAUDE_MODEL` | `claude-opus-4-8` | Model override (e.g. `claude-sonnet-5` for lower cost) |
| `DB_PATH` | `memory.db` | SQLite database location |

## Notes

- Scheduling times are handled in UTC internally; tell the bot your timezone once ("my timezone is Sydney") and it will store that as a fact and convert for you.
- The agent loop is capped at 12 iterations per turn and scheduled jobs at 5 per poll cycle to keep costs bounded.
- Never paste secrets into the chat — the agent is instructed not to store them, but conversation history is persisted.
