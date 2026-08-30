"""Build data/snapshot.json from the SQLite store.

This is the bridge between `refresh.py` (fills the store) and `build.py` (renders
the page). Everything the store can answer is derived here; anything no wired
API serves is read from data/manual.json and merged on top.

    python -m tracker.snapshot            # write data/snapshot.json
    python -m tracker.snapshot --dry-run  # print it instead

A series that is missing or stale does not silently become zero: `pick` raises,
and `main` reports which key failed. A dashboard rendered from a partial refresh
is worse than one that fails loudly.

The snapshot carries paths, not just points. Every gauge on the page is a claim
about a *direction*, and a single reading cannot be argued with. Two windows,
because they answer different questions: time-series paths run three years, wide
enough to contain the 2023 rate shock; curve comparisons are annual snapshots at
today, a year back and two years back.
"""
import argparse
import datetime as dt
import json

from . import store
from .config import SNAPSHOT, DATA
from .sources.fred import TIC_NAMES   # constant table, no network

MANUAL = DATA / "manual.json"

WINDOW_YEARS = 3        # history carried onto the page as paths
FED_WINDOW_YEARS = 5    # two extra, so the 2022 QT peak stays in frame
TIC_WINDOW_YEARS = 5    # TIC is monthly and slow-moving; five years shows the rotation

# Curves are read as annual snapshots: today, a year back, two years back. Three
# lines, two years of span — a path drawn through more dates than that stops
# being a curve comparison and becomes a mess of crossings.
CURVE_LOOKBACK = (("now", 0), ("yr_ago", 1), ("yr2_ago", 2))
CURVE_YEARS = max(back for _, back in CURVE_LOOKBACK)

# How stale a series may be before we refuse to build. Fiscal and ECOS releases
# lag by design; market data should be within days.
MAX_AGE_DAYS = {
    "mkt.": 7, "fx.": 7, "us.ust.": 7, "us.debt.": 10,
    "us.fed.": 21, "us.receipts.": 75, "us.outlays.": 75, "us.deficit.": 75,
    "us.interest.": 75, "kr.housing.": 120, "kr.": 200, "jp.": 10,
    "us.tic.": 120,     # TIC publishes ~2 months in arrears
}

UST_TENORS = ("m1", "y2", "y10", "y30")
JGB_TENORS = ("y1", "y2", "y10", "y30")


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


def years_ago(series, ref, n=1):
    date, value = store.as_of_years_ago(series, ref, n)
    if value is None:
        raise KeyError(f"{series}: no observation near {ref} minus {n} year(s)")
    return date, value


def _since(ref, years):
    y, m, d = (int(x) for x in str(ref)[:10].split("-"))
    try:
        return dt.date(y - years, m, d).isoformat()
    except ValueError:
        return dt.date(y - years, m, d - 1).isoformat()


def curve(prefix, tenors, ref=None):
    """A yield curve today, a year back and two years back.

    Three dates rather than two because the twelve-month comparison alone cannot
    distinguish a curve that is still repricing from one that repriced earlier
    and has been flat since — and those imply opposite things about demand.
    """
    ref = ref or pick(f"{prefix}.{tenors[-1]}")[0]
    out = {}
    for label, back in CURVE_LOOKBACK:
        row = {}
        for tag in tenors:
            if back == 0:
                d0, v0 = pick(f"{prefix}.{tag}", on_or_before=ref)
            else:
                d0, v0 = years_ago(f"{prefix}.{tag}", ref, back)
            row["date"], row[tag] = d0, v0
        out[label] = row
    return out


def _fiscal_months(record_date):
    """Months of FY data a 31-July FYTD figure represents (FY starts 1 October)."""
    d = dt.date.fromisoformat(record_date)
    return (d.month - 10) % 12 + 1


def _rebased(points):
    """Index path rescaled so the first observation is 100."""
    base = points[0][1]
    return [(d, v / base * 100) for d, v in points]


def build():
    # --- rates ---------------------------------------------------------------
    ref, y30 = pick("us.ust.y30")
    ust = curve("us.ust", UST_TENORS, ref)
    yields_now, yields_ago = ust["now"], ust["yr_ago"]
    since = _since(ref, WINDOW_YEARS)

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
    # WALCL is weekly. The page reads it monthly: at this horizon the weekly
    # print is noise, and the question Gauge 3 asks — has the balance sheet
    # stopped shrinking — is a question about the slope of the last two years.
    fdate, fed = pick("us.fed.balance_sheet")
    hist = store.series("us.fed.balance_sheet")
    prior = hist[-2][1] if len(hist) > 1 else fed
    peak_date, peak = max(hist, key=lambda r: r[1])
    fed_monthly = store.monthly("us.fed.balance_sheet", since=_since(fdate, FED_WINDOW_YEARS))
    _, fed_yr_ago = years_ago("us.fed.balance_sheet", fdate, 1)

    # --- market --------------------------------------------------------------
    gdate, gold = pick("mkt.gold_usd")
    _, gold0 = years_ago("mkt.gold_usd", gdate)
    market = {"gold_usd_oz": gold, "gold_usd_oz_yr_ago": gold0, "gold_date": gdate}
    for key, series in (("spx", "mkt.spx"), ("kospi", "mkt.kospi")):
        d, v = pick(series)
        _, v0 = years_ago(series, d)
        market[key] = v
        market[f"{key}_yoy_pct"] = (v / v0 - 1) * 100

    fx_now, fx_ago = {}, {}
    for code, series, invert in (("KRW", "fx.usdkrw", False), ("JPY", "fx.usdjpy", False),
                                 ("CNY", "fx.usdcny", False), ("EUR", "fx.eurusd", True)):
        d, v = pick(series)
        _, v0 = years_ago(series, d)
        fx_now[code] = 1 / v if invert else v
        fx_ago[code] = 1 / v0 if invert else v0
    market["fx_now"], market["fx_yr_ago"] = fx_now, fx_ago

    # --- japan ---------------------------------------------------------------
    jdate = pick("jp.jgb.y10")[0]
    jgb = curve("jp.jgb", JGB_TENORS, jdate)

    # --- who holds the debt (TIC) --------------------------------------------
    # The demand side of Gauge 2. Total foreign demand can rise while the
    # composition rotates out of official reserve managers, and only the second
    # of those is a statement about price-insensitive buyers.
    tdate, official = pick("us.tic.official")
    _, private = pick("us.tic.private", on_or_before=tdate)
    _, tic_total = pick("us.tic.total", on_or_before=tdate)
    tic_since = _since(tdate, TIC_WINDOW_YEARS)
    off_hist = store.series("us.tic.official", since=tic_since)
    priv_hist = store.series("us.tic.private", since=tic_since)
    tot_hist = store.series("us.tic.total", since=tic_since)
    _, off_yr = years_ago("us.tic.official", tdate, 1)
    _, tot_yr = years_ago("us.tic.total", tdate, 1)

    countries = []
    for slug, name in TIC_NAMES.items():
        series = f"us.tic.country.{slug}"
        points = store.series(series, since=tic_since)
        if len(points) < 2:
            raise KeyError(f"{series}: nothing in the last {TIC_WINDOW_YEARS} years")
        base, latest_v = points[0][1], points[-1][1]
        countries.append({"slug": slug, "name": name,
                          "base": base, "latest": latest_v,
                          "change": latest_v - base,
                          "change_pct": (latest_v / base - 1) * 100,
                          "share_pct": latest_v / tic_total * 100})
    countries.sort(key=lambda c: -c["latest"])

    tic = {
        "date": tdate,
        "window": [off_hist[0][0], tdate],
        "window_years": TIC_WINDOW_YEARS,
        "official": official, "private": private, "total": tic_total,
        "official_share_pct": official / tic_total * 100,
        "official_share_pct_yr_ago": off_yr / tot_yr * 100,
        "official_chg_12m": official - off_yr,
        "official_chg_12m_pct": (official / off_yr - 1) * 100,
        "official_series": [list(r) for r in off_hist],
        "private_series": [list(r) for r in priv_hist],
        "total_series": [list(r) for r in tot_hist],
        "official_chg_window": official - off_hist[0][1],
        "private_chg_window": private - priv_hist[0][1],
        "total_chg_window": tic_total - tot_hist[0][1],
        "countries": countries,
        "countries_share_pct": sum(c["latest"] for c in countries) / tic_total * 100,
    }

    # --- korea ---------------------------------------------------------------
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

    kr_since = _since(kr["fixed_share_date"], WINDOW_YEARS)
    _, share0 = years_ago("kr.mortgage.fixed_share", kr["fixed_share_date"])
    share_hist = store.series("kr.mortgage.fixed_share", since=kr_since)
    peak_share_date, peak_share = max(share_hist, key=lambda r: r[1])
    # 가계신용 is quarterly and 신규취급 고정비중 is monthly; they share an axis of
    # time, not of units, so both paths are carried and build.py scales them
    # against their own axes.
    credit_hist = store.series("kr.household_credit", since=kr_since)
    kr.update({
        "fixed_share_yr_ago": share0,
        "fixed_share_peak": peak_share, "fixed_share_peak_date": peak_share_date,
        "fixed_premium_pp": kr["mortgage_fixed"] - kr["mortgage_floating"],
        "fixed_share_series": [list(r) for r in share_hist],
        "household_credit_series": [list(r) for r in credit_hist],
        "household_credit_chg_pct": (credit_hist[-1][1] / credit_hist[0][1] - 1) * 100,
    })

    # 한국부동산원 monthly indices, rebased so four different base months can be
    # read on one axis. The comparison is the point: 매매 against 전세 against
    # 월세 says whether a price move is being paid for out of rent or out of
    # leverage, and the 실거래 index says whether the survey is keeping up with
    # what buyers actually transacted at.
    hdate = pick("kr.housing.seoul_sale")[0]
    h_since = _since(hdate, WINDOW_YEARS)
    housing = {"date": hdate, "series": {}, "chg_pct": {}, "level": {}}
    for key, series in (("real", "kr.housing.seoul_real"),
                        ("sale", "kr.housing.seoul_sale"),
                        ("jeonse", "kr.housing.seoul_jeonse"),
                        ("wolse", "kr.housing.seoul_wolse")):
        points = store.series(series, since=h_since)
        if not points:
            raise KeyError(f"{series}: nothing in the last {WINDOW_YEARS} years")
        rebased = _rebased(points)
        housing["series"][key] = [list(r) for r in rebased]
        housing["chg_pct"][key] = rebased[-1][1] - 100
        housing["level"][key] = points[-1][1]
    housing["window"] = [housing["series"]["sale"][0][0], hdate]
    # Deliberately a gap in percentage points, not a 전세가율. These indices carry
    # a common base month, so their ratio is a relative reading and would be
    # misread as the ~50% 전세-to-price level that 전세가율 actually means.
    housing["jeonse_lag_pp"] = housing["chg_pct"]["sale"] - housing["chg_pct"]["jeonse"]
    housing["wolse_lag_pp"] = housing["chg_pct"]["jeonse"] - housing["chg_pct"]["wolse"]
    housing["survey_gap_pp"] = housing["chg_pct"]["real"] - housing["chg_pct"]["sale"]
    kr["housing"] = housing

    snap = {
        "as_of": ref,
        "generated": dt.date.today().isoformat(),
        "window_years": WINDOW_YEARS,
        "curve_years": CURVE_YEARS,
        "us_fiscal": {
            "fytd_months": _fiscal_months(idate),
            "fytd_receipts": receipts, "fytd_outlays": outlays,
            "fytd_deficit": abs(deficit),
            "fytd_interest_public": interest,
            "debt_total": debt_total, "debt_held_public": debt_public,
            "debt_date": ddate,
            "avg_rate_series": [list(r) for r in avg_rate_series],
        },
        "yields": {"now": yields_now, "yr_ago": yields_ago, "yr2_ago": ust["yr2_ago"],
                   "recent_30y_high": {"date": hi_date, "y30": hi},
                   "since": since},
        "fed": {"balance_sheet_usd_mn": fed, "prior_week_usd_mn": prior,
                "date": fdate, "peak_usd_mn": peak, "peak_date": peak_date,
                "yr_ago_usd_mn": fed_yr_ago,
                "monthly": [list(r) for r in fed_monthly]},
        "market": market,
        "tic": tic,
        "asia": {
            "japan": {"yields": jgb, "jgb10": jgb["now"]["y10"],
                      "jgb10_chg_12m": jgb["now"]["y10"] - jgb["yr_ago"]["y10"],
                      "jgb30_chg_12m": jgb["now"]["y30"] - jgb["yr_ago"]["y30"],
                      "date": jdate},
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
