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
    except:
        pass

# Fetch symbol list
def get_futures_symbols():
    try:
        url = "https://api.bybit.com/v5/market/instruments-info?category=linear"
        resp = requests.get(url)
        data = resp.json()
        return [s['symbol'] for s in data['result']['list'] if s['symbol'].endswith("USDT")]
    except:
        return []

# Fetch klines: return list of [close, low, high]
def get_klines(symbol, interval="60", limit=100):
    try:
        url = f"https://api.bybit.com/v5/market/kline?category=linear&symbol={symbol}&interval={interval}&limit={limit}"
        resp = requests.get(url)
        data = resp.json()
        if resp.status_code != 200 or 'result' not in data or 'list' not in data['result']:
            return []
        # fields: [timestamp, open, high, low, close, volume, ...]
        return [[float(x[4]), float(x[3]), float(x[2])] for x in data['result']['list']]
    except:
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
    send_telegram_message("✅ Bot EMA działa! Monitoruję EMA50 i EMA100 na 1H i 4H...")
    while True:
        try:
            symbols = get_futures_symbols()
            for label, code in [("1H","60"), ("4H","240")]:
                for symbol in symbols:
                    klines = get_klines(symbol, interval=code)
                    if len(klines) < 100:
                        continue
                    closes = [k[0] for k in klines]
                    low = klines[-1][1]
                    high = klines[-1][2]
                    last_close = closes[-1]

                    # Raw and smoothed EMAs
                    ema50_raw = calculate_ema(closes, 50)
                    ema100_raw = calculate_ema(closes, 100)
                    ema50 = calculate_sma(ema50_raw, 9)
                    ema100 = calculate_sma(ema100_raw, 9)
                    last_ema50 = ema50[-1]
                    last_ema100 = ema100[-1]

                    # 1) Touch detection
                    if last_ema50 is not None and low <= last_ema50 <= high:
                        send_telegram_message(f"📉 {symbol} dotknął EMA50 (z SMA9) ({label})\nEMA50: {last_ema50:.4f}")
                    if last_ema100 is not None and low <= last_ema100 <= high:
                        send_telegram_message(f"📉 {symbol} dotknął EMA100 (z SMA9) ({label})\nEMA100: {last_ema100:.4f}")

                    # 2) Proximity detection
                    if last_ema50 is not None and abs(last_close - last_ema50)/last_ema50 <= PROX_THRESHOLD:
                        send_telegram_message(f"🔎 {symbol} blisko EMA50 ({label}): Close={last_close:.4f}, EMA50={last_ema50:.4f}")
                    if last_ema100 is not None and abs(last_close - last_ema100)/last_ema100 <= PROX_THRESHOLD:
                        send_telegram_message(f"🔎 {symbol} blisko EMA100 ({label}): Close={last_close:.4f}, EMA100={last_ema100:.4f}")

            time.sleep(300)
        except Exception as e:
            send_telegram_message(f"❌ Błąd EMA bota: {e}")
            time.sleep(300)

if __name__ == '__main__':
    threading.Thread(target=ema_bot).start()
    app.run(host='0.0.0.0', port=10000)
