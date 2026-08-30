# Weekly refresh playbook (cloud / agent-driven)

The hosted dashboard is refreshed by a scheduled Claude session rather than by
cron running `refresh.py`, because that sandbox has no general network egress —
only WebFetch. On a machine with normal network access, `python refresh.py` does
the same job better and this file is unnecessary.

Fetch each of these, update `data/snapshot.json`, then rebuild and republish.

## 1. Treasury (no key, always works)

- Debt: `https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/debt_to_penny?sort=-record_date&page[size]=3`
  → `us_fiscal.debt_total` (`tot_pub_debt_out_amt`), `debt_held_public` (`debt_held_public_amt`)
- Interest: `.../v2/accounting/od/interest_expense?sort=-record_date&page[size]=14`
  → sum `fytd_expense_amt` across the marketable types only: Treasury Notes,
  Bonds, Bills, TIPS, TIPS inflation compensation, FRN. Note the month count.
- Average rate: `.../v2/accounting/od/avg_interest_rates?filter=security_desc:eq:Total Interest-bearing Debt&sort=-record_date&page[size]=8`
- Receipts/outlays: `.../v1/accounting/mts/mts_table_1?filter=record_calendar_month:eq:<MM>,record_fiscal_year:eq:<YYYY>&sort=-record_date&page[size]=20`
  → the "Year-to-Date" classification rows
- Yields: `https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/<YYYY>/all?type=daily_treasury_yield_curve&field_tdr_date_value=<YYYY>&_format=csv`
  → latest row for `now`; the same calendar date one year earlier for `yr_ago`

## 2. FX (no key)

`https://api.frankfurter.dev/v1/latest?base=USD&symbols=KRW,JPY,CNY,EUR,CHF`
and `https://api.frankfurter.dev/v1/<YYYY-MM-DD one year ago>?base=USD&symbols=KRW,JPY,CNY,EUR`

## 3. Gold, equities, Fed, Asia (search + fetch)

These have no clean keyless JSON endpoint reachable from the sandbox, so use
search and read the figure off a primary-ish page:

- Gold spot USD/oz, and the twelve-month-ago level
- S&P 500 and KOSPI levels with 12-month percentage change
- Fed total assets (H.4.1), current and prior week
- Japan 10y and 30y JGB yields with 12-month change
- BOK base rate; Korea CPI and core
- 한국부동산원 weekly 아파트 매매가격지수: Seoul w/w, 강남/서초 w/w, 강북 14개구 w/w

## 4. Rebuild and republish

1. Write the updated values into `data/snapshot.json` (keep the schema).
2. `python build.py` → body-only HTML.
3. Republish to the **same artifact URL** so the link stays stable.
4. If a Dalio marker flipped state — Gauge 3 firing, or the long end starting to
   lead — say so explicitly in the republish note. State changes are the product.

## Sanity checks before publishing

- Interest ÷ receipts should move slowly. A jump of more than ~1pp week over week
  means the month count used for annualization is wrong.
- Debt held by the public ÷ annualized receipts sat at 6.00× on 28 Aug 2026.
- Every currency-versus-gold figure should have the same sign. If one diverges
  sharply, an FX rate is inverted.
