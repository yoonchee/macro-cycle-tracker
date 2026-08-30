# Big Debt Cycle Monitor

Ray Dalio's claim in *How Countries Go Broke: The Big Cycle* is that the late
stage of a sovereign debt cycle is **measurable**, and that almost nobody
measures it. This repo takes him at his word: it fetches the series his three
gauges are defined on, scores them against stated thresholds, and renders a
dashboard.

**Live dashboard: <https://yoonchee.github.io/macro-cycle-tracker/>** — rebuilt
weekly by GitHub Actions.

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

Every gauge is read over **three years as well as twelve months**. That is not
decoration: on the current data the two horizons disagree about Gauge 2, and a
one-week reading of Gauge 3 said the opposite of what nine months of it says.

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

## What it found (28 Aug 2026)

**Dalio's own figures check out.** Revenue ~$5.4T, spending ~$7.5T, debt held by
the public $32.3T, interest ~20% of revenue. His "about six times revenue" lands
at **6.00×** exactly against the Treasury's own filings.

**All three gauges are now lit.** Interest is 20.1% of receipts — just over the
line, so Gauge 1 scores *severe* — and the average rate Treasury actually pays
(3.45%) is still 1.28pp below the market 10-year, so a large slice of future
interest expense is already committed by arithmetic.

**Gauge 3 turned, and reading it weekly hid that.** The Fed balance sheet
bottomed at $6.55T in Nov 2025 and has risen 2.7% in the nine months since,
+1.8% over the last six. An earlier version of this repo scored the gauge on the
week-over-week H.4.1 print, which swings on repo and TGA operations, and it
reported "still contracting" while the trend had been up for three quarters.
The gauge is now scored on a six-month slope. What this is *not* is monetization
at scale: the balance sheet remains 24.9% below its 2022 peak and 1.8% over six
months is far below the pace of net issuance. This is the gauge leaving
contained, not arriving at the end state.

**Dalio's long-end marker depends entirely on where you start the clock.** He
writes that yields rose "led by the long end." Over twelve months that is false:
the 30-year rose 34bp against the 2-year's 72bp and the 30y−2y spread *narrowed*
from 126bp to 88bp. Over three years it is true, and emphatically: the 30-year
rose 93bp while the 2-year *fell* 64bp — a 157bp lead — and the curve went from
−69bp inverted to +88bp. The twelve-month move is a hiking cycle ending; the
three-year move is the debt-cycle claim. The page reports both so neither can be
quoted alone.

**Japan is running the same measurement, further along.** Read as a curve rather
than as a single 10-year print, the JGB market has repriced duration in public:
the 30-year has gone from 1.59% to **4.04%** in three years (+245bp) and the
30y−2y spread from 158bp to 234bp. The US–Japan 30-year gap has closed to 118bp
from 270bp — the hedged-yield arithmetic that sent Japanese capital abroad for a
generation, running in reverse.

**The Korean buffer is being withdrawn.** A US homeowner on a thirty-year fixed
mortgage is short the bond, which is why American housing absorbs a rate shock
through volume rather than price. Korean borrowers had a version of that — fixed
was *cheaper* than floating through 2025 and took ~90% of new lending — and it is
going away fast: the fixed share of new mortgages has fallen from 96.4% (Jul
2024) to 31.9% (Jul 2026), and the fixed premium flipped from −0.14pp to +0.41pp
as the Bank of Korea began tightening. Over the same three years 가계신용 rose
7.7% to 2,020조원 — the share being repriced is rising against a balance that is
also rising. Note that Korean 고정형 is typically 혼합형 — fixed five years, then
floating — so the buffer was always far shorter-dated than the US thirty-year.

**Seoul apartments outran the rent they can earn.** Over three years, on
한국부동산원's monthly indices: 실거래가격지수 +29.1%, 매매가격지수 (survey)
+21.9%, 전세가격지수 +18.8%, 월세통합가격지수 +12.8%. Prices beat 전세 by 3.2pp
and 월세 by 9.1pp, and the survey index lags actual transactions by 7.2pp. A
price rising faster than the rent it can earn is not being paid for out of
income.

**The measuring stick is where the story actually is.** Gold rose 32.0% in
dollars over twelve months. Against gold: USD −24.2%, EUR −24.6%, KRW −23.5%,
CNY −19.4%, JPY −30.3% — while the cross-rates barely moved. The S&P is +19.3% in
dollars and **−9.6% in gold**. The KOSPI is the exception in this dataset:
+117% in won and still +64% after the gold adjustment, a real gain.

## Where the opinions live

`tracker/gauges.py`, at the top of the file, as named constants. Every threshold
is stated in one place so it can be argued with:

```python
INTEREST_TO_REVENUE   = [(0.10, CONTAINED), (0.20, ELEVATED), (0.30, SEVERE)]
AVG_RATE_CRITICAL     = 4.0   # interest past ~25% of receipts at current revenue
LONG_END_LEAD_BP      = 25    # 30y must outrun the 2y by this over 12m
LONG_END_LEAD_3Y_BP   = 100   # ...and by this over three years
CURVE_STEEP_BP        = 150
MONETIZATION_WINDOW_M = 6     # months of balance-sheet slope Gauge 3 reads
MONETIZATION_TURN_PCT = 1.0   # growth over that window that counts as a turn
MONETIZATION_FAST_PCT = 5.0   # ...and as absorbing issuance rather than drifting
DEFICIT_GDP_LARGE     = 0.05
```

Change them and the dashboard changes. The sources do not.

## Data sources and attribution

| Source | Key | Covers |
|---|---|---|
| [Treasury Fiscal Data API](https://fiscaldata.treasury.gov/api-documentation/) | none | debt, interest expense, average rate, MTS receipts/outlays |
| [Treasury daily yield curve](https://home.treasury.gov/interest-rates-data-csv-archive) | none | par yields, 1mo–30yr |
| [FRED](https://fredaccount.stlouisfed.org/apikeys), Federal Reserve Bank of St. Louis | free | Fed balance sheet, SOMA, deferred asset, CPI, breakevens |
| [財務省 JGB par yields](https://www.mof.go.jp/english/jgbs/reference/interest_rate/) (Japan MoF) | none | daily JGB curve, 1y–40y, back to 1974 |
| Yahoo Finance, via [yfinance](https://github.com/ranaroussi/yfinance) | none | gold, S&P 500, KOSPI, Nikkei, FX, BTC |
| 한국은행 경제통계시스템 [ECOS](https://ecos.bok.or.kr/api/) (Bank of Korea) | free | 기준금리, 가계신용, 주택담보대출 금리 및 고정·변동 비중, CPI |
| 한국부동산원, relayed through ECOS | (ECOS key) | 서울 아파트 매매·전세·월세 가격지수, 아파트 매매 실거래가격지수 |

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
- JGB par yield data is published by 財務省 (Japan Ministry of Finance) and is
  subject to its terms of use.
- Yahoo Finance data is retrieved for personal research use and is subject to
  Yahoo's terms; `yfinance` is not affiliated with or endorsed by Yahoo.

`data/snapshot.json` holds only the current readings and two short series needed
to render the page. The full observation store (`data/history.sqlite`) is
deliberately **not** committed — it is a local cache, not a redistribution.

## Watchlist

Stated in advance so the reading can't be re-narrated after the fact:

- ~~Fed balance sheet stops shrinking and turns up~~ — **this happened.** It
  bottomed Nov 2025. The next threshold is expansion past 5% over six months,
  which is the pace at which it would be absorbing issuance rather than drifting.
- Average rate on the debt crosses 4.0% → interest past 25% of receipts.
- 30y−2y widens past ~150bp *with the 30-year leading* → Gauge 2 confirms on
  both horizons rather than only the three-year one.
- Treasury shortens weighted-average maturity of new issuance.
- Foreign official UST holdings fall while official gold reserves rise.
- 30-year JGB above ~4.5%, or the US–Japan 30-year gap closing below ~50bp.
- Korean fixed-rate share below 20% while 가계신용 keeps rising.
- Seoul 실거래가격지수 turning down while 전세 holds → the leverage, not the
  rent, was carrying the price.
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
