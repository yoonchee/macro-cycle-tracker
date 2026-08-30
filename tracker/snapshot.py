"""Build data/snapshot.json from the SQLite store.

This is the bridge between `refresh.py` (fills the store) and `build.py` (renders
the page). Everything the store can answer is derived here; the handful of
figures no wired API serves — the 한국부동산원 weekly apartment numbers — are read
from data/manual.json and merged on top.

    python -m tracker.snapshot            # write data/snapshot.json
    python -m tracker.snapshot --dry-run  # print it instead

A series that is missing or stale does not silently become zero: `pick` raises,
and `main` reports which key failed. A dashboard rendered from a partial refresh
is worse than one that fails loudly.
"""
import argparse
import datetime as dt
import json

from . import store
from .config import SNAPSHOT, DATA

MANUAL = DATA / "manual.json"

# How stale a series may be before we refuse to build. Fiscal and ECOS releases
# lag by design; market data should be within days.
MAX_AGE_DAYS = {
    "mkt.": 7, "fx.": 7, "us.ust.": 7, "us.debt.": 10,
    "us.fed.": 21, "us.receipts.": 75, "us.outlays.": 75, "us.deficit.": 75,
    "us.interest.": 75, "kr.": 200, "jp.": 120,
}


def _max_age(series):
    for prefix, days in MAX_AGE_DAYS.items():
        if series.startswith(prefix):
            return days
    return 60


def pick(series, on_or_before=None, required=True):
    """Latest value for a series, with a staleness check."""
    date, value = store.latest(series, on_or_before=on_or_before)
    if value is None:
        if required:
            raise KeyError(f"{series}: no observations in the store")
        return None, None
    if on_or_before is None:
        age = (dt.date.today() - dt.date.fromisoformat(date)).days
        if age > _max_age(series):
            raise KeyError(f"{series}: stale — last observation {date} ({age}d old)")
    return date, value


def year_ago(series, ref):
    date, value = store.as_of_a_year_ago(series, ref)
    if value is None:
        raise KeyError(f"{series}: no observation near {ref} minus one year")
    return date, value


def _fiscal_months(record_date):
    """Months of FY data a 31-July FYTD figure represents (FY starts 1 October)."""
    d = dt.date.fromisoformat(record_date)
    return (d.month - 10) % 12 + 1


def build():
    # --- rates ---------------------------------------------------------------
    ref, y30 = pick("us.ust.y30")
    yields_now = {"date": ref}
    yields_ago = {}
    for tag in ("m1", "y2", "y5", "y10", "y30"):
        _, v = pick(f"us.ust.{tag}", on_or_before=ref)
        yields_now[tag] = v
        d0, v0 = year_ago(f"us.ust.{tag}", ref)
        yields_ago[tag] = v0
        yields_ago["date"] = d0

    # 30-year high over the trailing quarter — context for "eased from"
    recent = store.series("us.ust.y30",
                          since=(dt.date.fromisoformat(ref) - dt.timedelta(days=90)).isoformat())
    hi_date, hi = max(recent, key=lambda r: r[1]) if recent else (ref, y30)

    # --- fiscal --------------------------------------------------------------
    idate, interest = pick("us.interest.fytd_public")
    _, receipts = pick("us.receipts.fytd")
    _, outlays = pick("us.outlays.fytd")
    _, deficit = pick("us.deficit.fytd")
    ddate, debt_total = pick("us.debt.total")
    _, debt_public = pick("us.debt.public", on_or_before=ddate)
    avg_rate_series = store.series("us.debt.avg_rate")[-8:]

    # --- fed -----------------------------------------------------------------
    fdate, fed = pick("us.fed.balance_sheet")
    hist = store.series("us.fed.balance_sheet")
    prior = hist[-2][1] if len(hist) > 1 else fed
    peak_date, peak = max(hist, key=lambda r: r[1])

    # --- market --------------------------------------------------------------
    gdate, gold = pick("mkt.gold_usd")
    _, gold0 = year_ago("mkt.gold_usd", gdate)
    market = {"gold_usd_oz": gold, "gold_usd_oz_yr_ago": gold0, "gold_date": gdate}
    for key, series in (("spx", "mkt.spx"), ("kospi", "mkt.kospi")):
        d, v = pick(series)
        _, v0 = year_ago(series, d)
        market[key] = v
        market[f"{key}_yoy_pct"] = (v / v0 - 1) * 100

    fx_now, fx_ago = {}, {}
    for code, series, invert in (("KRW", "fx.usdkrw", False), ("JPY", "fx.usdjpy", False),
                                 ("CNY", "fx.usdcny", False), ("EUR", "fx.eurusd", True)):
        d, v = pick(series)
        _, v0 = year_ago(series, d)
        fx_now[code] = 1 / v if invert else v
        fx_ago[code] = 1 / v0 if invert else v0
    market["fx_now"], market["fx_yr_ago"] = fx_now, fx_ago

    # --- asia ----------------------------------------------------------------
    jdate, jgb10 = pick("jp.jgb10")
    _, jgb10_0 = year_ago("jp.jgb10", jdate)

    kr = {}
    for key, series in (("base_rate", "kr.base_rate"), ("cpi_index", "kr.cpi"),
                        ("mortgage_rate", "kr.mortgage_rate"),
                        ("mortgage_fixed", "kr.mortgage_rate.fixed"),
                        ("mortgage_floating", "kr.mortgage_rate.floating"),
                        ("fixed_share", "kr.mortgage.fixed_share"),
                        ("household_credit", "kr.household_credit")):
        d, v = pick(series)
        kr[key] = v
        kr[f"{key}_date"] = d
    _, share0 = year_ago("kr.mortgage.fixed_share", kr["fixed_share_date"])
    share_hist = store.series("kr.mortgage.fixed_share")
    peak_share_date, peak_share = max(share_hist, key=lambda r: r[1])
    kr.update({
        "fixed_share_yr_ago": share0,
        "fixed_share_peak": peak_share, "fixed_share_peak_date": peak_share_date,
        "fixed_premium_pp": kr["mortgage_fixed"] - kr["mortgage_floating"],
        "fixed_share_series": [(d, v) for d, v in share_hist if d >= "2024-01-01"],
    })

    snap = {
        "as_of": ref,
        "generated": dt.date.today().isoformat(),
        "us_fiscal": {
            "fytd_months": _fiscal_months(idate),
            "fytd_receipts": receipts, "fytd_outlays": outlays,
            "fytd_deficit": abs(deficit),
            "fytd_interest_public": interest,
            "debt_total": debt_total, "debt_held_public": debt_public,
            "debt_date": ddate,
            "avg_rate_series": [list(r) for r in avg_rate_series],
        },
        "yields": {"now": yields_now, "yr_ago": yields_ago,
                   "recent_30y_high": {"date": hi_date, "y30": hi}},
        "fed": {"balance_sheet_usd_mn": fed, "prior_week_usd_mn": prior,
                "date": fdate, "peak_usd_mn": peak, "peak_date": peak_date},
        "market": market,
        "asia": {
            "japan": {"jgb10": jgb10, "jgb10_chg_12m": jgb10 - jgb10_0, "date": jdate},
            "korea": kr,
        },
    }

    # manual overrides for what no wired API serves yet
    if MANUAL.exists():
        manual = json.loads(MANUAL.read_text())
        snap["asia"]["korea"].update(manual.get("korea_housing", {}))
        snap.setdefault("manual_keys", sorted(manual.get("korea_housing", {})))
    return snap


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", default=str(SNAPSHOT))
    a = ap.parse_args()
    try:
        snap = build()
    except KeyError as exc:
        raise SystemExit(f"snapshot incomplete: {exc}\nRun `python refresh.py` first.")
    text = json.dumps(snap, indent=2, ensure_ascii=False)
    if a.dry_run:
        print(text)
    else:
        open(a.out, "w").write(text + "\n")
        print(f"wrote {a.out}  (as of {snap['as_of']})")


if __name__ == "__main__":
    main()
