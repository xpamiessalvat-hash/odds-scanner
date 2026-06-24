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

    print(f"BOT_TOKEN={BOT_TOKEN}", flush=True)
    print(f"URL={url}", flush=True)
    
    try:
        response = requests.post(
            url,
            data=data,
            timeout=20
        )

        print(
            f"TELEGRAM -> {response.status_code} {response.text}",
            flush=True
        )

    except Exception as e:
        print(
            f"ERROR TELEGRAM: {e}",
            flush=True
        )
