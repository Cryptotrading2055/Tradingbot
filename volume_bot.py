import requests
import time
import threading
from flask import Flask

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
    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }
    try:
        requests.post(BASE_URL, json=payload, headers=HEADERS)
    except:
        pass

def get_futures_symbols():
    try:
        url = "https://api.bybit.com/v5/market/instruments-info?category=linear"
        response = requests.get(url)
        data = response.json()
        return [s['symbol'] for s in data['result']['list'] if s['symbol'].endswith("USDT")]
    except:
        return []

def get_klines(symbol, interval="60", limit=100):
    try:
        url = f"https://api.bybit.com/v5/market/kline?category=linear&symbol={symbol}&interval={interval}&limit={limit}"
        response = requests.get(url)
        data = response.json()
        if response.status_code != 200 or 'result' not in data or 'list' not in data['result']:
            return []
        # Bybit kline fields: [timestamp, open, high, low, close, volume, ...]
        return [[float(x[4]), float(x[3]), float(x[2])] for x in data['result']['list']]  # [close, low, high]
    except:
        return []

def calculate_ema(data, period):
    ema = []
    k = 2 / (period + 1)
    for i in range(len(data)):
        if data[i] is None:
            ema.append(None)
        elif i < period - 1:
            ema.append(None)
        elif i == period - 1:
            sma = sum(data[:period]) / period
            ema.append(sma)
        else:
            prev = ema[i-1]
            ema.append((data[i] - prev) * k + prev)
    return ema

# Added SMA smoothing for EMA (smoothing_length = 9)
def calculate_sma(data, period):
    sma = []
    for i in range(len(data)):
        if i < period - 1 or data[i] is None:
            sma.append(None)
        else:
            window = [v for v in data[i-period+1:i+1] if v is not None]
            if len(window) < period:
                sma.append(None)
            else:
                sma.append(sum(window) / period)
    return sma

def ema_bot():
    send_telegram_message("✅ Bot EMA działa na Render! Monitoruję EMA50 i EMA100 (z SMA9) na 1H i 4H...")

    while True:
        try:
            symbols = get_futures_symbols()
            for interval_label, interval_code in [("1H", "60"), ("4H", "240")]:
                for symbol in symbols:
                    klines = get_klines(symbol, interval=interval_code)
                    if len(klines) < 100:
                        continue

                    closes = [k[0] for k in klines]
                    low = klines[-1][1]
                    high = klines[-1][2]

                    # raw EMA
                    ema50_raw = calculate_ema(closes, 50)
                    ema100_raw = calculate_ema(closes, 100)
                    # SMA smoothing line length 9
                    ema50 = calculate_sma(ema50_raw, 9)
                    ema100 = calculate_sma(ema100_raw, 9)

                    # last values
                    last_ema50 = ema50[-1]
                    last_ema100 = ema100[-1]

                    # check only if values exist
                    if last_ema50 is not None and low <= last_ema50 <= high:
                        send_telegram_message(f"📉 {symbol} dotknął EMA50 (z SMA9) ({interval_label})\nEMA50: {round(last_ema50, 4)}")

                    if last_ema100 is not None and low <= last_ema100 <= high:
                        send_telegram_message(f"📉 {symbol} dotknął EMA100 (z SMA9) ({interval_label})\nEMA100: {round(last_ema100, 4)}")

            time.sleep(300)

        except Exception as e:
            send_telegram_message(f"❌ Błąd EMA bota: {str(e)}")
            time.sleep(300)

if __name__ == '__main__':
    threading.Thread(target=ema_bot).start()
    app.run(host='0.0.0.0', port=10000)