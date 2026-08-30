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
- `tracker/snapshot.py` — derives `data/snapshot.json` from the store. Carries
  *paths*, not just latest points, because every gauge is a claim about a
  direction. Raises on a missing or stale series rather than writing
  zeros.
- `build.py` — renders `data/snapshot.json` into `out/monitor.html`. Chart
  geometry is computed from the data, never hand-placed. Two primitives:
  `curve_chart` (a term structure at three dates, used for both the UST and JGB
  curves) and `ts_chart` (paths through time, with an optional right-hand axis
  for series that share time but not units).
- `templates/` — `head.html` (fonts) and `monitor.css`. The CSS is theme-token
  based: `:root` holds the light palette, and both `@media (prefers-color-scheme:
  dark)` and `:root[data-theme="dark"]` redefine only the tokens.

## Conventions

- Series names are dotted and namespaced: `us.debt.public`, `us.ust.y30`,
  `fx.usdkrw`, `kr.base_rate`, `mkt.gold_usd`, `jp.jgb.y30`.
- Read gauges over a window, not a print. Anything that swings on operational
  noise — the weekly H.4.1 especially — gets scored on a slope whose length is a
  named constant in `gauges.py`. A single print is not evidence of direction.
- Fiscal figures are annualized from fiscal-year-to-date actuals, never
  projected. Any annualization must state the month count it came from.
- Every asset that matters gets reported in two denominators: local currency and
  gold. That comparison is the point of the framework, not a garnish.
- Where a horizon changes the answer, publish both horizons. Gauge 2's long-end
  marker fails over twelve months and passes over two years; the page says so.
- Curves are compared at annual snapshots — today, y−1, y−2 (`CURVE_LOOKBACK` in
  `snapshot.py`). Time-series paths use their own, longer window.
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
- 한국부동산원 R-ONE detail — 거래량, 전월세전환율, 시군구 weekly. The monthly
  indices now come through ECOS and need no extra key, but R-ONE's own API wants
  a key issued by 한국부동산원 itself; a data.go.kr key returns ERROR-290.
- 日銀 JGB holdings, to sit beside the MOF curve as Japan's Gauge 3.
