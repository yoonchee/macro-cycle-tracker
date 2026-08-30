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
  `fx.usdkrw`, `kr.base_rate`, `mkt.gold_usd`, `jp.jgb.y30`,
  `us.tic.country.japan`.
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

## Refreshing

`python refresh.py` locally, or the `Refresh monitor` workflow — cron Sundays
07:00 KST plus `gh workflow run refresh.yml`. The workflow is the thing that
publishes: it commits `data/snapshot.json` and `docs/index.html`, and Pages
serves `docs/` from `main`, so a green run republishes the site.

`snapshot.py` raises on a missing or stale series rather than writing zeros, so
a partial fetch fails the run instead of shipping a page that looks fine and
isn't. If a run fails on staleness, check `MAX_AGE_DAYS` against the source's
actual release calendar before widening it — the point of the check is to
notice when a publisher stops publishing.

## Adding a source

1. New module in `tracker/sources/` with `fetch_all()`.
2. Register it in `tracker/sources/__init__.py::REGISTRY`.
3. `python refresh.py <name>` — it should print row counts, not a traceback.
4. If it feeds a gauge, add the threshold to `tracker/gauges.py`, not to
   `build.py`.

## Reading TIC

`us.tic.*` is the demand side of Gauge 2. Two things to keep straight:

- The **official/private split exists only in aggregate** (`us.tic.official` /
  `us.tic.private`). TIC never publishes it per country, so no country line can
  be described as central-bank behaviour.
- **Country totals are attributed to the custodian**, not the owner, which is
  why the UK, Belgium, Cayman, Luxembourg and Ireland look so large.
  `CUSTODY_CENTRES` and `RESERVE_MANAGERS` in `gauges.py` name that split; the
  page states the caveat rather than letting the bars imply otherwise.
- Values are **market** values, so they fall when yields rise with nobody
  selling. TIC's net-transaction series would separate flow from valuation and
  is not on FRED.

## Not yet wired

- Treasury weighted-average maturity of new issuance (Dalio's "Treasury shortens
  maturities" tell) — Monthly Statement of the Public Debt.
- NY Fed ACM term premium (CSV on newyorkfed.org).
- 한국부동산원 R-ONE detail — 거래량, 전월세전환율, 시군구 weekly. The monthly
  indices now come through ECOS and need no extra key, but R-ONE's own API wants
  a key issued by 한국부동산원 itself; a data.go.kr key returns ERROR-290.
- 日銀 JGB holdings, to sit beside the MOF curve as Japan's Gauge 3.
- Official gold reserves, the other half of the TIC marker. FRED has nothing
  usable, IMF `dataservices.imf.org` is retired and `api.imf.org` 404s on IFS;
  World Gold Council has the tonnage but needs scraping or a licence.
- TIC net transactions, to separate official selling from mark-to-market.
