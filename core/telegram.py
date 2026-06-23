import requests

from core.config import (
    BOT_TOKEN,
    CHAT_ID
)


def send_telegram(message):

    url = (
        f"https://api.telegram.org/bot"
        f"{BOT_TOKEN}/sendMessage"
    )

    data = {
        "chat_id": CHAT_ID,
        "text": message
    }

    try:

        requests.post(
            url,
            data=data,
            timeout=20
        )

    except Exception as e:

        print(
            f"ERROR TELEGRAM: {e}",
            flush=True
        )