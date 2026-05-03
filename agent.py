import os
import logging
import sqlite3
from datetime import datetime
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from openai import OpenAI

# =========================
# 🔑 KEYS
# =========================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

# =========================
# 🧾 LOGGING
# =========================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# =========================
# 💾 DATABASE (PERMANENT MEMORY)
# =========================
conn = sqlite3.connect("memory.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS memory (
    user_id TEXT,
    role TEXT,
    content TEXT
)
""")
conn.commit()

# =========================
# 🧠 MEMORY FUNCTIONS
# =========================
def save_message(user_id, role, content):
    cursor.execute(
        "INSERT INTO memory (user_id, role, content) VALUES (?, ?, ?)",
        (str(user_id), role, content)
    )
    conn.commit()

def load_memory(user_id):
    cursor.execute(
        "SELECT role, content FROM memory WHERE user_id=? ORDER BY rowid DESC LIMIT 10",
        (str(user_id),)
    )
    rows = cursor.fetchall()
    return [{"role": r[0], "content": r[1]} for r in reversed(rows)]

# =========================
# 🤖 MAIN HANDLER
# =========================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user_id = update.message.chat_id
    user_message = update.message.text.strip()

    # typing indicator
    await context.bot.send_chat_action(chat_id=user_id, action=ChatAction.TYPING)

    # ⚡ real-time time
    if "time" in user_message.lower():
        now = datetime.now().strftime("%H:%M")
        await update.message.reply_text(f"The current time is {now}")
        return

    # 🧠 load memory
    memory = load_memory(user_id)

    # add system prompt
    memory.insert(0, {
        "role": "system",
        "content": "You are a smart, helpful AI assistant. Be clear and conversational."
    })

    # save user message
    save_message(user_id, "user", user_message)

    try:
        # 🤖 AI call
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=memory,
            temperature=0.7
        )

        reply = response.choices[0].message.content.strip()

        if not reply:
            return

        # save AI reply
        save_message(user_id, "assistant", reply)

        # send reply
        await update.message.reply_text(reply)

    except Exception as e:
        logger.error(f"Error: {e}")
        await update.message.reply_text("Something went wrong. Try again.")

# =========================
# 🚀 RUN BOT
# =========================
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()