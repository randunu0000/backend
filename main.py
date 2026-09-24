from fastapi import FastAPI
import requests
import pandas as pd
import ta

app = FastAPI()

API_KEY = "YOUR_ALPHA_VANTAGE_KEY"  # get free key at https://www.alphavantage.co

pairs = {
    "XAU/USD": ("XAU", "USD"),
    "EUR/USD": ("EUR", "USD"),
    "USD/JPY": ("USD", "JPY")
}

# Fetch 1-minute OHLC data
def fetch_data(base, quote):
    url = f"https://www.alphavantage.co/query?function=FX_INTRADAY&from_symbol={base}&to_symbol={quote}&interval=1min&apikey={API_KEY}"
    r = requests.get(url).json()
    data = r["Time Series FX (1min)"]
    df = pd.DataFrame(data).T
    df = df.rename(columns={
        "1. open":"open","2. high":"high","3. low":"low","4. close":"close"
    }).astype(float)
    return df

# Detect candlestick patterns
def detect_candlestick(latest, prev=None):
    o, h, l, c = latest["open"], latest["high"], latest["low"], latest["close"]

    if (c > o and (o - l) > 2*(c - o)) or (o > c and (c - l) > 2*(o - c)):
        return "Hammer (Bullish Reversal)"
    if prev is not None and c > o and prev["close"] < prev["open"] and (c - o) > (prev["open"] - prev["close"]):
        return "Bullish Engulfing"
    if (h - max(o, c)) > 2*abs(c - o):
        return "Shooting Star (Bearish Reversal)"
    return "Neutral"

# Generate AI signal with multi-confirmation filter
def generate_signal(base, quote, pairname):
    df = fetch_data(base, quote)
    df["rsi"] = ta.momentum.RSIIndicator(df["close"]).rsi()
    df["ema50"] = ta.trend.EMAIndicator(df["close"], window=50).ema_indicator()
    latest = df.iloc[-1]
    prev = df.iloc[-2]

    price = latest["close"]
    rsi = latest["rsi"]
    ema50 = latest["ema50"]
    candle_pattern = detect_candlestick(latest, prev)

    confirmations = 0
    if rsi > 65 or rsi < 35: confirmations += 1
    if (price > ema50 and rsi < 35) or (price < ema50 and rsi > 65): confirmations += 1
    if candle_pattern != "Neutral": confirmations += 1

    # Chart pattern tags (simplified)
    chart_pattern = "Triple Top" if price < ema50 and rsi > 65 else "Double Bottom" if price > ema50 and rsi < 35 else "Consolidation"

    if confirmations >= 3:
        if price < ema50 and rsi > 65 and "Shooting Star" in candle_pattern:
            action = "SELL"
            confidence = 90
            stopLoss = round(price + (15 if pairname=="XAU/USD" else 0.0020), 5)
            tp1 = round(price - (20 if pairname=="XAU/USD" else 0.0020), 5)
            tp2 = round(price - (40 if pairname=="XAU/USD" else 0.0040), 5)
        elif price > ema50 and rsi < 35 and "Hammer" in candle_pattern:
            action = "BUY"
            confidence = 90
            stopLoss = round(price - (15 if pairname=="XAU/USD" else 0.0020), 5)
            tp1 = round(price + (20 if pairname=="XAU/USD" else 0.0020), 5)
            tp2 = round(price + (40 if pairname=="XAU/USD" else 0.0040), 5)
        else:
            action = "HOLD"
            confidence = 60
            stopLoss, tp1, tp2 = None, None, None
    else:
        action = "HOLD"
        confidence = 50
        stopLoss, tp1, tp2 = None, None, None

    return {
        "pair": pairname,
        "price": round(price, 5) if pairname != "XAU/USD" else round(price, 2),
        "pattern": f"{chart_pattern} + {candle_pattern}",
        "action": action,
        "confidence": confidence,
        "lotSize": 0.01,
        "stopLoss": stopLoss,
        "TP1": tp1,
        "TP2": tp2
    }

@app.get("/api/signals")
def get_all_signals():
    results = {}
    for pairname, (base, quote) in pairs.items():
        results[pairname] = generate_signal(base, quote, pairname)
    return results
