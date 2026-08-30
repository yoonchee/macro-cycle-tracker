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

# Interest on debt held by the public — the "$1T interest bill". Select by
# CATEGORY, not by instrument name: expense_type_desc repeats across groups
# (there is a "Treasury Notes" row under ACCRUED INTEREST EXPENSE *and* under
# AMORTIZED DISCOUNT and AMORTIZED PREMIUM), so matching on names both
# double-counts and misses the negative premium amortization.
#
# The excluded category, INTEREST EXPENSE ON GOVT ACCOUNT SERIES, is interest
# the government pays itself (Social Security and other trust funds). It is
# real accounting but it is not a claim on revenue by outside creditors, which
# is what Gauge 1 measures.
PUBLIC_ISSUES = "INTEREST EXPENSE ON PUBLIC ISSUES"


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


def interest_expense(n=2000):
    """Monthly interest expense, FYTD, on debt held by the public.

    Sums every group within INTEREST EXPENSE ON PUBLIC ISSUES: accrued interest,
    amortized discount, amortized premium (negative), savings bonds and
    miscellaneous. Intragovernmental (GAS) interest is excluded — see the note
    on PUBLIC_ISSUES above.
    """
    rows = _get("/v2/accounting/od/interest_expense",
                sort="-record_date", **{"page[size]": n})
    by_date = {}
    for r in rows:
        if (r.get("expense_catg_desc") or "").strip() != PUBLIC_ISSUES:
            continue
        d = r["record_date"]
        by_date[d] = by_date.get(d, 0.0) + float(r["fytd_expense_amt"] or 0)
    return [{"series": "us.interest.fytd_public", "date": d, "value": v,
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


def mts_summary(n=400):
    """Monthly Treasury Statement table 1 — receipts, outlays, deficit (FYTD).

    One response carries TWO fiscal years as a flat list: an `FY <year>` header
    row, that year's months, then its `Year-to-Date` total, repeated for the
    prior year. The prior year's Year-to-Date is a full twelve months, so
    grabbing the wrong one inflates annualized revenue by ~17%. Rows are keyed
    only by record_date, so we must resolve the section by classification_id
    rather than letting the later row win.
    """
    rows = _get("/v1/accounting/mts/mts_table_1",
                sort="-record_date", **{"page[size]": n})

    by_date = {}
    for r in rows:
        by_date.setdefault(r["record_date"], []).append(r)

    out = []
    for date, group in by_date.items():
        fy = group[0].get("record_fiscal_year")
        group = sorted(group, key=lambda r: int(r.get("classification_id") or 0))
        # the section header for the *current* fiscal year
        header = next((r for r in group
                       if (r.get("classification_desc") or "").strip() == f"FY {fy}"), None)
        if header is None:
            continue
        start = int(header["classification_id"])
        ytd = next((r for r in group
                    if int(r.get("classification_id") or 0) > start
                    and "Year-to-Date" in (r.get("classification_desc") or "")), None)
        if ytd is None:
            continue
        for key, series in (
            ("current_month_gross_rcpt_amt", "us.receipts.fytd"),
            ("current_month_gross_outly_amt", "us.outlays.fytd"),
            ("current_month_dfct_sur_amt", "us.deficit.fytd"),
        ):
            if ytd.get(key) not in (None, ""):
                out.append({"series": series, "date": date, "value": ytd[key],
                            "unit": "USD", "source": "treasury"})
    return out


# Four calendar years, so a three-year-ago comparison always has a full year of
# data behind it even in January.
YEARS_KEPT = 4


def yield_curve(years=None):
    """Daily par yield curve. Dalio's 'long end leading' marker lives here."""
    years = years or [dt.date.today().year - i for i in range(YEARS_KEPT)]
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
