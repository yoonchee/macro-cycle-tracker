# Big Debt Cycle Monitor — working notes

Tracks Ray Dalio's three Big Debt Cycle gauges against primary-source data.
Gauge definitions come from *How Countries Go Broke: The Big Cycle* (2025).

## Layout

- `tracker/sources/` — one module per data source, each exposing `fetch_all()`
  returning `[{series, date, value, unit?, source?}]`. Sources fail
  independently.
- `tracker/store.py` — SQLite. Idempotent on `(series, date)`, so history
  accumulates even though most APIs only serve a recent window.
- `tracker/gauges.py` — **the opinionated file.** All thresholds live at the top
  as named constants. This is the file to argue with.
- `build.py` — renders `data/snapshot.json` into `out/monitor.html`. Chart
  geometry is computed from the data, never hand-placed.
- `templates/` — `head.html` (fonts) and `monitor.css`. The CSS is theme-token
  based: `:root` holds the light palette, and both `@media (prefers-color-scheme:
  dark)` and `:root[data-theme="dark"]` redefine only the tokens.

## Conventions

- Series names are dotted and namespaced: `us.debt.public`, `us.ust.y30`,
  `fx.usdkrw`, `kr.base_rate`, `mkt.gold_usd`.
- Fiscal figures are annualized from fiscal-year-to-date actuals, never
  projected. Any annualization must state the month count it came from.
- Every asset that matters gets reported in two denominators: local currency and
  gold. That comparison is the point of the framework, not a garnish.
- If a marker Dalio names is **not** confirmed by the data, say so on the page.
  The tracker exists to discipline the narrative, not to illustrate it.

## Adding a source

1. New module in `tracker/sources/` with `fetch_all()`.
2. Register it in `tracker/sources/__init__.py::REGISTRY`.
3. `python refresh.py <name>` — it should print row counts, not a traceback.
4. If it feeds a gauge, add the threshold to `tracker/gauges.py`, not to
   `build.py`.

## Not yet wired

- Treasury weighted-average maturity of new issuance (Dalio's "Treasury shortens
  maturities" tell) — Monthly Statement of the Public Debt.
- TIC foreign holdings of Treasuries; World Gold Council central-bank purchases.
- NY Fed ACM term premium (CSV on newyorkfed.org).
- 한국부동산원 R-ONE weekly apartment index — needs a data.go.kr service key; the
  weekly figures are hand-entered in `data/snapshot.json` for now.
