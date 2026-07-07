"""Background autonomy: polls the jobs table and fires scheduled tasks.

Jobs live in SQLite (see memory.py) so they survive restarts. When a job is
due, the agent runs autonomously with the job's prompt and the result is
delivered to the originating Telegram chat.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import brain
import memory

logger = logging.getLogger(__name__)

POLL_SECONDS = 30
MAX_RUNS_PER_CYCLE = 5  # safety valve if a backlog builds up


async def _fire(bot, job: dict) -> None:
    chat_id = job["chat_id"]
    logger.info("Firing scheduled job #%s for chat %s", job["id"], chat_id)
    try:
        prompt = f"[SCHEDULED TASK] {job['prompt']}"
        reply = await brain.run_agent(chat_id, chat_id, prompt)
        if str(chat_id).startswith("web"):
            # Web chats have no push channel; run_agent already saved the
            # exchange to history, which the web UI polls.
            return
        for i in range(0, len(reply), 4000):
            await bot.send_message(chat_id=chat_id, text=reply[i:i + 4000])
    except Exception:
        logger.exception("Scheduled job #%s failed", job["id"])


def _advance(job: dict) -> None:
    """Compute the job's next run, or retire it if it was one-shot."""
    if job["schedule_type"] == "once":
        memory.deactivate_job(job["id"])
    elif job["schedule_type"] == "daily":
        memory.reschedule_job(job["id"], brain._next_daily_run(job["daily_time"]))
    elif job["schedule_type"] == "every":
        next_run = datetime.now(timezone.utc) + timedelta(minutes=job["interval_minutes"])
        memory.reschedule_job(job["id"], next_run.isoformat())


async def scheduler_loop(app) -> None:
    logger.info("Scheduler running (poll every %ss)", POLL_SECONDS)
    while True:
        try:
            due = memory.due_jobs()[:MAX_RUNS_PER_CYCLE]
            for job in due:
                # Advance BEFORE running so a crash mid-task can't fire it in a loop.
                _advance(job)
                await _fire(app.bot, job)
        except Exception:
            logger.exception("Scheduler cycle failed")
        await asyncio.sleep(POLL_SECONDS)
