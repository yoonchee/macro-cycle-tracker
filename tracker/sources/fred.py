"""FRED — Fed balance sheet and the series Treasury doesn't publish itself.

Free key: https://fredaccount.stlouisfed.org/apikeys
Without a key this module is skipped; everything in Gauges 1 and 2 still works
because those come from Treasury directly.
"""
import requests
from ..config import FRED_API_KEY, UA, TIMEOUT

BASE = "https://api.stlouisfed.org/fred/series/observations"

SERIES = {
    # Gauge 3 — monetization
    "WALCL":   "us.fed.balance_sheet",      # total Fed assets, weekly, $mn
    "WSHOSHO": "us.fed.soma_treasuries",    # SOMA Treasury holdings
    "RESPPLLOPNWW": "us.fed.deferred_asset",# the Fed's own losses — the tell
    # Japan — the template already running (Dalio's Q7)
    "IRLTLT01JPM156N": "jp.jgb10",          # 10-year JGB, monthly
    # Context
    "CPIAUCSL": "us.cpi",
    "GDP":      "us.gdp",
    "T10YIE":   "us.breakeven.10y",
}


def fetch_all(start="2015-01-01"):
    if not FRED_API_KEY:
        raise RuntimeError("FRED_API_KEY not set — skipping FRED (Gauge 3 will be stale)")
    out = []
    for fid, name in SERIES.items():
        r = requests.get(BASE, headers=UA, timeout=TIMEOUT, params={
            "series_id": fid, "api_key": FRED_API_KEY, "file_type": "json",
            "observation_start": start,
        })
        r.raise_for_status()
        for o in r.json().get("observations", []):
            if o["value"] != ".":
                out.append({"series": name, "date": o["date"], "value": o["value"],
                            "source": "fred"})
    return out
