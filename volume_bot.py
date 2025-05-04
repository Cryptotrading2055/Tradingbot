import requests
import time
import threading
import os
from flask import Flask

# --- Configuration ---
PROX_THRESHOLD = 0.002  # 0.2% proximity threshold to EMA

# --- Telegram Setup ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8136212695:AAH3f0HVU3P0hd7jtPN_u0ggCdTC8Cn1vCg")
CHAT_ID = os.getenv("CHAT_ID", "333714345")
BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
HEADERS = {'Content-Type': 'application/json'}

# --- Flask App (for keep-alive on Render) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot działa :)"

# --- Bot Functions ---
def send_telegram_message(message):
    print(f"[DEBUG] Sending Telegram message: {message}", flush=True)
    payload = {"chat_id": CHAT_ID, "text": message}
    try:
        requests.post(BASE_URL, json=payload, headers=HEADERS)
    except Exception as e:
        print(f"[ERROR] Telegram send failed: {e}", flush=True)

# Fetch list of futures symbols
def get_futures_symbols():
    try:
        url = "https://api.bybit.com/v5/market/instruments-info?category=linear"
        data = requests.get(url).json()
        return [s['symbol'] for s in data['result']['list'] if s['symbol'].endswith("USDT")]
    except Exception as e:
        print(f"[ERROR] Fetching symbols failed: {e}", flush=True)
        return []

# Fetch klines for symbol: return list of [close, low, high]
def get_klines(symbol, interval="60", limit=100):
    try:
        url = f"https://api.bybit.com/v5/market/kline?category=linear&symbol={symbol}&interval={interval}&limit={limit}"
        resp = requests.get(url)
        data = resp.json()
        if resp.status_code != 200 or 'result' not in data or 'list' not in data['result']:
            return []
        # Kline array: [timestamp, open, high, low, close, volume, ...]
        return [[float(x[4]), float(x[3]), float(x[2])] for x in data['result']['list']]
    except Exception as e:
        print(f"[ERROR] Fetching klines for {symbol} failed: {e}", flush=True)
        return []

# Calculate EMA
def calculate_ema(arr, period):
    ema = []
    k = 2 / (period + 1)
    for i, price in enumerate(arr):
        if price is None or i < period - 1:
            ema.append(None)
        elif i == period - 1:
            ema.append(sum(arr[:period]) / period)
        else:
            ema.append((price - ema[i-1]) * k + ema[i-1])
    return ema

# Calculate SMA
def calculate_sma(arr, period):
    sma = []
    for i in range(len(arr)):
        if i < period - 1 or arr[i] is None:
            sma.append(None)
        else:
            window = [v for v in arr[i-period+1:i+1] if v is not None]
            sma.append(sum(window) / period if len(window) == period else None)
    return sma

# Self-ping thread

def self_ping(port):
    while True:
        try:
            requests.get(f"http://127.0.0.1:{port}/")
            print(f"[DEBUG] Self-ping sent to port {port}", flush=True)
        except Exception as e:
            print(f"[ERROR] Self-ping failed: {e}", flush=True)
        time.sleep(240)

# Main EMA scanning logic
def ema_bot():
    print("[DEBUG] Bot start", flush=True)
    send_telegram_message("✅ Bot EMA działa! Monitoruję EMA50 i EMA100 na 1H i 4H...")
    while True:
        print("[DEBUG] Starting scan cycle", flush=True)
        symbols = get_futures_symbols()
        for label, code in [("1H", "60"), ("4H", "240")]:
            for symbol in symbols:
                klines = get_klines(symbol, interval=code)
                if len(klines) < 100:
                    print(f"[DEBUG] Not enough klines for {symbol} ({label}): {len(klines)}", flush=True)
                    continue
                closes = [k[0] for k in klines]
                low = klines[-1][1]
                high = klines[-1][2]
                last_close = closes[-1]

                ema50_raw = calculate_ema(closes, 50)
                ema100_raw = calculate_ema(closes, 100)
                ema50 = calculate_sma(ema50_raw, 9)
                ema100 = calculate_sma(ema100_raw, 9)
                last_ema50 = ema50[-1]
                last_ema100 = ema100[-1]
                print(f"[DEBUG] {symbol} {label}: close={last_close}, EMA50={last_ema50}, EMA100={last_ema100}, low={low}, high={high}", flush=True)

                # Touch alerts
                if last_ema50 is not None and low <= last_ema50 <= high:
                    send_telegram_message(f"📉 {symbol} dotknął EMA50 ({label})\nEMA50: {last_ema50:.4f}")
                if last_ema100 is not None and low <= last_ema100 <= high:
                    send_telegram_message(f"📉 {symbol} dotknął EMA100 ({label})\nEMA100: {last_ema100:.4f}")

                # Proximity alerts
                if last_ema50 is not None and abs(last_close - last_ema50)/last_ema50 <= PROX_THRESHOLD:
                    send_telegram_message(f"🔎 {symbol} blisko EMA50 ({label}): Close={last_close:.4f}, EMA50={last_ema50:.4f}")
                if last_ema100 is not None and abs(last_close - last_ema100)/last_ema100 <= PROX_THRESHOLD:
                    send_telegram_message(f"🔎 {symbol} blisko EMA100 ({label}): Close={last_close:.4f}, EMA100={last_ema100:.4f}")
        time.sleep(300)

# Entry point
if __name__ == '__main__':
    port = int(os.environ.get("PORT", "10000"))
    # Run flask in background
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=port), daemon=True).start()
    # Run self-ping
    threading.Thread(target=self_ping, args=(port,), daemon=True).start()
    # Run EMA bot
    ema_bot()
