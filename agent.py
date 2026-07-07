"""Entry point: Telegram interface for the Claude-powered agentic assistant.

Run with: python agent.py
Requires env vars: TELEGRAM_BOT_TOKEN, ANTHROPIC_API_KEY
"""

import asyncio
import logging
import os

from dotenv import load_dotenv
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

load_dotenv()

import brain  # noqa: E402  (imports the Anthropic client, needs env loaded first)
import scheduler  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

WELCOME = (
    "Hey — I'm your personal agent, powered by Claude.\n\n"
    "I can:\n"
    "• Answer anything, searching the web when freshness matters\n"
    "• Remember things about you permanently (just tell me)\n"
    "• Run tasks on a schedule — try: \"every morning at 8am, send me the top AI news\"\n\n"
    "Just talk to me normally."
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(WELCOME)


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    chat_id = update.message.chat_id
    user_text = update.message.text.strip()

    typing = asyncio.create_task(_keep_typing(context, chat_id))
    try:
        reply = await brain.run_agent(chat_id, chat_id, user_text)
    except Exception:
        logger.exception("Agent run failed")
        reply = "Something went wrong on my end. Try again in a moment."
    finally:
        typing.cancel()

    # Telegram caps messages at 4096 chars — chunk long replies.
    for i in range(0, len(reply), 4000):
        await update.message.reply_text(reply[i:i + 4000])


async def _keep_typing(context, chat_id):
    """Keep the typing indicator alive during long agent runs."""
    try:
        while True:
            await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            await asyncio.sleep(5)
    except asyncio.CancelledError:
        pass


async def _post_init(app):
    app.create_task(scheduler.scheduler_loop(app))


def main():
    if not TELEGRAM_TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN is not set")
    if not os.getenv("ANTHROPIC_API_KEY"):
        raise SystemExit("ANTHROPIC_API_KEY is not set")

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(_post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Agent is running (model: %s)...", brain.MODEL)
    app.run_polling()


if __name__ == "__main__":
    main()
