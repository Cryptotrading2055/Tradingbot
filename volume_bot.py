import requests
import time
import threading
import os
from flask import Flask

# --- Configuration ---
PROX_THRESHOLD = 0.002  # 0.2% proximity threshold to EMA
DEFAULT_SYMBOLS = os.getenv("SYMBOLS", "BTCUSDT,ETHUSDT,LINKUSDT,TRUMPUSDT")  # fallback if API blocked

# --- Telegram Setup ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "8136212695:AAH3f0HVU3P0hd7jtPN_u0ggCdTC8Cn1vCg")
CHAT_ID = os.getenv("CHAT_ID", "333714345")
BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
HEADERS = {'Content-Type': 'application/json'}

# --- Flask App (for keep-alive) ---
app = Flask(__name__)
@app.route('/')
def home():
    return "Bot działa :)"

# --- Bot Functions ---
def send_telegram_message(message):
    print(f"[DEBUG] Sending Telegram message: {message}", flush=True)
    payload = {"chat_id": CHAT_ID, "text": message}
    try:
        requests.post(BASE_URL, json=payload, headers=HEADERS, timeout=10)
    except Exception as e:
        print(f"[ERROR] Telegram send failed: {e}", flush=True)

# Fetch futures symbols with API fallback and user-defined fallback
def get_futures_symbols():
    symbols = []
    # 1) Try v5 API
    v5_url = "https://api.bybit.com/v5/market/instruments-info?category=linear"
    try:
        resp = requests.get(v5_url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            symbols = [s['symbol'] for s in data.get('result', {}).get('list', []) if s.get('symbol', '').endswith('USDT')]
            if symbols:
                print(f"[DEBUG] Fetched {len(symbols)} symbols via v5 API", flush=True)
                return symbols
            else:
                print("[DEBUG] v5 API returned empty, falling back", flush=True)
        else:
            print(f"[ERROR] v5 instruments-info status {resp.status_code}", flush=True)
    except Exception as e:
        print(f"[ERROR] v5 instruments-info failed: {e}", flush=True)
    # 2) Try v2 API
    v2_url = "https://api.bybit.com/v2/public/symbols"
    try:
        resp2 = requests.get(v2_url, timeout=10)
        if resp2.status_code == 200:
            data2 = resp2.json()
            symbols = [item['name'] for item in data2.get('result', []) if item.get('name', '').endswith('USDT')]
            if symbols:
                print(f"[DEBUG] Fetched {len(symbols)} symbols via v2 API", flush=True)
                return symbols
            else:
                print("[DEBUG] v2 API returned empty, falling back to DEFAULT_SYMBOLS", flush=True)
        else:
            print(f"[ERROR] v2 symbols status {resp2.status_code}", flush=True)
    except Exception as e:
        print(f"[ERROR] v2 symbols request failed: {e}", flush=True)
    # 3) Fallback to user-defined list
    fallback = [s.strip() for s in DEFAULT_SYMBOLS.split(',') if s.strip()]
    print(f"[DEBUG] Using DEFAULT_SYMBOLS fallback: {fallback}", flush=True)
    return fallback

# Fetch klines: return list [close, low, high]
def get_klines(symbol, interval="60", limit=100):
    url = f"https://api.bybit.com/v5/market/kline?category=linear&symbol={symbol}&interval={interval}&limit={limit}"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            lst = data.get('result', {}).get('list', [])
            klines = []
            for x in lst:
                try:
                    close, low, high = float(x[4]), float(x[3]), float(x[2])
                    klines.append([close, low, high])
                except:
                    pass
            return klines
        else:
            print(f"[ERROR] kline {symbol} status {resp.status_code}", flush=True)
    except Exception as e:
        print(f"[ERROR] kline request {symbol} failed: {e}", flush=True)
    return []

# Helpers for EMA and SMA
def calculate_ema(arr, period):
    ema=[]; k=2/(period+1)
    for i, price in enumerate(arr):
        if price is None or i<period-1:
            ema.append(None)
        elif i==period-1:
            ema.append(sum(arr[:period])/period)
        else:
            ema.append((price-ema[i-1])*k+ema[i-1])
    return ema

def calculate_sma(arr, period):
    sma=[]
    for i in range(len(arr)):
        if i<period-1 or arr[i] is None:
            sma.append(None)
        else:
            window=[v for v in arr[i-period+1:i+1] if v is not None]
            sma.append(sum(window)/period if len(window)==period else None)
    return sma

# Self-ping thread to keep dyno awake
def self_ping(port):
    while True:
        try:
            requests.get(f"http://127.0.0.1:{port}/", timeout=5)
            print(f"[DEBUG] Self-ping sent to port {port}", flush=True)
        except Exception as e:
            print(f"[ERROR] Self-ping failed: {e}", flush=True)
        time.sleep(240)

# Main loop: EMA scan and alerts
def ema_bot():
    print("[DEBUG] Bot start", flush=True)
    send_telegram_message("✅ Bot EMA działa! Monitoruję EMA50 i EMA100 na 1H i 4H...")
    while True:
        print("[DEBUG] Starting scan cycle", flush=True)
        symbols = get_futures_symbols()
        print(f"[DEBUG] Symbols to scan ({len(symbols)}): {symbols}", flush=True)
        for label, code in [("1H","60"),("4H","240")]:
            for symbol in symbols:
                klines = get_klines(symbol, interval=code)
                if len(klines)<100:
                    continue
                closes = [k[0] for k in klines]
                low, high = klines[-1][1], klines[-1][2]
                last_close = closes[-1]
                ema50_raw = calculate_ema(closes,50)
                ema100_raw = calculate_ema(closes,100)
                ema50 = calculate_sma(ema50_raw,9)
                ema100 = calculate_sma(ema100_raw,9)
                last_ema50, last_ema100 = ema50[-1], ema100[-1]
                print(f"[DEBUG] {symbol} {label}: close={last_close}, EMA50={last_ema50}, EMA100={last_ema100}, low={low}, high={high}", flush=True)
                if last_ema50 is not None and low<=last_ema50<=high:
                    send_telegram_message(f"📉 {symbol} dotknął EMA50 ({label})\nEMA50: {last_ema50:.4f}")
                if last_ema100 is not None and low<=last_ema100<=high:
                    send_telegram_message(f"📉 {symbol} dotknął EMA100 ({label})\nEMA100: {last_ema100:.4f}")
                if last_ema50 is not None and abs(last_close-last_ema50)/last_ema50<=PROX_THRESHOLD:
                    send_telegram_message(f"🔎 {symbol} blisko EMA50 ({label}): Close={last_close:.4f}, EMA50={last_ema50:.4f}")
                if last_ema100 is not None and abs(last_close-last_ema100)/last_ema100<=PROX_THRESHOLD:
                    send_telegram_message(f"🔎 {symbol} blisko EMA100 ({label}): Close={last_close:.4f}, EMA100={last_ema100:.4f}")
        time.sleep(300)

if __name__=='__main__':
    port=int(os.environ.get("PORT","10000"))
    threading.Thread(target=lambda: app.run(host='0.0.0.0',port=port),daemon=True).start()
    threading.Thread(target=self_ping,args=(port,),daemon=True).start()
    ema_bot()
