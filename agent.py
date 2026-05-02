import os
from datetime import datetime
from telegram import Update
from telegram.ext import ApplicationBuilder, MessageHandler, filters, ContextTypes
from openai import OpenAI

# =========================
# 🔑 SETUP
# =========================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

client = OpenAI(api_key=OPENAI_API_KEY)

# 🧠 Memory per user
user_memory = {}

# =========================
# 🤖 MESSAGE HANDLER
# =========================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.chat_id
    user_message = update.message.text

    # -------------------------
    # 🧠 Create memory if new
    # -------------------------
    if user_id not in user_memory:
        user_memory[user_id] = [
            {
                "role": "system",
                "content": (
                    "You are a smart, practical AI assistant. "
                    "Be clear, helpful, and direct. "
                    "Help the user with ideas, planning, learning, and real-world tasks. "
                    "Avoid generic disclaimers. Be useful."
                )
            }
        ]

    # -------------------------
    # ⚡ REAL-TIME SHORTCUTS
    # -------------------------
    if "time" in user_message.lower():
        now = datetime.now().strftime("%H:%M")
        await update.message.reply_text(f"The current time is {now}")
        return

    # -------------------------
    # 💬 Add user message
    # -------------------------
    user_memory[user_id].append({"role": "user", "content": user_message})

    try:
        # -------------------------
        # 🤖 AI RESPONSE
        # -------------------------
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=user_memory[user_id]
        )

        reply = response.choices[0].message.content

        # Save reply to memory
        user_memory[user_id].append({"role": "assistant", "content": reply})

        # -------------------------
        # 🧠 MEMORY CONTROL (IMPORTANT)
        # Prevent memory getting too big
        # -------------------------
        if len(user_memory[user_id]) > 20:
            user_memory[user_id] = (
                user_memory[user_id][:1] +  # keep system prompt
                user_memory[user_id][-19:]  # keep recent messages
            )

    except Exception as e:
        reply = f"Error: {str(e)}"

    # -------------------------
    # 📤 SEND REPLY
    # -------------------------
    await update.message.reply_text(reply)

# =========================
# 🚀 RUN BOT
# =========================
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()