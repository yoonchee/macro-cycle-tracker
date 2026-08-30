# Big Debt Cycle Monitor

Ray Dalio's claim in *How Countries Go Broke: The Big Cycle* is that the late
stage of a sovereign debt cycle is **measurable**, and that almost nobody
measures it. This repo takes him at his word: it fetches the series his three
gauges are defined on, scores them against stated thresholds, and renders a
dashboard.

It is built to disagree with him where the data does — and on the current
reading it does exactly that on one of his named markers. See *What it found*.

## The three gauges

| # | Gauge | Primary series | Source |
|---|-------|----------------|--------|
| 1 | Debt service ÷ government revenue | interest expense, MTS receipts, average rate on the debt | Treasury (no key) |
| 2 | Selling ÷ demand for government debt | daily par yield curve, 30y−2y, long-end leadership | Treasury (no key) |
| 3 | Central-bank monetization | Fed balance sheet, SOMA, the Fed's deferred asset | FRED (free key) |

Plus his market-action markers: currency versus **gold** (not versus other
currencies), and the Korea/Japan transmission channel.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env        # optional — Treasury needs no key
set -a; source .env; set +a

python refresh.py           # fetch everything wired
python build.py --standalone && open out/monitor.html
```

`refresh.py` with no arguments runs every source. Each one fails independently:
no FRED key just means Gauge 3 stays on the last snapshot, and Treasury — which
carries Gauges 1 and 2 entirely — needs no credentials at all.

```bash
python refresh.py treasury          # one source
python refresh.py --coverage        # what the store holds
python -m tracker.gauges            # score the snapshot, text output
```

## What it found on the first run (28 Aug 2026)

**Dalio's own figures check out.** Revenue ~$5.4T, spending ~$7.5T, debt held by
the public $32.3T, interest ~20% of revenue. His "about six times revenue" lands
at **6.00×** exactly against the Treasury's own filings.

**Two gauges lit, the third pointing the other way.** Interest is 20.1% of
receipts — just over the line, so Gauge 1 scores *severe* — and the average rate
Treasury actually pays (3.45%) is still 1.28pp below the market 10-year, so a
large slice of future interest expense is already committed by arithmetic. But
the Fed balance sheet is 24.8% below peak and *still shrinking* — Gauge 3, the
one that decides whether the adjustment lands in nominal prices or in purchasing
power, has not fired.

**The Korean buffer is being withdrawn.** A US homeowner on a thirty-year fixed
mortgage is short the bond, which is why American housing absorbs a rate shock
through volume rather than price. Korean borrowers had a version of that — fixed
was *cheaper* than floating through 2025 and took ~90% of new lending — and it is
going away fast: the fixed share of new mortgages has fallen from 96.4% (Jul
2024) to 31.9% (Jul 2026), and the fixed premium flipped from −0.14pp to +0.41pp
as the Bank of Korea began tightening. Note that Korean 고정형 is typically
혼합형 — fixed five years, then floating — so the buffer was always far
shorter-dated than the US thirty-year.

**One marker contradicts the article.** Dalio writes that yields rose "led by the
long end." Over twelve months the 30-year rose 34bp while the 2-year rose 72bp,
and the 30y−2y spread *narrowed* from 126bp to 88bp. The short end led. That is
a bear flattening, not a duration buyers' strike. The dashboard says so on the
page rather than quietly omitting it.

**The measuring stick is where the story actually is.** Gold rose 34.9% in
dollars over twelve months. Against gold: USD −25.8%, EUR −26.1%, KRW −25.2%,
CNY −21.3%, JPY −31.8% — while the cross-rates barely moved. The S&P is +19.4% in
dollars and **−11.5% in gold**. The KOSPI is the exception in this dataset:
+113% in won and still +58% after the gold adjustment, a real gain.

## Where the opinions live

`tracker/gauges.py`, at the top of the file, as named constants. Every threshold
is stated in one place so it can be argued with:

```python
INTEREST_TO_REVENUE = [(0.10, CONTAINED), (0.20, ELEVATED), (0.30, SEVERE)]
AVG_RATE_CRITICAL   = 4.0     # interest past ~25% of receipts at current revenue
LONG_END_LEAD_BP    = 25      # 30y must outrun the 2y by this to confirm Gauge 2
CURVE_STEEP_BP      = 150
DEFICIT_GDP_LARGE   = 0.05
```

Change them and the dashboard changes. The sources do not.

## Data sources and attribution

| Source | Key | Covers |
|---|---|---|
| [Treasury Fiscal Data API](https://fiscaldata.treasury.gov/api-documentation/) | none | debt, interest expense, average rate, MTS receipts/outlays |
| [Treasury daily yield curve](https://home.treasury.gov/interest-rates-data-csv-archive) | none | par yields, 1mo–30yr |
| [FRED](https://fredaccount.stlouisfed.org/apikeys), Federal Reserve Bank of St. Louis | free | Fed balance sheet, SOMA, deferred asset, CPI, breakevens, 10y JGB |
| Yahoo Finance, via [yfinance](https://github.com/ranaroussi/yfinance) | none | gold, S&P 500, KOSPI, Nikkei, FX, BTC |
| 한국은행 경제통계시스템 [ECOS](https://ecos.bok.or.kr/api/) (Bank of Korea) | free | 기준금리, 가계신용, 주택담보대출 금리 및 고정·변동 비중, CPI |
| [한국부동산원 R-ONE](https://www.reb.or.kr/r-one/) | free via data.go.kr | weekly apartment price index — *not yet wired, hand-entered* |

**Attribution.** Data in this repository is retrieved from the providers above
and remains theirs. This project's Apache-2.0 license covers its own source code
only and grants no rights in that data.

- 한국은행 경제통계시스템(ECOS) 자료를 이용하였습니다. 출처: 한국은행.
  ECOS 자료의 재배포는 한국은행 이용약관을 따릅니다.
- FRED® data is provided by the Federal Reserve Bank of St. Louis and is subject
  to its [terms of use](https://fred.stlouisfed.org/legal/). FRED® is a
  registered trademark of the Federal Reserve Bank of St. Louis, which is not
  affiliated with and does not endorse this project.
- US Treasury Fiscal Data and daily yield curve figures are US Government works
  in the public domain.
- Yahoo Finance data is retrieved for personal research use and is subject to
  Yahoo's terms; `yfinance` is not affiliated with or endorsed by Yahoo.

`data/snapshot.json` holds only the current readings and two short series needed
to render the page. The full observation store (`data/history.sqlite`) is
deliberately **not** committed — it is a local cache, not a redistribution.

## Watchlist

Stated in advance so the reading can't be re-narrated after the fact:

- Fed balance sheet stops shrinking and turns up while the deficit is near 7% of
  GDP → **Gauge 3 fires.** This is the regime change; everything else is prologue.
- Average rate on the debt crosses 4.0% → interest past 25% of receipts.
- 30y−2y widens past ~150bp *with the 30-year leading* → Gauge 2 confirms.
- Treasury shortens weighted-average maturity of new issuance.
- Foreign official UST holdings fall while official gold reserves rise.
- 10-year JGB above ~3.5% without BoJ intervention.
- Gold's twelve-month gain falls below ~10% across all major currencies → the
  cleanest single falsification of the devaluation thesis.

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE). The license covers this
project's source code; see *Data sources and attribution* above for the terms
attached to the data it retrieves.

## Caveats

A monitor, not a forecast, and not investment advice. Dalio's own timing guess is
"three years, give or take two, if the course we're on is not changed" — followed
immediately by "which I suppose will be a bad one." The framework is useful for
deciding what a portfolio can survive. It has never been useful for deciding when.
