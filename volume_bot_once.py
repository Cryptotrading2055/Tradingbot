#!/usr/bin/env python3
import os
import requests
import time
from dotenv import load_dotenv

load_dotenv()

# --- Config ---
PROX_THRESHOLD = 0.002    # 0.2%
SYMBOLS_ENV = os.getenv("SYMBOLS", "")
# jeśli env SYMBOLS pusty, fetch z API
USE_API = SYMBOLS_ENV == ""
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
HEADERS = {'Content-Type': 'application/json'}

def send_msg(txt):
    requests.post(BASE_URL, json={"chat_id": CHAT_ID, "text": txt}, headers=HEADERS, timeout=10)

def get_symbols():
    if not USE_API:
        return [s.strip() for s in SYMBOLS_ENV.split(",") if s.strip()]
    # próba v5
    try:
        r = requests.get("https://api.bybit.com/v5/market/instruments-info?category=linear", timeout=10)
        if r.status_code == 200:
            data = r.json().get("result", {}).get("list", [])
            syms = [s["symbol"] for s in data if s["symbol"].endswith("USDT")]
            if syms:
                return syms
    except: pass
    # fallback v2
    try:
        r2 = requests.get("https://api.bybit.com/v2/public/symbols", timeout=10)
        if r2.status_code == 200:
            data2 = r2.json().get("result", [])
            return [it["name"] for it in data2 if it["name"].endswith("USDT")]
    except: pass
    # ostatecznie env
    return [s.strip() for s in SYMBOLS_ENV.split(",") if s.strip()]

def get_klines(sym, interval="60", limit=100):
    try:
        r = requests.get(f"https://api.bybit.com/v5/market/kline?category=linear&symbol={sym}&interval={interval}&limit={limit}", timeout=10)
        if r.status_code == 200:
            lst = r.json().get("result", {}).get("list", [])
            return [[float(x[4]), float(x[3]), float(x[2])] for x in lst]
    except: pass
    return []

def ema(data, period):
    k = 2/(period+1); res=[]
    for i, p in enumerate(data):
        if i < period-1: res.append(None)
        elif i == period-1: res.append(sum(data[:period])/period)
        else: res.append((p-res[-1])*k+res[-1])
    return res

def sma(data, period):
    res=[]
    for i in range(len(data)):
        if i < period-1 or data[i] is None:
            res.append(None)
        else:
            w = [v for v in data[i-period+1:i+1] if v is not None]
            res.append(sum(w)/period if len(w)==period else None)
    return res

def main():
    syms = get_symbols()
    send_msg(f"✅ EMA-bot run: scanning {len(syms)} symbols")
    for label, code in [("1H","60"), ("4H","240")]:
        for s in syms:
            kl = get_klines(s, code)
            if len(kl) < 100: continue
            closes = [c[0] for c in kl]
            low, high = kl[-1][1], kl[-1][2]
            e50 = sma(ema(closes,50),9)[-1]
            e100= sma(ema(closes,100),9)[-1]
            last = closes[-1]
            if e50 and low<=e50<=high:
                send_msg(f"📉 {s} hit EMA50 ({label}): {e50:.4f}")
            if e100 and low<=e100<=high:
                send_msg(f"📉 {s} hit EMA100 ({label}): {e100:.4f}")
            if e50 and abs(last-e50)/e50<=PROX_THRESHOLD:
                send_msg(f"🔎 {s} near EMA50 ({label})")
            if e100 and abs(last-e100)/e100<=PROX_THRESHOLD:
                send_msg(f"🔎 {s} near EMA100 ({label})")

if __name__=="__main__":
    main()

