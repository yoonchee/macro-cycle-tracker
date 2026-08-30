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


def _paged(path, page_size=10000, **params):
    """Every page, not just the first.

    MSPD table 3 is one row per CUSIP, so a single month is ~700 rows and a page
    boundary lands *inside* a month. Taking page one alone would compute that
    month's weighted-average maturity from whatever fraction of the debt
    happened to fit — which looks like a plausible number, not like an error.
    """
    out, page = [], 1
    while True:
        r = requests.get(f"{FISCAL}{path}", headers=UA, timeout=TIMEOUT,
                         params={**params, "page[size]": page_size, "page[number]": page})
        r.raise_for_status()
        body = r.json()
        out += body.get("data", [])
        if page >= (body.get("meta", {}).get("total-pages") or 1):
            return out
        page += 1


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


# Four calendar years, so a two-years-back comparison always has a full year of
# data behind it even in January.
YEARS_KEPT = 4


# --- maturity structure ------------------------------------------------------
# Dalio's "Treasury shortens maturities" tell. A Treasury that cannot sell
# duration funds itself short instead, which quietly converts a solvency problem
# into a rollover problem — the debt reprices at the front of the curve within
# months rather than over a decade.
#
# Measured on the stock and on the flow, because they can disagree and each
# answers a different question. The stock says what has already been financed
# short; the flow says what Treasury is choosing to sell now.
MSPD_YEARS = 5


def _since(years):
    today = dt.date.today()
    try:
        return today.replace(year=today.year - years).isoformat()
    except ValueError:                      # 29 Feb
        return today.replace(year=today.year - years, day=28).isoformat()


def maturity_profile(years=MSPD_YEARS):
    """Weighted-average maturity of marketable debt outstanding, in months.

    Par-weighted, which is Treasury's own convention: TIPS count at face rather
    than inflation-adjusted value. Rows with no outstanding amount are stripped
    or matured entries and are skipped — the remaining total reconciles with
    MSPD table 1 to within the Federal Financing Bank, which carries no maturity.
    """
    rows = _paged("/v1/debt/mspd/mspd_table_3",
                  filter=f"record_date:gte:{_since(years)},security_type_desc:eq:Marketable",
                  fields="record_date,maturity_date,outstanding_amt",
                  sort="-record_date")
    by = {}
    for r in rows:
        amt, mat = r.get("outstanding_amt"), r.get("maturity_date")
        if not amt or amt in ("null",) or not mat or mat == "null":
            continue
        amt = float(amt)
        if amt <= 0:
            continue
        ref = dt.date.fromisoformat(r["record_date"])
        years_to = (dt.date.fromisoformat(mat) - ref).days / 365.25
        a, w, s = by.get(r["record_date"], (0.0, 0.0, 0.0))
        by[r["record_date"]] = (a + amt, w + amt * years_to,
                                s + (amt if years_to <= 1 else 0.0))
    out = []
    for d, (a, w, short) in by.items():
        if a <= 0:
            continue
        out.append({"series": "us.debt.wam_months", "date": d, "value": w / a * 12,
                    "unit": "months", "source": "treasury"})
        # The rollover number: how much of the marketable stock has to be
        # refinanced within a year at whatever rate prevails then. An average
        # maturity held flat by a barbell hides this; this does not.
        out.append({"series": "us.debt.maturing_1y_pct", "date": d,
                    "value": short / a * 100, "unit": "pct", "source": "treasury"})
    return out


def marketable_mix(years=MSPD_YEARS):
    """Bills as a share of marketable debt — the fastest-moving shortening tell."""
    rows = _paged("/v1/debt/mspd/mspd_table_1", page_size=5000,
                  filter=f"record_date:gte:{_since(years)}",
                  fields="record_date,security_type_desc,security_class_desc,total_mil_amt",
                  sort="-record_date")
    bills, marketable = {}, {}
    for r in rows:
        kind, cls = r["security_type_desc"], r["security_class_desc"]
        if kind == "Marketable" and cls == "Bills":
            bills[r["record_date"]] = float(r["total_mil_amt"])
        elif kind == "Total Marketable":
            marketable[r["record_date"]] = float(r["total_mil_amt"])
    out = []
    for d, total in marketable.items():
        if d in bills and total:
            out.append({"series": "us.debt.bill_share_pct", "date": d,
                        "value": bills[d] / total * 100, "unit": "pct",
                        "source": "treasury"})
            out.append({"series": "us.debt.marketable", "date": d, "value": total,
                        "unit": "USD_mn", "source": "treasury"})
    return out


def issuance_maturity(years=MSPD_YEARS):
    """Twelve-month rolling weighted-average maturity of new COUPON issuance.

    Bills are excluded on purpose. Gross issuance is ~85% bills in every period
    because a 4-week bill is sold thirteen times a year, so a bill-inclusive
    average measures rollover frequency rather than any decision. The question
    worth asking is whether, within the duration Treasury does sell, it is
    selling less of it.

    SOMA add-ons are removed: `total_accepted` is competitive + noncompetitive +
    SOMA, and the SOMA leg is the Fed rolling its own holdings, not the market
    financing the deficit.
    """
    rows = _paged("/v1/accounting/od/auctions_query",
                  filter=f"issue_date:gte:{_since(years + 1)}",
                  fields="security_type,issue_date,maturity_date,total_accepted,soma_accepted",
                  sort="-issue_date")
    coupons = []
    for r in rows:
        if r.get("security_type") == "Bill":
            continue
        ta = r.get("total_accepted")
        if not ta or ta == "null":
            continue
        amt = float(ta) - float(r.get("soma_accepted") or 0)
        if amt <= 0:
            continue
        iss = dt.date.fromisoformat(r["issue_date"])
        mat = dt.date.fromisoformat(r["maturity_date"])
        coupons.append((iss, amt, (mat - iss).days / 365.25))
    if not coupons:
        return []
    coupons.sort()
    # one reading per month-end, over the trailing twelve months
    month_ends = sorted({dt.date(i.year, i.month, 1) for i, _, _ in coupons})
    out = []
    for m in month_ends:
        window = [(a, y) for i, a, y in coupons if m - dt.timedelta(days=365) < i <= m]
        amt = sum(a for a, _ in window)
        if amt <= 0 or len(window) < 12:      # not a full year of auctions yet
            continue
        out.append({"series": "us.issuance.coupon_wam_months",
                    "date": m.isoformat(),
                    "value": sum(a * y for a, y in window) / amt * 12,
                    "unit": "months", "source": "treasury"})
    return out


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
    for fn in (debt_to_penny, interest_expense, avg_interest_rate, mts_summary,
               maturity_profile, marketable_mix, issuance_maturity, yield_curve):
        rows += fn()
    return rows
