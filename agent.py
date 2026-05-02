import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

async def handle_message(update, context):
    user_message = update.message.text

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "You are a helpful assistant helping the user achieve their goals."},
            {"role": "user", "content": user_message}
        ]
    )

    reply = response.choices[0].message.content

    await update.message.reply_text(reply)