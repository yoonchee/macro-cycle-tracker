"""Dalio's three gauges, scored.

The thresholds below are the opinionated part of this repo. They are stated
here, in one place, so they can be argued with — which is the whole point of
writing a framework down as code instead of prose. Change them and the dashboard
changes; the sources do not.

Gauge definitions are from How Countries Go Broke: The Big Cycle (2025):
  1. debt service relative to government revenue
  2. selling of government debt relative to demand for it
  3. central-bank money printing to absorb the shortfall
"""
from dataclasses import dataclass, field

CONTAINED, ELEVATED, SEVERE, CRITICAL = "contained", "elevated", "severe", "critical"
ORDER = [CONTAINED, ELEVATED, SEVERE, CRITICAL]

# --- thresholds -------------------------------------------------------------
# Interest as a share of federal receipts. Dalio's "plaque": the level at which
# debt service starts crowding out committed spending.
INTEREST_TO_REVENUE = [(0.10, CONTAINED), (0.20, ELEVATED), (0.30, SEVERE)]

# Weighted-average rate Treasury pays. Crossing 4% puts interest past ~25% of
# receipts at current revenue with no new borrowing and no rate change.
AVG_RATE_CRITICAL = 4.0

# Gauge 2: the curve. Dalio's marker is rates rising *led by the long end*.
# Tested on two horizons because they answer different questions and, right now,
# answer them differently. Twelve months asks whether the long end is leading
# *today*. Three years asks whether it led across the repricing as a whole — a
# curve that inverted under a hiking cycle and has since bear-steepened will fail
# the first test and pass the second, and only the second is the debt-cycle
# claim. Reporting one without the other is how a marker gets narrated either
# way after the fact.
LONG_END_LEAD_BP = 25       # 30y must outrun the 2y by this much over 12m
LONG_END_LEAD_3Y_BP = 100   # and by this much across the full three years
CURVE_STEEP_BP = 150        # 30y-2y this wide is a duration-demand problem

# Gauge 3: monetization fires when the balance sheet turns up while the deficit
# is still structurally large.
#
# Read as a slope over months, not week over week. The H.4.1 print swings on
# repo and TGA operations, and a one-week test would have called this gauge both
# ways repeatedly through 2026 while the trend did one thing. Dalio's question is
# whether the central bank has *turned*, and a turn is only observable at the
# length of a few months.
MONETIZATION_WINDOW_M = 6     # months of balance-sheet slope to read
MONETIZATION_TURN_PCT = 1.0   # growth over that window that counts as a turn
MONETIZATION_FAST_PCT = 5.0   # ...and as absorbing issuance rather than drifting

DEFICIT_GDP_LARGE = 0.05


@dataclass
class Gauge:
    key: str
    name: str
    status: str
    headline: str
    metrics: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)


def _band(x, table, above=CRITICAL):
    for cut, label in table:
        if x < cut:
            return label
    return above


def _worst(*statuses):
    return max(statuses, key=ORDER.index)


# --- gauge 1 ----------------------------------------------------------------
def gauge_1(s):
    f = s["us_fiscal"]
    ann = 12 / f["fytd_months"]
    receipts = f["fytd_receipts"] * ann
    outlays = f["fytd_outlays"] * ann
    deficit = f["fytd_deficit"] * ann
    interest = f["fytd_interest_public"] * ann
    ratio = interest / receipts
    avg_rate = f["avg_rate_series"][-1][1]
    market_10y = s["yields"]["now"]["y10"]

    status = _band(ratio, INTEREST_TO_REVENUE)
    if avg_rate >= AVG_RATE_CRITICAL:
        status = _worst(status, SEVERE)

    notes = []
    rising = sum(1 for a, b in zip(f["avg_rate_series"], f["avg_rate_series"][1:])
                 if b[1] > a[1])
    if rising >= 4:
        notes.append(
            f"The average rate paid has risen in {rising} of the last "
            f"{len(f['avg_rate_series']) - 1} months, toward a market 10-year of "
            f"{market_10y:.2f}%. The {market_10y - avg_rate:.2f}pp gap is committed "
            "future interest expense, not a forecast.")

    return Gauge("g1", "Debt service relative to revenue", status,
                 f"Interest is {ratio:.1%} of federal revenue.",
                 {"interest_to_receipts": ratio,
                  "debt_to_receipts": f["debt_held_public"] / receipts,
                  "debt_total_to_receipts": f["debt_total"] / receipts,
                  "outlays_to_receipts": outlays / receipts,
                  "receipts": receipts, "outlays": outlays,
                  "deficit": deficit, "interest": interest,
                  "avg_rate": avg_rate, "repricing_gap_pp": market_10y - avg_rate},
                 notes)


# --- gauge 2 ----------------------------------------------------------------
def gauge_2(s):
    y = s["yields"]
    now, ago, ago3 = y["now"], y["yr_ago"], y["yr3_ago"]
    horizon = s.get("window_years", 3)
    d30 = (now["y30"] - ago["y30"]) * 100
    d2 = (now["y2"] - ago["y2"]) * 100
    d30_3y = (now["y30"] - ago3["y30"]) * 100
    d2_3y = (now["y2"] - ago3["y2"]) * 100
    curve = (now["y30"] - now["y2"]) * 100
    curve_ago = (ago["y30"] - ago["y2"]) * 100
    curve_ago3 = (ago3["y30"] - ago3["y2"]) * 100
    long_end_leads = (d30 - d2) >= LONG_END_LEAD_BP
    long_end_leads_3y = (d30_3y - d2_3y) >= LONG_END_LEAD_3Y_BP

    status = ELEVATED if now["y30"] >= 5.0 else CONTAINED
    if long_end_leads and curve >= CURVE_STEEP_BP:
        status = SEVERE
    if now["y30"] >= 6.5 and long_end_leads:
        status = CRITICAL

    notes = []
    if long_end_leads_3y and not long_end_leads:
        notes.append(
            f"Dalio's marker for this gauge is rates rising led by the long end, "
            f"and the answer depends on where you start the clock. Across "
            f"{horizon} years the 30-year rose {d30_3y:+.0f}bp while the 2-year "
            f"{'fell' if d2_3y < 0 else 'rose'} {abs(d2_3y):.0f}bp — the long end "
            f"led by {d30_3y - d2_3y:.0f}bp and the curve went "
            f"{curve_ago3:+.0f}bp -> {curve:+.0f}bp. The marker IS confirmed on "
            f"that horizon. Over the last 12 months it is not: the 30-year rose "
            f"{d30:+.0f}bp against the 2-year's {d2:+.0f}bp and the spread "
            f"narrowed {curve_ago:.0f}bp -> {curve:.0f}bp. The three-year move is "
            f"the debt-cycle claim; the twelve-month move is a hiking cycle "
            f"ending. Both readings are on the chart above so neither can be "
            f"quoted alone.")
    elif not long_end_leads:
        notes.append(
            f"Dalio's marker for this gauge is rates rising led by the long end. "
            f"Over 12 months the 30-year rose {d30:+.0f}bp against the 2-year's "
            f"{d2:+.0f}bp, and the 30y-2y spread moved {curve_ago:.0f}bp -> "
            f"{curve:.0f}bp. Over {horizon} years the long end led by only "
            f"{d30_3y - d2_3y:.0f}bp, short of the {LONG_END_LEAD_3Y_BP}bp test. "
            f"The marker is NOT confirmed on either horizon.")
    else:
        notes.append(
            f"The long end led on both horizons: {d30 - d2:+.0f}bp over 12 months "
            f"and {d30_3y - d2_3y:+.0f}bp over {horizon} years. This is the shape "
            f"Dalio's marker describes.")
    return Gauge("g2", "Selling relative to demand", status,
                 f"30-year at {now['y30']:.2f}%, curve {curve:+.0f}bp.",
                 {"y30": now["y30"], "y2": now["y2"], "y10": now["y10"],
                  "d30_bp": d30, "d2_bp": d2, "curve_bp": curve,
                  "curve_bp_ago": curve_ago, "long_end_leads": long_end_leads,
                  "d30_3y_bp": d30_3y, "d2_3y_bp": d2_3y,
                  "curve_bp_3y_ago": curve_ago3,
                  "long_end_leads_3y": long_end_leads_3y},
                 notes)


# --- gauge 3 ----------------------------------------------------------------
def _months_between(a, b):
    ya, ma = int(a[:4]), int(a[5:7])
    yb, mb = int(b[:4]), int(b[5:7])
    return (yb - ya) * 12 + (mb - ma)


def gauge_3(s):
    fed = s["fed"]
    now = fed["balance_sheet_usd_mn"]
    wow = now - fed["prior_week_usd_mn"]
    off_peak = now / fed["peak_usd_mn"] - 1

    monthly = fed.get("monthly") or []
    window = monthly[-(MONETIZATION_WINDOW_M + 1)] if len(monthly) > MONETIZATION_WINDOW_M else None
    trend_pct = (now / window[1] - 1) * 100 if window else (wow / now * 100)
    trough_date, trough = min(monthly, key=lambda r: r[1]) if monthly else (fed["date"], now)
    since_trough_pct = (now / trough - 1) * 100
    months_since_trough = _months_between(trough_date, fed["date"])
    expanding = trend_pct >= MONETIZATION_TURN_PCT

    status = CONTAINED
    if expanding:
        status = SEVERE if trend_pct >= MONETIZATION_FAST_PCT else ELEVATED

    notes = []
    if not expanding:
        notes.append(
            f"The balance sheet is still contracting: {trend_pct:+.1f}% over "
            f"{MONETIZATION_WINDOW_M} months. In Dalio's template this is the gauge "
            "that decides the exit — pressure with a shrinking central bank is a "
            "solvency problem, the same pressure with an expanding one is a "
            "currency problem. It has not fired.")
    else:
        notes.append(
            f"Quantitative tightening has ended. The balance sheet bottomed at "
            f"${trough/1e6:.2f}T in {trough_date[:7]}, {months_since_trough} months ago, "
            f"and is {since_trough_pct:+.1f}% since — {trend_pct:+.1f}% over the last "
            f"{MONETIZATION_WINDOW_M} months. Read week to week this looks like noise; "
            f"read as a slope it is a turn, which is why the gauge is scored on months.")
        notes.append(
            f"What it is not, yet: the balance sheet is still {off_peak:+.1%} against "
            f"its {fed['peak_date'][:7]} peak, and growth of {trend_pct:.1f}% over "
            f"{MONETIZATION_WINDOW_M} months is far below the pace of net issuance it "
            f"would have to absorb to be monetizing the deficit. This is the gauge "
            f"leaving contained, not arriving at the end state — it escalates when "
            f"expansion passes {MONETIZATION_FAST_PCT:.0f}% over the same window.")

    headline = (f"Fed balance sheet ${now/1e6:.2f}T, {trend_pct:+.1f}% over "
                f"{MONETIZATION_WINDOW_M}m.")
    return Gauge("g3", "Central-bank monetization", status, headline,
                 {"balance_sheet": now, "wow_change": wow, "off_peak": off_peak,
                  "expanding": expanding, "trend_pct": trend_pct,
                  "trend_months": MONETIZATION_WINDOW_M,
                  "trough": trough, "trough_date": trough_date,
                  "since_trough_pct": since_trough_pct,
                  "months_since_trough": months_since_trough},
                 notes)


# --- the measuring stick ----------------------------------------------------
def vs_gold(s):
    """Every currency and index priced in gold. Dalio's Q8 in one table."""
    m = s["market"]
    g, g0 = m["gold_usd_oz"], m["gold_usd_oz_yr_ago"]
    gold_ratio = g / g0

    currencies = {}
    for code in ["USD"] + [c for c in m["fx_now"] if c in m["fx_yr_ago"]]:
        rate = 1.0 if code == "USD" else m["fx_now"][code]
        rate0 = 1.0 if code == "USD" else m["fx_yr_ago"][code]
        gold_now, gold_then = g * rate, g0 * rate0
        currencies[code] = {
            "gold_price_now": gold_now,
            "gold_up_pct": (gold_now / gold_then - 1) * 100,
            "currency_vs_gold_pct": (gold_then / gold_now - 1) * 100,
        }

    assets = {}
    for name, key in (("S&P 500", "spx"), ("KOSPI", "kospi")):
        yoy = m[f"{key}_yoy_pct"] / 100
        assets[name] = {"level": m[key], "local_pct": yoy * 100,
                        "in_gold_pct": ((1 + yoy) / gold_ratio - 1) * 100}

    return {"gold_usd": g, "gold_yoy_pct": (gold_ratio - 1) * 100,
            "currencies": currencies, "assets": assets}


def read(snapshot):
    gs = [gauge_1(snapshot), gauge_2(snapshot), gauge_3(snapshot)]
    fired = [g for g in gs if ORDER.index(g.status) >= ORDER.index(ELEVATED)]
    return {"gauges": gs, "stage": _worst(*[g.status for g in gs]),
            "n_elevated": len(fired), "gold": vs_gold(snapshot)}


if __name__ == "__main__":
    import json, sys
    from .config import SNAPSHOT
    r = read(json.load(open(sys.argv[1] if len(sys.argv) > 1 else SNAPSHOT)))
    print(f"STAGE: {r['stage'].upper()}  ({r['n_elevated']}/3 gauges elevated+)\n")
    for g in r["gauges"]:
        print(f"[{g.status.upper():>9}] {g.name}\n            {g.headline}")
        for n in g.notes:
            print(f"            · {n}")
        print()
    print("Currencies vs gold, 12m:")
    for c, v in r["gold"]["currencies"].items():
        print(f"  {c}: {v['currency_vs_gold_pct']:+6.1f}%")
    print("\nAssets:")
    for a, v in r["gold"]["assets"].items():
        print(f"  {a}: local {v['local_pct']:+.1f}%  in gold {v['in_gold_pct']:+.1f}%")
