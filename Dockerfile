FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

RUN python -m playwright install chromium

COPY . .

CMD ["python", "baseball_scanner_v21_5leagues_all_markets_telegram_bankroll.py"]
