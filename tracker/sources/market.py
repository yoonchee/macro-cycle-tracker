"""Prices — the denominator question. No key required.

Gold is the measuring stick: every currency and index is also stored priced in
gold, because that is the comparison Dalio's framework actually turns on.
"""
import yfinance as yf

TICKERS = {
    "GC=F":    "mkt.gold_usd",     # gold futures, USD/oz
    "^GSPC":   "mkt.spx",
    "^KS11":   "mkt.kospi",
    "^N225":   "mkt.nikkei",
    "KRW=X":   "fx.usdkrw",
    "JPY=X":   "fx.usdjpy",
    "CNY=X":   "fx.usdcny",
    "EURUSD=X":"fx.eurusd",
    "DX-Y.NYB":"fx.dxy",
    "BTC-USD": "mkt.btc_usd",
}


def fetch_all(period="5y"):
    out = []
    data = yf.download(list(TICKERS), period=period, interval="1d",
                       progress=False, auto_adjust=False, group_by="ticker")
    for tic, name in TICKERS.items():
        try:
            col = data[tic]["Close"].dropna()
        except (KeyError, TypeError):
            continue
        out += [{"series": name, "date": d.date().isoformat(),
                 "value": float(v), "source": "yfinance"}
                for d, v in col.items()]
    return out
