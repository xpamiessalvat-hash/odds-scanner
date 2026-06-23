import os

# -------------------------
# Fitxers
# -------------------------

CSV_FILE = "moviments.csv"
STEAM_FILE = "steam.csv"
CLV_FILE = "closing_lines.csv"

# -------------------------
# Telegram
# -------------------------

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# -------------------------
# API
# -------------------------

BASE_URL = "https://guest.api.arcadia.pinnacle.com/0.1"
# -------------------------
# Google Sheets
# -------------------------

GOOGLE_SHEETS_WEBHOOK = (
    "https://script.google.com/macros/s/AKfycbxwdYpjhLe2vcgOiBwXZkLYERh7c4CmvZmwBH5ziqf7C_0rH_LScxg9LTiRyFj4yg6q/exec"
)