from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import json
import yfinance as yf
import pandas as pd

def tv_ema(series, period):
    alpha = 2 / (period + 1)
    result = [float(series.iloc[0])]
    for i in range(1, len(series)):
        result.append(float(series.iloc[i]) * alpha + result[-1] * (1 - alpha))
    return pd.Series(result, index=series.index)

def tv_rsi(series, period):
    delta  = series.diff()
    gain   = delta.clip(lower=0)
    loss   = -delta.clip(upper=0)
    gains  = [0.0] * len(series)
    losses = [0.0] * len(series)
    gains[period]  = float(gain.iloc[1:period+1].mean())
    losses[period] = float(loss.iloc[1:period+1].mean())
    for i in range(period + 1, len(series)):
        gains[i]  = (gains[i-1]  * (period-1) + float(gain.iloc[i]))  / period
        losses[i] = (losses[i-1] * (period-1) + float(loss.iloc[i])) / period
    gains  = pd.Series(gains,  index=series.index)
    losses = pd.Series(losses, index=series.index)
    rs = gains / losses.replace(0, 1e-10)
    return 100 - (100 / (1 + rs))

def calc_bx(df):
    closes = df["Close"].squeeze()
    return tv_rsi(tv_ema(closes, 5) - tv_ema(closes, 20), 5) - 50

def calc_fvb(df, period=33):
    ohlc4  = (df["Open"].squeeze() + df["High"].squeeze() +
              df["Low"].squeeze()  + df["Close"].squeeze()) / 4
    middle = ohlc4.rolling(window=period).mean()
    return df["Low"].squeeze() > middle

def get_bx(ticker):
    df_w = yf.download(ticker, period="max", interval="1wk",
                       progress=False, auto_adjust=False, threads=False)
    df_m = yf.download(ticker, period="max", interval="1mo",
                       progress=False, auto_adjust=False, threads=False)

    if df_w is None or len(df_w) < 40: return None
    if df_m is None or len(df_m) < 5:  return None

    bx_w  = calc_bx(df_w)
    fvb_w = calc_fvb(df_w)
    bx_m  = calc_bx(df_m)
    fvb_m = calc_fvb(df_m)

    wbx_cur    = float(bx_w.iloc[-1])
    wbx_prev   = float(bx_w.iloc[-2])
    mbx_cur    = float(bx_m.iloc[-1])
    mbx_prev   = float(bx_m.iloc[-2])
    fvb_w_cur  = bool(fvb_w.iloc[-1])
    fvb_w_prev = bool(fvb_w.iloc[-2])
    fvb_m_cur  = bool(fvb_m.iloc[-1])
    price      = float(df_w["Close"].squeeze().iloc[-1])

    return {
        "ticker":           ticker,
        "wbx":              round(wbx_cur, 2),
        "wbx_prev":         round(wbx_prev, 2),
        "mbx":              round(mbx_cur, 2),
        "mbx_prev":         round(mbx_prev, 2),
        "fvb_w":            fvb_w_cur,
        "fvb_w_prev":       fvb_w_prev,
        "fvb_m":            fvb_m_cur,
        "wbx_green":        wbx_cur > 0,
        "fvb_green":        fvb_w_cur,
        "mbx_green":        mbx_cur > 0,
        "mbx_flipped_red":  mbx_cur < 0 and mbx_prev >= 0,
        "price":            round(price, 2),
    }

class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        ticker = params.get("ticker", [None])[0]

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        if not ticker:
            self.wfile.write(json.dumps({"error": "No ticker provided"}).encode())
            return
        try:
            result = get_bx(ticker.upper())
            if result:
                self.wfile.write(json.dumps(result).encode())
            else:
                self.wfile.write(json.dumps({"error": "Not enough data"}).encode())
        except Exception as e:
            self.wfile.write(json.dumps({"error": str(e)}).encode())

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.end_headers()
