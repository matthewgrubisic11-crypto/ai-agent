"""The agent brain: Claude with an agentic tool-use loop.

Each call to run_agent() gives Claude the conversation history plus a tool belt
(web search, long-term memory, self-scheduling) and loops — Claude calls tools,
we execute them, results go back — until Claude produces a final answer.
"""

import json
import logging
import os
from datetime import datetime, timedelta, timezone

from anthropic import AsyncAnthropic

import memory

logger = logging.getLogger(__name__)

MODEL = os.getenv("CLAUDE_MODEL", "claude-opus-4-8")
MAX_ITERATIONS = 12          # hard cap on the agent loop, keeps cost bounded
HISTORY_LIMIT = 20           # recent messages loaded per conversation

client = AsyncAnthropic()

SYSTEM_CORE = """You are a personal agentic assistant that lives in Telegram. \
You are the user's always-on agent: you answer questions, research things on the \
web, remember important information permanently, and schedule tasks to run \
yourself later.

Capabilities and how to use them:
- web_search: use it whenever current information would change the answer \
(news, prices, weather, recent events, version-specific facts). Don't answer \
from memory when freshness matters.
- remember_fact: whenever the user shares something durable about themselves \
(name, timezone, preferences, projects, goals, recurring context), store it. \
Don't ask permission for obviously useful facts; just save them and move on. \
Never store passwords, API keys, or other secrets.
- forget_fact: remove a stored fact when the user corrects it or asks you to.
- schedule_task / list_scheduled_tasks / cancel_scheduled_task: when the user \
wants something done later or on a repeating basis ("every morning...", \
"remind me at..."), schedule it. All scheduling times are in UTC — if you know \
the user's timezone from their facts, convert their local time to UTC before \
scheduling, and confirm back in their local time.

When a message begins with [SCHEDULED TASK] you are running autonomously — the \
user did not just message you. Do the task and report the result concisely; \
don't ask clarifying questions.

Style: be clear, direct, and conversational. This is a chat app — keep replies \
tight and skip preamble. Use plain text, not markdown tables."""


# ---------- custom tool definitions ----------

CUSTOM_TOOLS = [
    {
        "name": "remember_fact",
        "description": (
            "Store a durable fact about the user in permanent memory. Call this "
            "whenever the user shares lasting information: their name, timezone, "
            "preferences, projects, goals, or recurring context. The fact is "
            "injected into your context in every future conversation."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "fact": {"type": "string", "description": "The fact to remember, phrased as a standalone statement, e.g. 'User's timezone is Australia/Sydney'."}
            },
            "required": ["fact"],
        },
    },
    {
        "name": "forget_fact",
        "description": "Delete a stored fact by its id (ids are shown in your memory context). Call when the user corrects outdated info or asks you to forget something.",
        "input_schema": {
            "type": "object",
            "properties": {
                "fact_id": {"type": "integer", "description": "The id of the fact to delete."}
            },
            "required": ["fact_id"],
        },
    },
    {
        "name": "schedule_task",
        "description": (
            "Schedule a task for yourself to run later, once or repeatedly. When it "
            "fires, you will be invoked autonomously with the given prompt and your "
            "answer is sent to the user. Use for reminders, recurring briefings, "
            "check-ins. All times are UTC."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "The instruction your future self will execute, self-contained, e.g. 'Search for the top 3 AI news stories today and summarize them in 5 bullet points.'",
                },
                "schedule_type": {
                    "type": "string",
                    "enum": ["once", "daily", "every"],
                    "description": "'once' = single run at run_at; 'daily' = every day at daily_time; 'every' = repeating every interval_minutes.",
                },
                "run_at": {"type": "string", "description": "For 'once': ISO 8601 UTC datetime, e.g. '2026-07-08T08:00:00'."},
                "daily_time": {"type": "string", "description": "For 'daily': UTC time as HH:MM, e.g. '22:00'."},
                "interval_minutes": {"type": "integer", "description": "For 'every': the repeat interval in minutes (minimum 15)."},
            },
            "required": ["prompt", "schedule_type"],
        },
    },
    {
        "name": "list_scheduled_tasks",
        "description": "List the user's active scheduled tasks with their ids and next run times (UTC).",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "cancel_scheduled_task",
        "description": "Cancel an active scheduled task by its id.",
        "input_schema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "integer", "description": "The id of the task to cancel."}
            },
            "required": ["task_id"],
        },
    },
]

SERVER_TOOLS = [
    {"type": "web_search_20260209", "name": "web_search", "max_uses": 5},
]

TOOLS = SERVER_TOOLS + CUSTOM_TOOLS


# ---------- custom tool execution ----------

def _next_daily_run(daily_time: str) -> str:
    hh, mm = (int(x) for x in daily_time.split(":"))
    now = datetime.now(timezone.utc)
    candidate = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    return candidate.isoformat()


def execute_tool(name: str, tool_input: dict, user_id, chat_id) -> str:
    if name == "remember_fact":
        fact_id = memory.add_fact(user_id, tool_input["fact"])
        return f"Saved as fact #{fact_id}."

    if name == "forget_fact":
        ok = memory.delete_fact(user_id, tool_input["fact_id"])
        return "Deleted." if ok else "No fact with that id."

    if name == "schedule_task":
        stype = tool_input["schedule_type"]
        prompt = tool_input["prompt"]
        if stype == "once":
            run_at = tool_input.get("run_at")
            if not run_at:
                return "Error: 'once' requires run_at (ISO UTC datetime)."
            dt = datetime.fromisoformat(run_at)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt <= datetime.now(timezone.utc):
                return "Error: run_at is in the past."
            job_id = memory.add_job(chat_id, prompt, "once", dt.isoformat())
            return f"Scheduled task #{job_id} to run once at {dt.isoformat()} UTC."
        if stype == "daily":
            daily_time = tool_input.get("daily_time")
            if not daily_time:
                return "Error: 'daily' requires daily_time (HH:MM UTC)."
            next_run = _next_daily_run(daily_time)
            job_id = memory.add_job(chat_id, prompt, "daily", next_run, daily_time=daily_time)
            return f"Scheduled task #{job_id} daily at {daily_time} UTC (next run {next_run})."
        if stype == "every":
            minutes = tool_input.get("interval_minutes")
            if not minutes or minutes < 15:
                return "Error: 'every' requires interval_minutes >= 15."
            next_run = (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()
            job_id = memory.add_job(chat_id, prompt, "every", next_run, interval_minutes=minutes)
            return f"Scheduled task #{job_id} every {minutes} minutes (next run {next_run} UTC)."
        return f"Error: unknown schedule_type '{stype}'."

    if name == "list_scheduled_tasks":
        jobs = memory.list_jobs(chat_id)
        if not jobs:
            return "No active scheduled tasks."
        return json.dumps(jobs)

    if name == "cancel_scheduled_task":
        ok = memory.cancel_job(chat_id, tool_input["task_id"])
        return "Cancelled." if ok else "No active task with that id."

    return f"Error: unknown tool '{name}'."


# ---------- system prompt assembly ----------

def build_system(user_id) -> list[dict]:
    facts = memory.list_facts(user_id)
    facts_text = (
        "\n".join(f"- (#{f['id']}) {f['fact']}" for f in facts)
        if facts else "(nothing stored yet)"
    )
    dynamic = (
        f"Current UTC time: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}\n\n"
        f"Permanent memory — facts you have stored about this user:\n{facts_text}"
    )
    # Stable block first and cached; volatile block (time, facts) after it.
    return [
        {"type": "text", "text": SYSTEM_CORE, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": dynamic},
    ]


# ---------- the agent loop ----------

async def run_agent(user_id, chat_id, user_text: str) -> str:
    """Run one full agentic turn and return the final reply text."""
    messages = memory.load_recent_messages(user_id, HISTORY_LIMIT)
    messages.append({"role": "user", "content": user_text})

    response = None
    for _ in range(MAX_ITERATIONS):
        response = await client.messages.create(
            model=MODEL,
            max_tokens=8000,
            thinking={"type": "adaptive"},
            system=build_system(user_id),
            tools=TOOLS,
            messages=messages,
        )

        if response.stop_reason == "tool_use":
            messages.append({"role": "assistant", "content": response.content})
            results = []
            for block in response.content:
                if block.type == "tool_use":
                    logger.info("Tool call: %s %s", block.name, block.input)
                    try:
                        result = execute_tool(block.name, block.input, user_id, chat_id)
                    except Exception as e:
                        logger.exception("Tool %s failed", block.name)
                        results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": f"Error: {e}",
                            "is_error": True,
                        })
                        continue
                    results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })
            messages.append({"role": "user", "content": results})
            continue

        if response.stop_reason == "pause_turn":
            # Server-side tool (web search) paused mid-loop; re-send to resume.
            messages.append({"role": "assistant", "content": response.content})
            continue

        break

    if response is None:
        return "Something went wrong — no response from the model."

    if response.stop_reason == "refusal":
        return "I can't help with that one."

    reply = "\n".join(b.text for b in response.content if b.type == "text").strip()
    if not reply:
        return "I hit my step limit on that task without a final answer — try narrowing it down."

    memory.save_message(user_id, "user", user_text)
    memory.save_message(user_id, "assistant", reply)
    return reply
