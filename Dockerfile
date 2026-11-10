
FROM python:3.12-slim

WORKDIR /app

# Dependències necessàries per a Playwright i Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    libatomic1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

RUN python -m playwright install chromium

COPY . .

CMD ["python", "baseball_scanner_v21_5leagues_all_markets_telegram_bankroll.py"]
