import requests

from core.config import (
    GOOGLE_SHEETS_WEBHOOK
)


def save_to_sheets(data):

    try:

        response = requests.post(
            GOOGLE_SHEETS_WEBHOOK,
            json=data,
            timeout=20
        )

        print(
            f"GOOGLE SHEETS -> {response.status_code}",
            flush=True
        )

    except Exception as e:

        print(
            f"ERROR SHEETS: {e}",
            flush=True
        )