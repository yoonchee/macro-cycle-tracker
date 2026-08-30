"""Japan — the template already running. No API key required.

MOF publishes the JGB par yield curve daily, 1Y through 40Y, back to 1974:
  https://www.mof.go.jp/english/jgbs/reference/interest_rate/

This replaces the FRED monthly 10-year series. Dalio's Q7 argument is about the
*shape* of the Japanese curve — a country that funded 215% debt-to-GDP on the
assumption that yields stay near zero has a duration problem at the long end
first — and a single monthly 10-year point cannot show that. MOF gives the whole
curve at a daily cadence, from the issuer, which is what the US side already
uses.

Two files: the historical archive ends with the prior month, so the current
month is fetched separately and merged.
"""
import csv
import datetime as dt
import io

import requests

from ..config import UA, TIMEOUT

BASE = "https://www.mof.go.jp/english/jgbs/reference/interest_rate"
HISTORICAL = f"{BASE}/historical/jgbcme_all.csv"
CURRENT = f"{BASE}/jgbcme.csv"

# Mirrors the US tenor set where the maturities exist. Japan has no bill on this
# table, so the short leg is the 1-year rather than the 1-month.
TENORS = {"1Y": "y1", "2Y": "y2", "5Y": "y5", "10Y": "y10", "30Y": "y30", "40Y": "y40"}

YEARS_KEPT = 4      # enough for the two-year curve comparison plus a margin


def _parse(text, since):
    """MOF CSV: a title line, a header line, then `2026/8/3,1.287,...` rows."""
    rows = []
    reader = csv.reader(io.StringIO(text))
    header = None
    for row in reader:
        if not row:
            continue
        if header is None:
            if row[0].strip() == "Date":
                header = [c.strip() for c in row]
            continue
        try:
            y, m, d = (int(x) for x in row[0].split("/"))
            date = dt.date(y, m, d)
        except (ValueError, IndexError):
            continue
        if date < since:
            continue
        for col, value in zip(header[1:], row[1:]):
            tag = TENORS.get(col)
            if tag is None or value.strip() in ("", "-"):
                continue
            rows.append({"series": f"jp.jgb.{tag}", "date": date.isoformat(),
                         "value": value.strip(), "unit": "pct", "source": "mof"})
    return rows


def yield_curve(years=YEARS_KEPT):
    since = dt.date.today().replace(year=dt.date.today().year - years)
    out = []
    for url in (HISTORICAL, CURRENT):
        r = requests.get(url, headers=UA, timeout=TIMEOUT)
        r.raise_for_status()
        out += _parse(r.text, since)
    return out


def fetch_all():
    return yield_curve()


if __name__ == "__main__":
    rows = fetch_all()
    last = max(r["date"] for r in rows)
    print(f"{len(rows)} rows, {len({r['series'] for r in rows})} series, latest {last}")
    for r in sorted(rows, key=lambda r: r["series"]):
        if r["date"] == last:
            print(f"  {r['series']:<12} {r['value']}")
