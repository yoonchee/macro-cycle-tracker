"""US Treasury — the backbone of the tracker. No API key required.

Fiscal Data API docs: https://fiscaldata.treasury.gov/api-documentation/
Daily yield curve:     https://home.treasury.gov/interest-rates-data-csv-archive
"""
import csv
import io
import datetime as dt
import requests

from ..config import UA, TIMEOUT

FISCAL = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"
YIELD_CSV = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
    "daily-treasury-rates.csv/{year}/all"
    "?type=daily_treasury_yield_curve&field_tdr_date_value={year}&page&_format=csv"
)

# Marketable securities only — this is the "interest bill" Dalio's ~$1T refers to.
MARKETABLE = {
    "Treasury Notes", "Treasury Bonds", "Treasury Bills",
    "Inflation Protected Securities (TIPS)",
    "Int. Expense Inflation Compensation (TIPS)",
    "Treasury Floating Rate Notes (FRN)",
}


def _get(path, **params):
    r = requests.get(f"{FISCAL}{path}", params=params, headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json().get("data", [])


def debt_to_penny(n=400):
    """Total public debt outstanding, split public vs intragovernmental. Daily."""
    rows = _get("/v2/accounting/od/debt_to_penny",
                sort="-record_date", **{"page[size]": n})
    out = []
    for r in rows:
        out += [
            {"series": "us.debt.total", "date": r["record_date"],
             "value": r["tot_pub_debt_out_amt"], "unit": "USD", "source": "treasury"},
            {"series": "us.debt.public", "date": r["record_date"],
             "value": r["debt_held_public_amt"], "unit": "USD", "source": "treasury"},
        ]
    return out


def interest_expense(n=600):
    """Monthly interest expense. We keep the marketable FYTD total per month."""
    rows = _get("/v2/accounting/od/interest_expense",
                sort="-record_date", **{"page[size]": n})
    by_date = {}
    for r in rows:
        if r.get("expense_type_desc") in MARKETABLE:
            d = r["record_date"]
            by_date[d] = by_date.get(d, 0.0) + float(r["fytd_expense_amt"] or 0)
    return [{"series": "us.interest.fytd_marketable", "date": d, "value": v,
             "unit": "USD", "source": "treasury"} for d, v in by_date.items()]


def avg_interest_rate(n=120):
    """Weighted-average rate Treasury actually pays on its interest-bearing debt.

    The gap between this and the market rate is committed future interest expense.
    """
    rows = _get("/v2/accounting/od/avg_interest_rates",
                filter="security_desc:eq:Total Interest-bearing Debt",
                sort="-record_date", **{"page[size]": n})
    return [{"series": "us.debt.avg_rate", "date": r["record_date"],
             "value": r["avg_interest_rate_amt"], "unit": "pct", "source": "treasury"}
            for r in rows]


def mts_summary(n=200):
    """Monthly Treasury Statement table 1 — receipts, outlays, deficit (FYTD)."""
    rows = _get("/v1/accounting/mts/mts_table_1",
                sort="-record_date", **{"page[size]": n})
    out = []
    for r in rows:
        if "Year-to-Date" not in (r.get("classification_desc") or ""):
            continue
        d = r["record_date"]
        for key, series in (
            ("current_month_gross_rcpt_amt", "us.receipts.fytd"),
            ("current_month_gross_outly_amt", "us.outlays.fytd"),
            ("current_month_dfct_sur_amt", "us.deficit.fytd"),
        ):
            if r.get(key) not in (None, ""):
                out.append({"series": series, "date": d, "value": r[key],
                            "unit": "USD", "source": "treasury"})
    return out


def yield_curve(years=None):
    """Daily par yield curve. Dalio's 'long end leading' marker lives here."""
    years = years or [dt.date.today().year, dt.date.today().year - 1]
    tenors = {"1 Mo": "m1", "2 Yr": "y2", "5 Yr": "y5", "10 Yr": "y10", "30 Yr": "y30"}
    out = []
    for y in years:
        r = requests.get(YIELD_CSV.format(year=y), headers=UA, timeout=TIMEOUT)
        r.raise_for_status()
        for row in csv.DictReader(io.StringIO(r.text)):
            try:
                m, d, yy = row["Date"].split("/")
                iso = f"{yy}-{m}-{d}"
            except (KeyError, ValueError):
                continue
            for col, tag in tenors.items():
                v = row.get(col)
                if v not in (None, "", "N/A"):
                    out.append({"series": f"us.ust.{tag}", "date": iso, "value": v,
                                "unit": "pct", "source": "treasury"})
    return out


def fetch_all():
    rows = []
    for fn in (debt_to_penny, interest_expense, avg_interest_rate, mts_summary, yield_curve):
        rows += fn()
    return rows
