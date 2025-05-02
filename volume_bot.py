import requests
import time
import threading
from flask import Flask

# --- Configuration ---
PROX_THRESHOLD = 0.002  # 0.2% proximity threshold to EMA

# --- Telegram Setup ---
TELEGRAM_TOKEN = "8136212695:AAH3f0HVU3P0hd7jtPN_u0ggCdTC8Cn1vCg"
CHAT_ID = "333714345"
BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
HEADERS = {'Content-Type': 'application/json'}

# --- Flask App (for keep-alive on Render) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot działa :)"

# --- Bot Functions ---
def send_telegram_message(message):
    payload = {"chat_id": CHAT_ID, "text": message}
    try:
        requests.post(BASE_URL, json=payload, headers=HEADERS)
    except Exception as e:
        print(f"Error sending Telegram message: {e}")

# Fetch symbol list
def get_futures_symbols():
    try:
        url = "https://api.bybit.com/v5/market/instruments-info?category=linear"
        resp = requests.get(url)
        data = resp.json()
        return [s['symbol'] for s in data['result']['list'] if s['symbol'].endswith("USDT")]
    except Exception as e:
        print(f"Error fetching symbols: {e}")
        return []

# Fetch klines: return list of [close, low, high]
def get_klines(symbol, interval="60", limit=100):
    try:
        url = f"https://api.bybit.com/v5/market/kline?category=linear&symbol={symbol}&interval={interval}&limit={limit}"
        resp = requests.get(url)
        data = resp.json()
        if resp.status_code != 200 or 'result' not in data or 'list' not in data['result']:
            return []
        return [[float(x[4]), float(x[3]), float(x[2])] for x in data['result']['list']]
    except Exception as e:
        print(f"Error fetching klines for {symbol}: {e}")
        return []

# Calculate EMA
def calculate_ema(arr, period):
    ema = []
    k = 2 / (period + 1)
    for i, price in enumerate(arr):
        if price is None or i < period - 1:
            ema.append(None)
        elif i == period - 1:
            sma = sum(arr[:period]) / period
            ema.append(sma)
        else:
            prev = ema[i-1]
            ema.append((price - prev) * k + prev)
    return ema

# Calculate SMA

