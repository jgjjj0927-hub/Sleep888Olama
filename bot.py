
import json
import requests
import logging
from pathlib import Path
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)

from config import (
    BOT_TOKEN,
    OLLAMA_URL,
    OLLAMA_MODEL,
    SYSTEM_PROMPT
)

logging.basicConfig(level=logging.INFO)

MEMORY_DIR = Path("memory")
MEMORY_DIR.mkdir(exist_ok=True)

histories = {}


def get_history(user_id):
    if user_id not in histories:
        path = MEMORY_DIR / f"{user_id}.json"

        if path.exists():
            histories[user_id] = json.loads(
                path.read_text(encoding="utf-8")
            )
        else:
            histories[user_id] = []

    return histories[user_id]


def save_history(user_id):
    path = MEMORY_DIR / f"{user_id}.json"
    path.write_text(
        json.dumps(
            histories[user_id],
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )


def ask_ollama(user_id, text):
    history = get_history(user_id)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT}
    ]

    messages.extend(history[-10:])
    messages.append({
        "role": "user",
        "content": text
    })

    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        "keep_alive": "30m",
        "options": {
            "temperature": 0.5,
            "num_predict": 300,
            "num_ctx": 2048
        }
    }

    response = requests.post(
        OLLAMA_URL,
        json=payload,
        timeout=180
    )

    response.raise_for_status()

    answer = response.json()["message"]["content"]

    history.extend([
        {"role": "user", "content": text},
        {"role": "assistant", "content": answer}
    ])

    histories[user_id] = history[-20:]
    save_history(user_id)

    return answer


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Здравствуйте, сэр. JARVIS готов к работе."
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    histories[user_id] = []
    save_history(user_id)

    await update.message.reply_text(
        "История диалога очищена, сэр."
    )


async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text

    status = await update.message.reply_text(
        "Обрабатываю запрос, сэр..."
    )

    try:
        answer = ask_ollama(user_id, text)

        # Telegram ограничивает длину одного сообщения
        for i in range(0, len(answer), 4000):
            await update.message.reply_text(answer[i:i + 4000])

        await status.delete()

    except requests.exceptions.ConnectionError:
        await status.edit_text(
            "Не могу подключиться к Ollama. "
            "Проверьте, запущена ли она."
        )

    except Exception as e:
        logging.exception("Ошибка JARVIS")
        await status.edit_text(
            f"Произошла ошибка: {str(e)[:300]}"
        )


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))

    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, chat)
    )

    print("JARVIS Telegram запущен.")
    app.run_polling()


if __name__ == "__main__":
    main()
