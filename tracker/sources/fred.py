"""FRED — Fed balance sheet and the series Treasury doesn't publish itself.

Free key: https://fredaccount.stlouisfed.org/apikeys
Without a key this module is skipped; everything in Gauges 1 and 2 still works
because those come from Treasury directly.
"""
import time

import requests
from ..config import FRED_API_KEY, UA, TIMEOUT

BASE = "https://api.stlouisfed.org/fred/series/observations"

# FRED's gateway throws the odd 502 mid-run, and one bad series used to skip
# every series in the module, Gauge 3 included. Retry 5xx and network errors
# with backoff of 2s, 6s, 18s; a 4xx (a retired series id, a bad key) is an
# answer, not an outage, and is never retried.
FRED_RETRIES = 4

SERIES = {
    # Gauge 3 — monetization
    "WALCL":   "us.fed.balance_sheet",      # total Fed assets, weekly, $mn
    "WSHOSHO": "us.fed.soma_treasuries",    # SOMA Treasury holdings
    "RESPPLLOPNWW": "us.fed.deferred_asset",# the Fed's own losses — the tell
    # Japan is not read here. Dalio's Q7 argument is about the shape of the JGB
    # curve, not one point on it, so it comes from MOF — see sources/japan.py.
    # Context
    "CPIAUCSL": "us.cpi",
    "GDP":      "us.gdp",
    "T10YIE":   "us.breakeven.10y",
}

# --- TIC: who actually holds the debt ---------------------------------------
# Treasury International Capital, relayed by FRED. Monthly, ~2 months in
# arrears. This is the demand side of Gauge 2: total foreign demand can hold up
# while its *composition* rotates from price-insensitive official reserve
# managers to private money that has to be paid to show up.
TIC_AGGREGATE = {
    "FORTREASPOS99990": "us.tic.official",     # foreign official — central banks, SWFs
    "FORTREASPOS99991": "us.tic.private",      # foreign non-official
    "FORTREASPOS99996": "us.tic.total",        # grand total
}

# The twenty largest holders, ~80% of the total. TIC attributes holdings to the
# CUSTODIAN's country, not the beneficial owner, so a large number here is not
# proof of large domestic ownership — see the grouping in gauges.py. The
# official/private split is published only in aggregate, never per country.
TIC_COUNTRIES = {
    "42609": ("japan",       "Japan"),
    "13005": ("uk",          "United Kingdom"),
    "41408": ("china",       "China"),
    "10251": ("belgium",     "Belgium"),
    "29998": ("canada",      "Canada"),
    "36137": ("cayman",      "Cayman Islands"),
    "11703": ("luxembourg",  "Luxembourg"),
    "10804": ("france",      "France"),
    "11401": ("ireland",     "Ireland"),
    "46302": ("taiwan",      "Taiwan"),
    "12688": ("switzerland", "Switzerland"),
    "46019": ("singapore",   "Singapore"),
    "42005": ("hong_kong",   "Hong Kong"),
    "12203": ("norway",      "Norway"),
    "42102": ("india",       "India"),
    "30309": ("brazil",      "Brazil"),
    "45608": ("saudi",       "Saudi Arabia"),
    "43001": ("korea",       "Korea"),
    "46604": ("uae",         "UAE"),
    "11002": ("germany",     "Germany"),
}

TIC_NAMES = {slug: name for slug, name in TIC_COUNTRIES.values()}
TIC_SERIES = dict(TIC_AGGREGATE)
TIC_SERIES.update({f"FORTREASPOS{code}": f"us.tic.country.{slug}"
                   for code, (slug, _) in TIC_COUNTRIES.items()})


def fetch_all(start="2015-01-01"):
    if not FRED_API_KEY:
        raise RuntimeError("FRED_API_KEY not set — skipping FRED (Gauge 3 will be stale)")
    out = []
    for fid, name in {**SERIES, **TIC_SERIES}.items():
        for o in _observations(fid, start):
            if o["value"] != ".":
                out.append({"series": name, "date": o["date"], "value": o["value"],
                            "source": "fred"})
    return out


def _observations(fid, start):
    for attempt in range(FRED_RETRIES):
        try:
            r = requests.get(BASE, headers=UA, timeout=TIMEOUT, params={
                "series_id": fid, "api_key": FRED_API_KEY, "file_type": "json",
                "observation_start": start,
            })
            r.raise_for_status()
            return r.json().get("observations", [])
        except requests.RequestException as exc:
            status = getattr(exc.response, "status_code", None)
            if attempt == FRED_RETRIES - 1 or (status and status < 500):
                raise
            time.sleep(2 * 3 ** attempt)
