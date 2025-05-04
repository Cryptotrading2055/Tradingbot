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
    payload = {"chat_id": CHAT_ID, "text": message}
    print(f"[DEBUG] Sending Telegram message: {message}")
    try:
        requests.post(BASE_URL, json=payload, headers=HEADERS)
    except Exception as e:
        print(f"[ERROR] Telegram send failed: {e}")

# Fetch symbols
def get_futures_symbols():
    try:
        url = "https://api.bybit.com/v5/market/instruments-info?category=linear"
        data = requests.get(url).json()
        return [s['symbol'] for s in data['result']['list'] if s['symbol'].endswith("USDT")]
    except Exception as e:
        print(f"[ERROR] Fetching symbols failed: {e}")
        return []

# Fetch klines: [close, low, high]
def get_klines(symbol, interval="1", limit=100):
    try:
        url = f"https://api.bybit.com/v5/market/kline?category=linear&symbol={symbol}&interval={interval}&limit={limit}"
        resp = requests.get(url)
        data = resp.json()
        if resp.status_code != 200 or 'result' not in data or 'list' not in data['result']:
            return []
        # Kline format: [timestamp, open, high, low, close, volume, ...]
        return [[float(x[4]), float(x[3]), float(x[2])] for x in data['result']['list']]
    except Exception as e:
        print(f"[ERROR] Fetching klines for {symbol} failed: {e}")
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

# Main bot logic
def ema_bot():
    send_telegram_message("✅ Bot EMA działa! Test 1m: Monitoruję EMA50 i EMA100 na 1-minutowych świecach...")
    while True:
        symbols = get_futures_symbols()
        # Test tylko interwału 1m
        for label, code in [("1m","1")]:
            for symbol in symbols:
                klines = get_klines(symbol, interval=code)
                if len(klines) < 100:
                    continue
                closes = [k[0] for k in klines]
                low = klines[-1][1]
                high = klines[-1][2]
                last_close = closes[-1]
                prev_close = closes[-2] if len(closes) >= 2 else None

                # Raw and smoothed EMAs
                ema50_raw = calculate_ema(closes, 50)
                ema100_raw = calculate_ema(closes, 100)
                ema50 = calculate_sma(ema50_raw, 9)
                ema100 = calculate_sma(ema100_raw, 9)
                last_ema50 = ema50[-1]
                last_ema100 = ema100[-1]
                prev_ema50 = ema50[-2] if len(ema50) >= 2 else None
                prev_ema100 = ema100[-2] if len(ema100) >= 2 else None

                # Debug logging
                print(f"[DEBUG] {symbol} {label}: prev_close={prev_close}, last_close={last_close}, prev_ema50={prev_ema50}, last_ema50={last_ema50}, low={low}, high={high}")

                # Touch detection
                if last_ema50 is not None and low <= last_ema50 <= high:
                    send_telegram_message(f"📉 {symbol} dotknął EMA50 (z SMA9) ({label})\nEMA50: {last_ema50:.4f}")
                if last_ema100 is not None and low <= last_ema100 <= high:
                    send_telegram_message(f"📉 {symbol} dotknął EMA100 (z SMA9) ({label})\nEMA100: {last_ema100:.4f}")

                # Cross detection
                if prev_ema50 is not None and prev_close is not None and last_close is not None:
                    if prev_close < prev_ema50 <= last_close:
                        send_telegram_message(f"🚀 {symbol} przecięcie EMA50 wzrostowo ({label})\nClose: {last_close:.4f}, EMA50: {last_ema50:.4f}")
                    if prev_close > prev_ema50 >= last_close:
                        send_telegram_message(f"🔻 {symbol} przecięcie EMA50 spadkowo ({label})\nClose: {last_close:.4f}, EMA50: {last_ema50:.4f}")

                # Proximity detection
                if last_ema50 is not None and abs(last_close - last_ema50)/last_ema50 <= PROX_THRESHOLD:
                    send_telegram_message(f"🔎 {symbol} blisko EMA50 ({label}): Close={last_close:.4f}, EMA50={last_ema50:.4f}")
                if last_ema100 is not None and abs(last_close - last_ema100)/last_ema100 <= PROX_THRESHOLD:
                    send_telegram_message(f"🔎 {symbol} blisko EMA100 ({label}): Close={last_close:.4f}, EMA100={last_ema100:.4f}")
        time.sleep(60)

if __name__ == '__main__':
    threading.Thread(target=ema_bot, daemon=True).start()
    port = int(os.environ.get("PORT", "10000"))
    app.run(host='0.0.0.0', port=port)
