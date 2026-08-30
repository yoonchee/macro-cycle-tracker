#!/usr/bin/env python3
"""Render data/snapshot.json into out/monitor.html.

Chart geometry is computed, not hand-placed, so new data can't silently break
the plot. `--standalone` wraps the page in a full HTML document for local
viewing; without it the output is body-only, which is what the Artifact
publisher expects.

    python build.py                 # -> out/monitor.html (body-only)
    python build.py --standalone    # -> out/monitor.html (full document)
"""
import argparse
import json
from pathlib import Path

from tracker import gauges
from tracker.config import SNAPSHOT, OUT, ROOT

TPL = ROOT / "templates"
PILL = {"contained": "ok", "elevated": "warn", "severe": "warn", "critical": "crit"}
LABEL = {"contained": "Not triggered", "elevated": "Elevated",
         "severe": "Severe", "critical": "Critical"}


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def metric(k, v, sub=""):
    return (f'<div class="metric"><span class="k">{k}</span><span class="v">{v}</span>'
            f'{f"<span class=s>{sub}</span>" if sub else ""}</div>')


def metrics(*items):
    return f'<div class="metrics">{"".join(items)}</div>'


def pill(status):
    return f'<span class="pill {PILL[status]}">{LABEL[status]}</span>'


def sechead(idx, title):
    return f'<div class="sechead"><span class="idx">{idx}</span><h2>{title}</h2></div>'


# --- charts -----------------------------------------------------------------
def gap_scale(avg, y10, y30, lo=None, hi=None):
    """Average rate paid vs market rates, on one scale."""
    lo = lo if lo is not None else min(avg, y10, y30) - 0.5
    hi = hi if hi is not None else max(avg, y10, y30) + 0.6
    pos = lambda v: (v - lo) / (hi - lo) * 100
    mk = lambda v, lbl, col: (
        f'<div class="marker" style="left:{pos(v):.1f}%; --mk:var(--{col})">'
        f'<span>{v:.2f}%</span><small>{lbl}</small></div>')
    return (
        '<div class="gapscale"><div class="gaptrack"></div>'
        f'<div class="gapfill" style="left:{pos(avg):.1f}%; width:{pos(y10)-pos(avg):.1f}%"></div>'
        + mk(avg, "avg paid", "accent") + mk(y10, "10-year", "gold") + mk(y30, "30-year", "gold")
        + f'<div class="scaleends"><span class="num">{lo:.1f}%</span>'
          f'<span class="num">{hi:.1f}%</span></div></div>')


def curve_svg(now, ago, d_now, d_ago):
    """Two yield curves, twelve months apart. Coordinates computed from the data."""
    tenors = [("m1", "1 month", 110), ("y2", "2 year", 290),
              ("y10", "10 year", 490), ("y30", "30 year", 660)]
    vals = [now[k] for k, _, _ in tenors] + [ago[k] for k, _, _ in tenors]
    lo = (min(vals) * 10 // 2) / 5 - 0.2
    hi = (max(vals) * 10 // 2) / 5 + 0.3
    TOP, BOT = 30, 205
    y = lambda v: BOT - (v - lo) / (hi - lo) * (BOT - TOP)

    def line(src, colour, width, r, labels_above):
        pts = " ".join(f"{x},{y(src[k]):.1f}" for k, _, x in tenors)
        dots = "".join(f'<circle cx="{x}" cy="{y(src[k]):.1f}" r="{r}"></circle>'
                       for k, _, x in tenors)
        texts = "".join(
            f'<text x="{x}" y="{y(src[k]) + (-10 if labels_above[i] else 17):.1f}">'
            f'{src[k]:.2f}</text>' for i, (k, _, x) in enumerate(tenors))
        return pts, dots, texts

    above_now = [now[k] > ago[k] for k, _, _ in tenors]
    above_ago = [not a for a in above_now]
    p1, d1, t1 = line(ago, "gold", 2, 4.5, above_ago)
    p2, d2, t2 = line(now, "accent", 2.4, 5.5, above_now)

    grid = "".join(
        f'<line x1="52" y1="{y(g):.1f}" x2="700" y2="{y(g):.1f}"></line>'
        for g in _ticks(lo, hi))
    gtext = "".join(f'<text x="44" y="{y(g)+4:.1f}">{g:.1f}</text>' for g in _ticks(lo, hi))
    xtext = "".join(f'<text x="{x}" y="226">{lbl}</text>' for _, lbl, x in
                    [(k, l, x) for k, l, x in tenors])
    desc = "; ".join(f"{l} {now[k]:.2f} vs {ago[k]:.2f}" for k, l, _ in tenors)

    return f'''<div class="svgwrap"><svg viewBox="0 0 720 260" role="img"
 aria-label="US Treasury yield curve {d_now} versus {d_ago}: {desc}">
<line class="ax" x1="52" y1="205" x2="700" y2="205"></line>
<line class="ax" x1="52" y1="30" x2="52" y2="205"></line>
<g class="axtext" text-anchor="end">{gtext}</g>
<g class="ax" stroke-dasharray="2 4" opacity=".55">{grid}</g>
<polyline fill="none" stroke="var(--gold)" stroke-width="2" stroke-linejoin="round" points="{p1}"></polyline>
<g fill="var(--gold)">{d1}</g>
<g class="dotlabel" fill="var(--muted)" text-anchor="middle">{t1}</g>
<polyline fill="none" stroke="var(--accent)" stroke-width="2.4" stroke-linejoin="round" points="{p2}"></polyline>
<g fill="var(--accent)" stroke="var(--surface)" stroke-width="2">{d2}</g>
<g class="dotlabel" text-anchor="middle">{t2}</g>
<g class="axtext" text-anchor="middle">{xtext}</g>
</svg></div>'''


def _ticks(lo, hi, n=4):
    step = (hi - lo) / n
    return [round(lo + step * i, 1) for i in range(1, n + 1)]


def gold_bars(currencies):
    rows = sorted(currencies.items(), key=lambda kv: kv[1]["currency_vs_gold_pct"])
    span = max(abs(v["currency_vs_gold_pct"]) for _, v in rows) * 1.26
    out = []
    for code, v in rows:
        pct = v["currency_vs_gold_pct"]
        w = abs(pct) / span * 100
        out.append(
            f'<div class="barrow"><span class="lbl">{code}</span>'
            f'<div class="bartrack"><div class="barfill" style="width:{w:.1f}%"></div>'
            f'<div class="barval" style="left:{w:.1f}%">{pct:+.1f}%</div></div></div>')
    return f'<div class="bars">{"".join(out)}</div>'


# --- page -------------------------------------------------------------------
def render(s):
    r = gauges.read(s)
    g1, g2, g3 = r["gauges"]
    m1, m2, m3 = g1.metrics, g2.metrics, g3.metrics
    gold = r["gold"]
    kr, jp = s["asia"]["korea"], s["asia"]["japan"]
    ny, ay = s["yields"]["now"], s["yields"]["yr_ago"]

    tiles = "".join(
        f'<div class="tile"><span class="g">Gauge {i} · {n}</span>{pill(g.status)}'
        f'<span class="n">{esc(g.headline)}</span></div>'
        for i, (g, n) in enumerate(
            zip(r["gauges"], ["Debt service", "Supply vs demand", "Monetization"]), 1))

    notes = lambda g: "".join(f'<div class="note"><p>{esc(n)}</p></div>' for n in g.notes)

    body = f'''<div class="wrap">
<header class="top">
  <span class="eyebrow">Ray Dalio · How Countries Go Broke · gauge readings</span>
  <h1>Big Debt Cycle Monitor</h1>
  <p class="lede">Dalio says the late stage of a debt cycle is measurable, and that
  almost nobody measures it. These are his three gauges plus his market-action
  markers, read against live data — including where the tape disagrees with the
  narrative.</p>
  <div class="stamp"><span>Data as of <strong class="num">{s["as_of"]}</strong></span>
  <span>Fiscal: US Treasury</span><span>Rates: US Treasury</span><span>FX: ECB</span></div>
</header>

<div class="readout">
  <p class="verdict">{r["n_elevated"]} of the three gauges are elevated. Composite
  stage: <strong>{r["stage"]}</strong>.</p>
  <div class="tiles">{tiles}</div>
</div>

<section>{sechead("GAUGE 1", "Debt service relative to revenue")}
  <p>Dalio's plaque metaphor: the slowest-moving gauge, and the one that sets the
  ceiling on everything else.</p>
  {metrics(
      metric("Interest ÷ receipts", f"{m1['interest_to_receipts']:.1%}",
             f"~${m1['interest']/1e12:.2f}T on ~${m1['receipts']/1e12:.2f}T revenue, annualized"),
      metric("Debt ÷ receipts", f"{m1['debt_to_receipts']:.2f}×",
             f"Held by the public; {m1['debt_total_to_receipts']:.2f}× counting intragovernmental"),
      metric("Outlays ÷ receipts", f"{m1['outlays_to_receipts']:.0%}",
             f"${m1['deficit']/1e12:.2f}T deficit"),
      metric("Avg rate on the debt", f"{m1['avg_rate']:.2f}%",
             f"{m1['repricing_gap_pp']:.2f}pp below the market 10-year"))}
  <div class="card striped s-{PILL[g1.status]}">
    <figure><div class="charttitle">The repricing pipeline</div>
    <div class="chartsub">What Treasury pays on its stock of debt, against what the market charges today</div>
    <div class="legend"><span><i style="background:var(--accent)"></i>Average rate paid</span>
    <span><i style="background:var(--gold)"></i>Market rate today</span>
    <span><i style="background:var(--gold); opacity:.3; box-shadow:inset 0 0 0 1px var(--gold)"></i>Committed repricing gap</span></div>
    {gap_scale(m1["avg_rate"], ny["y10"], ny["y30"])}
    <figcaption>Roughly $10T of principal rolls every year. Each maturity that rolls
    moves the average rate paid toward the market rate — the gap is arithmetic
    already committed, not a forecast.</figcaption></figure>
  </div>
  {notes(g1)}
</section>

<section>{sechead("GAUGE 2", "Selling relative to demand")}
  <p>Dalio's market signature for this stage is rates rising <em>led by the long
  end</em>. That is a testable claim, so the tracker tests it.</p>
  <div class="card striped s-{PILL[g2.status]}">
    <figure><div class="charttitle">US Treasury curve, twelve months apart</div>
    <div class="chartsub">{ay["date"]} versus {ny["date"]}, percent</div>
    <div class="legend"><span><i style="background:var(--accent)"></i>{ny["date"]}</span>
    <span><i style="background:var(--gold)"></i>{ay["date"]}</span></div>
    {curve_svg(ny, ay, ny["date"], ay["date"])}
    <figcaption>30-year {m2["d30_bp"]:+.0f}bp over twelve months against the
    2-year's {m2["d2_bp"]:+.0f}bp. The 30y–2y spread moved
    {m2["curve_bp_ago"]:.0f}bp → {m2["curve_bp"]:.0f}bp.</figcaption></figure>
  </div>
  {metrics(
      metric("30-year", f"{m2['y30']:.2f}%", f"{m2['d30_bp']:+.0f}bp over 12 months"),
      metric("2-year", f"{m2['y2']:.2f}%", f"{m2['d2_bp']:+.0f}bp over 12 months"),
      metric("30y − 2y", f"{m2['curve_bp']:+.0f}bp",
             f"From {m2['curve_bp_ago']:+.0f}bp a year ago"))}
  {notes(g2)}
</section>

<section>{sechead("GAUGE 3", "Central-bank monetization")}
  <p>The gauge that decides which exit the cycle takes.</p>
  <div class="card striped s-{PILL[g3.status]}">{pill(g3.status)}
  {metrics(metric("Fed balance sheet", f"${m3['balance_sheet']/1e6:.2f}T",
                  f"{m3['off_peak']:+.1%} versus peak · {m3['wow_change']/1e3:+,.1f}bn on the week"))}
  {notes(g3)}
  </div>
</section>

<section>{sechead("MARKER", "The measuring stick")}
  <p>A currency's decline is invisible measured against other currencies that are
  declining too. Gold rose {gold["gold_yoy_pct"]:.1f}% in dollars over twelve months.</p>
  <div class="card striped s-crit">
    <figure><div class="charttitle">What each currency lost against gold</div>
    <div class="chartsub">Twelve months to {s["as_of"]}</div>
    {gold_bars(gold["currencies"])}
    <figcaption>Measured against each other these currencies barely moved.
    Measured against gold they devalued together.</figcaption></figure>
  </div>
  <div class="card" style="margin-top:18px"><h3 style="margin-bottom:14px">The same assets in two denominators</h3>
  <div class="scroller"><table class="data"><thead><tr><th>Asset</th><th>Level</th>
  <th>12m local</th><th>12m in gold</th></tr></thead><tbody>
  {"".join(f'<tr><td>{a}</td><td class="n">{v["level"]:,.2f}</td>'
           f'<td class="n">{v["local_pct"]:+.1f}%</td>'
           f'<td class="n" style="color:var(--{"ok" if v["in_gold_pct"]>0 else "crit"})">'
           f'{v["in_gold_pct"]:+.1f}%</td></tr>' for a, v in gold["assets"].items())}
  </tbody></table></div></div>
</section>

<section>{sechead("MARKER", "Japan and Korea")}
  <div class="grid g2">
    <div class="card striped s-crit"><h3 style="margin-bottom:12px">Japan</h3>
    {metrics(metric("10-year JGB", f"{jp['jgb10']:.2f}%", f"{jp['jgb10_chg_12m']*100:+.0f}bp over 12 months"),
             metric("30-year JGB", f"{jp['jgb30']:.2f}%", f"{jp['jgb30_chg_12m']*100:+.0f}bp over 12 months"))}
    <p style="font-size:14px;margin-bottom:0">Japan carries roughly 215% debt-to-GDP
    on the assumption that yields stay near zero. Rising JGB yields turn Dalio's
    Q7 argument from theory into arithmetic.</p></div>

    <div class="card striped s-warn"><h3 style="margin-bottom:12px">Korea</h3>
    {metrics(metric("BOK base rate", f"{kr['base_rate']:.2f}%", f"From {kr['prev_rate']:.2f}% on {kr['last_hike']}"),
             metric("CPI / core", f"{kr['cpi']:.1f}%", f"Core {kr['core_cpi']:.1f}%, above the 2% target"))}
    <p style="font-size:14px">Korean mortgages are largely floating-rate, so policy
    tightening reaches household cash flow immediately — there is no thirty-year-fixed
    buffer of the kind that insulates US homeowners.</p>
    <p style="font-size:14px;margin-bottom:0">Seoul apartments {kr['seoul_apt_wow']:+.2f}% in the
    week to {kr['housing_date']}, but rotating rather than rising uniformly:
    강남 {kr['gangnam_wow']:+.2f}% and 서초 {kr['seocho_wow']:+.2f}% against
    강북 14개구 {kr['gangbuk14_wow']:+.2f}%.</p></div>
  </div>
</section>

<footer><p>Gauge definitions from Ray Dalio, <em>How Countries Go Broke: The Big
Cycle</em> (2025). Readings computed from US Treasury, Federal Reserve, ECB and
Bank of Korea primary sources. A monitor, not a forecast, and not investment
advice.</p></footer>
</div>'''
    return body


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", default=str(SNAPSHOT))
    ap.add_argument("--out", default=str(OUT / "monitor.html"))
    ap.add_argument("--standalone", action="store_true",
                    help="wrap in a full HTML document for local viewing")
    a = ap.parse_args()

    s = json.load(open(a.snapshot))
    head = (TPL / "head.html").read_text()
    css = (TPL / "monitor.css").read_text()
    page = f"{head}\n<style>\n{css}</style>\n\n{render(s)}\n"
    if a.standalone:
        page = ('<!doctype html><html><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width,initial-scale=1">'
                f'</head><body style="margin:0">{page}</body></html>')
    Path(a.out).write_text(page)
    print(f"wrote {a.out}  ({len(page):,} bytes)")


if __name__ == "__main__":
    main()
