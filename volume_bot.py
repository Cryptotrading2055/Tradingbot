import requests
import time
import threading
import os
from flask import Flask

# --- Configuration ---
PROX_THRESHOLD = 0.002  # 0.2% proximity threshold to EMA
DEFAULT_SYMBOLS = os.getenv("SYMBOLS", "BTCUSDT,ETHUSDT,LINKUSDT,TRUMPUSDT")

# --- Telegram Setup ---
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
HEADERS = {'Content-Type': 'application/json'}

# --- Flask for keep-alive ---
app = Flask(__name__)
@app.route('/')
def home():
    return "Bot działa :)"

# --- Utility Functions ---
def send_telegram_message(message):
    print(f"[DEBUG] Sending Telegram message: {message}", flush=True)
    payload = {"chat_id": CHAT_ID, "text": message}
    try:
        requests.post(BASE_URL, json=payload, headers=HEADERS, timeout=10)
    except Exception as e:
        print(f"[ERROR] Telegram send failed: {e}", flush=True)

# Fetch futures symbols
def get_futures_symbols():
    # try v5
    try:
        resp = requests.get("https://api.bybit.com/v5/market/instruments-info?category=linear", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            syms = [s['symbol'] for s in data.get('result', {}).get('list', []) if s.get('symbol','').endswith('USDT')]
            if syms:
                print(f"[DEBUG] Fetched {len(syms)} symbols via v5 API", flush=True)
                return syms
    except Exception as e:
        print(f"[ERROR] v5 symbol fetch failed: {e}", flush=True)
    # try v2
    try:
        resp2 = requests.get("https://api.bybit.com/v2/public/symbols", timeout=10)
        if resp2.status_code == 200:
            data2 = resp2.json()
            syms2 = [item['name'] for item in data2.get('result', []) if item.get('name','').endswith('USDT')]
            if syms2:
                print(f"[DEBUG] Fetched {len(syms2)} symbols via v2 API", flush=True)
                return syms2
    except Exception as e:
        print(f"[ERROR] v2 symbol fetch failed: {e}", flush=True)
    # fallback
    fallback = [s.strip() for s in DEFAULT_SYMBOLS.split(',')]
    print(f"[DEBUG] Using DEFAULT_SYMBOLS fallback: {fallback}", flush=True)
    return fallback

# Fetch klines with v5 -> v2 fallback
def get_klines(symbol, interval="60", limit=100):
    # v5
    try:
        url5 = f"https://api.bybit.com/v5/market/kline?category=linear&symbol={symbol}&interval={interval}&limit={limit}"
        r5 = requests.get(url5, timeout=10)
        if r5.status_code == 200:
            d5 = r5.json().get('result', {}).get('list', [])
            kl5 = [[float(x[4]), float(x[3]), float(x[2])] for x in d5]
            if kl5:
                return kl5
    except Exception as e:
        print(f"[ERROR] v5 kline {symbol} failed: {e}", flush=True)
    # fallback v2
    try:
        url2 = f"https://api.bybit.com/v2/public/kline/list?symbol={symbol}&interval={interval}&limit={limit}"
        r2 = requests.get(url2, timeout=10)
        if r2.status_code == 200:
            data2 = r2.json().get('result', [])
            kl2 = [[float(x['close']), float(x['low']), float(x['high'])] for x in data2]
            if kl2:
                print(f"[DEBUG] Fetched {len(kl2)} klines via v2 for {symbol}", flush=True)
                return kl2
            else:
                print(f"[DEBUG] v2 klines empty for {symbol}", flush=True)
        else:
            print(f"[ERROR] v2 kline {symbol} status {r2.status_code}", flush=True)
    except Exception as e:
        print(f"[ERROR] v2 kline {symbol} failed: {e}", flush=True)
    return []

# EMA & SMA helpers
def calculate_ema(arr, period):
    ema=[]; k=2/(period+1)
    for i,p in enumerate(arr):
        if p is None or i<period-1:
            ema.append(None)
        elif i==period-1:
            ema.append(sum(arr[:period])/period)
        else:
            ema.append((p-ema[i-1])*k+ema[i-1])
    return ema

def calculate_sma(arr, period):
    sma=[]
    for i,p in enumerate(arr):
        if p is None or i<period-1:
            sma.append(None)
        else:
            win=[v for v in arr[i-period+1:i+1] if v is not None]
            sma.append(sum(win)/period if len(win)==period else None)
    return sma

# keep-alive self-ping
def self_ping(port):
    while True:
        try:
            requests.get(f"http://127.0.0.1:{port}/", timeout=5)
            print(f"[DEBUG] Self-ping sent to port {port}", flush=True)
        except Exception as e:
            print(f"[ERROR] Self-ping failed: {e}", flush=True)
        time.sleep(240)

# Main loop
def ema_bot():
    print("[DEBUG] Bot start", flush=True)
    send_telegram_message("✅ Bot EMA działa! Monitoruję EMA50 i EMA100 na 1H i 4H...")
    while True:
        print("[DEBUG] Starting scan cycle", flush=True)
        syms = get_futures_symbols()
        print(f"[DEBUG] Symbols to scan ({len(syms)}): {syms}", flush=True)
        for label,code in [("1H","60"),("4H","240")]:
            for sym in syms:
                kls = get_klines(sym, interval=code)
                if len(kls)<100:
                    continue
                closes=[c[0] for c in kls]; low=kls[-1][1]; high=kls[-1][2]; last=closes[-1]
                e50=calculate_sma(calculate_ema(closes,50),9)[-1]
                e100=calculate_sma(calculate_ema(closes,100),9)[-1]
                print(f"[DEBUG] {sym} {label}: close={last}, EMA50={e50}, EMA100={e100}, low={low}, high={high}", flush=True)
                if e50 and low<=e50<=high:
                    send_telegram_message(f"📉 {sym} dotknął EMA50 ({label})\nEMA50: {e50:.4f}")
                if e100 and low<=e100<=high:
                    send_telegram_message(f"📉 {sym} dotknął EMA100 ({label})\nEMA100: {e100:.4f}")
                if e50 and abs(last-e50)/e50<=PROX_THRESHOLD:
                    send_telegram_message(f"🔎 {sym} blisko EMA50 ({label}): Close={last:.4f}, EMA50={e50:.4f}")
                if e100 and abs(last-e100)/e100<=PROX_THRESHOLD:
                    send_telegram_message(f"🔎 {sym} blisko EMA100 ({label}): Close={last:.4f}, EMA100={e100:.4f}")
        time.sleep(300)

if __name__=='__main__':
    p=int(os.environ.get("PORT","10000"))
    threading.Thread(target=lambda: app.run(host='0.0.0.0',port=p),daemon=True).start()
    threading.Thread(target=self_ping,args=(p,),daemon=True).start()
    ema_bot()
