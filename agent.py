import os
import logging
from datetime import datetime
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from openai import OpenAI

# =========================
# 🔑 CONFIG
# =========================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not TELEGRAM_TOKEN or not OPENAI_API_KEY:
    raise ValueError("Missing API keys")

client = OpenAI(api_key=OPENAI_API_KEY)

# =========================
# 🧾 LOGGING
# =========================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =========================
# 🧠 MEMORY CONFIG
# =========================
MAX_MEMORY = 15
user_memory = {}

SYSTEM_PROMPT = {
    "role": "system",
    "content": (
        "You are a smart, practical AI assistant. "
        "Be clear, helpful, and concise. "
        "Avoid repeating yourself. Stay conversational."
    )
}

# =========================
# 🧠 MEMORY HELPERS
# =========================
def get_memory(user_id):
    if user_id not in user_memory:
        user_memory[user_id] = [SYSTEM_PROMPT]
    return user_memory[user_id]

def trim_memory(memory):
    if len(memory) > MAX_MEMORY:
        return memory[:1] + memory[-(MAX_MEMORY - 1):]
    return memory

# =========================
# ⚡ REAL-TIME HANDLERS
# =========================
def handle_realtime(message):
    text = message.lower()

    if "time" in text:
        return f"The current time is {datetime.now().strftime('%H:%M')}"

    return None

# =========================
# 🤖 MAIN HANDLER
# =========================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user_id = update.message.chat_id
    user_message = update.message.text.strip()

    # typing indicator (feels faster)
    await context.bot.send_chat_action(chat_id=user_id, action=ChatAction.TYPING)

    # -------------------------
    # ⚡ REAL-TIME SHORTCUT
    # -------------------------
    realtime = handle_realtime(user_message)
    if realtime:
        await update.message.reply_text(realtime)
        return

    memory = get_memory(user_id)

    # -------------------------
    # 💬 ADD USER MESSAGE
    # -------------------------
    memory.append({"role": "user", "content": user_message})

    try:
        # -------------------------
        # 🤖 AI CALL
        # -------------------------
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=memory,
            temperature=0.7,
        )

        reply = response.choices[0].message.content.strip()

        # -------------------------
        # 🧹 CLEAN BAD OUTPUT
        # -------------------------
        if not reply:
            return

        if reply.lower().startswith("hello! how can i assist"):
            return

        # avoid duplicate last reply
        if len(memory) > 1 and memory[-1]["content"] == reply:
            return

        # -------------------------
        # 🧠 SAVE MEMORY
        # -------------------------
        memory.append({"role": "assistant", "content": reply})
        user_memory[user_id] = trim_memory(memory)

        # -------------------------
        # 📤 SEND
        # -------------------------
        await update.message.reply_text(reply)

    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text("Something went wrong. Try again.")

# =========================
# 🚀 RUN
# =========================
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()