#!/usr/bin/env python3
"""Render data/snapshot.json into out/monitor.html.

Chart geometry is computed, not hand-placed, so new data can't silently break
the plot. `--standalone` wraps the page in a full HTML document for local
viewing; without it the output is body-only, which is what the Artifact
publisher expects.

    python build.py                 # -> out/monitor.html (body-only)
    python build.py --standalone    # -> out/monitor.html (full document)

Two chart primitives do all the work. `curve_chart` draws a term structure at
several dates — used for both the US and Japanese curves, because the whole
point of putting Japan on the page is that it is the same measurement. `ts_chart`
draws paths through time, optionally against a second right-hand axis when the
two series share an axis of time but not of units.
"""
import argparse
import datetime as dt
import json
import math
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


def legend(*items):
    """items: (colour token, label) or (colour token, label, 'dashed')."""
    out = []
    for colour, label, *rest in items:
        style = f"background:var(--{colour})"
        if rest and rest[0] == "dashed":
            style = (f"background:repeating-linear-gradient(90deg,var(--{colour}) 0 3px,"
                     f"transparent 3px 6px)")
        elif rest and rest[0] == "ghost":
            style = (f"background:var(--{colour}); opacity:.3; "
                     f"box-shadow:inset 0 0 0 1px var(--{colour})")
        out.append(f'<span><i style="{style}"></i>{esc(label)}</span>')
    return f'<div class="legend">{"".join(out)}</div>'


def chart_head(title, sub):
    return f'<div class="charttitle">{esc(title)}</div><div class="chartsub">{esc(sub)}</div>'


# --- chart primitives -------------------------------------------------------
def _axis(lo, hi, n=4):
    """A rounded [lo, hi] and exactly n+1 ticks, so two axes can share gridlines."""
    if hi <= lo:
        hi = lo + max(abs(lo) * 0.1, 1)
    step0 = (hi - lo) / n
    mag = 10 ** math.floor(math.log10(step0))
    for mult in (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10, 12, 15, 20, 25, 40, 50):
        step = mult * mag
        base = math.floor(lo / step) * step
        if base + n * step >= hi - 1e-9:
            return base, base + n * step, [base + i * step for i in range(n + 1)]
    return lo, hi, [lo + i * (hi - lo) / n for i in range(n + 1)]


def _ord(d):
    return dt.date.fromisoformat(d).toordinal()


def ts_chart(lines, *, aria="", W=720, H=252, n_ticks=4, x_ticks=4,
             left_fmt="{:.0f}", right_fmt="{:.0f}",
             left_pad=(0.06, 0.10), right_pad=(0.06, 0.10), left_range=None):
    """Paths through time.

    Each line: label, points [(iso date, value)], colour, and optionally
    axis ('left'|'right'), scale, fill, dash, end_fmt, mark_max.

    A right-hand axis shares the left axis's gridlines rather than drawing its
    own, so the two scales cannot be read as though they were one.
    """
    lines = [l for l in lines if l.get("points")]
    if not lines:
        return ""
    has_right = any(l.get("axis") == "right" for l in lines)
    PAD_L, TOP, PAD_B = 52, 22, 30
    PAD_R = 54 if has_right else 16

    xs = [_ord(d) for l in lines for d, _ in l["points"]]
    x0, x1 = min(xs), max(xs)
    X = lambda d: PAD_L + (_ord(d) - x0) / max(x1 - x0, 1) * (W - PAD_L - PAD_R)

    def scaled(line):
        s = line.get("scale", 1)
        return [(d, v * s) for d, v in line["points"]]

    def bounds(side, pad):
        vals = [v for l in lines if l.get("axis", "left") == side for _, v in scaled(l)]
        if not vals:
            return None
        lo, hi = min(vals), max(vals)
        span = (hi - lo) or abs(hi) or 1
        return _axis(lo - span * pad[0], hi + span * pad[1], n_ticks)

    if left_range:      # a bounded quantity — a share cannot run past 100%
        l_lo, l_hi = left_range
        l_ticks = [l_lo + i * (l_hi - l_lo) / n_ticks for i in range(n_ticks + 1)]
    else:
        l_lo, l_hi, l_ticks = bounds("left", left_pad)
    r = bounds("right", right_pad) if has_right else None
    Y = lambda v: (H - PAD_B) - (v - l_lo) / (l_hi - l_lo) * (H - PAD_B - TOP)
    Yr = (lambda v: (H - PAD_B) - (v - r[0]) / (r[1] - r[0]) * (H - PAD_B - TOP)) if r else None

    grid = "".join(f'<line class="ax" stroke-dasharray="2 4" opacity=".5" x1="{PAD_L}" '
                   f'y1="{Y(t):.1f}" x2="{W-PAD_R}" y2="{Y(t):.1f}"></line>' for t in l_ticks)
    gtext = "".join(f'<text x="{PAD_L-8}" y="{Y(t)+4:.1f}">{left_fmt.format(t)}</text>'
                    for t in l_ticks)
    rtext = ("".join(f'<text x="{W-PAD_R+8}" y="{Y(l):.1f}">{right_fmt.format(t)}</text>'
                     for l, t in zip(l_ticks, r[2]))) if r else ""

    body = []
    for line in lines:
        pts = scaled(line)
        y = Yr if line.get("axis") == "right" else Y
        colour = f'var(--{line["colour"]})'
        path = " ".join(f"{X(d):.1f},{y(v):.1f}" for d, v in pts)
        if line.get("fill"):
            floor = H - PAD_B
            body.append(f'<polygon points="{X(pts[0][0]):.1f},{floor} {path} '
                        f'{X(pts[-1][0]):.1f},{floor}" fill="{colour}" opacity=".10"></polygon>')
        dash = ' stroke-dasharray="5 4"' if line.get("dash") else ""
        body.append(f'<polyline points="{path}" fill="none" stroke="{colour}" '
                    f'stroke-width="{line.get("width", 2.2)}" stroke-linejoin="round"'
                    f' stroke-linecap="round"{dash}></polyline>')
        if line.get("mark_max"):
            md, mv = max(pts, key=lambda p: p[1])
            body.append(
                f'<circle cx="{X(md):.1f}" cy="{y(mv):.1f}" r="4" fill="var(--muted)"></circle>'
                f'<text class="dotlabel" fill="var(--muted)" text-anchor="start" '
                f'x="{X(md)+8:.1f}" y="{y(mv)+4:.1f}">'
                f'{line.get("end_fmt", "{:.0f}").format(mv)} peak</text>')
        ed, ev = pts[-1]
        body.append(
            f'<circle cx="{X(ed):.1f}" cy="{y(ev):.1f}" r="5" fill="{colour}" '
            f'stroke="var(--surface)" stroke-width="2"></circle>'
            f'<text class="dotlabel" fill="{colour}" text-anchor="end" '
            f'x="{X(ed)-9:.1f}" y="{y(ev)+4:.1f}">'
            f'{line.get("end_fmt", "{:.0f}").format(ev)}</text>')

    step = (x1 - x0) / max(x_ticks - 1, 1)
    xlab = "".join(
        f'<text x="{PAD_L + i/(x_ticks-1)*(W-PAD_L-PAD_R):.1f}" y="{H-9}">'
        f'{dt.date.fromordinal(int(x0 + step*i)).isoformat()[:7]}</text>'
        for i in range(x_ticks))

    return f'''<div class="svgwrap"><svg viewBox="0 0 {W} {H}" role="img" aria-label="{esc(aria)}">
<g class="axtext" text-anchor="end">{gtext}</g>
<g class="axtext" text-anchor="start">{rtext}</g>{grid}
{"".join(body)}
<line class="ax" x1="{PAD_L}" y1="{H-PAD_B}" x2="{W-PAD_R}" y2="{H-PAD_B}"></line>
<g class="axtext" text-anchor="middle">{xlab}</g>
</svg></div>'''


def curve_chart(rows, tenors, aria="", W=720, H=262):
    """A term structure at several dates.

    rows: list of (values dict, colour, style) oldest first, newest last.
    tenors: list of (key, label).

    Point labels are placed by sorting the values at each tenor and offsetting
    from the top down, so three lines that cross — which is the interesting
    case — never collide.
    """
    vals = [v[k] for v, _, _ in rows for k, _ in tenors]
    lo, hi, ticks = _axis(min(vals) - 0.35, max(vals) + 0.35, 4)
    PAD_L, PAD_R, TOP, BOT = 52, 18, 34, H - 56
    n = len(tenors)
    X = lambda i: PAD_L + i / max(n - 1, 1) * (W - PAD_L - PAD_R)
    Y = lambda v: BOT - (v - lo) / (hi - lo) * (BOT - TOP)

    grid = "".join(f'<line class="ax" stroke-dasharray="2 4" opacity=".5" x1="{PAD_L}" '
                   f'y1="{Y(t):.1f}" x2="{W-PAD_R}" y2="{Y(t):.1f}"></line>' for t in ticks)
    gtext = "".join(f'<text x="{PAD_L-8}" y="{Y(t)+4:.1f}">{t:.1f}</text>' for t in ticks)

    body = []
    for values, colour, style in rows:
        pts = " ".join(f"{X(i):.1f},{Y(values[k]):.1f}" for i, (k, _) in enumerate(tenors))
        dash = ' stroke-dasharray="5 4"' if style.get("dash") else ""
        body.append(f'<polyline points="{pts}" fill="none" stroke="var(--{colour})" '
                    f'stroke-width="{style.get("width", 2.2)}" stroke-linejoin="round"'
                    f'{dash}></polyline>')
        r = style.get("r", 4.5)
        body.append(f'<g fill="var(--{colour})" stroke="var(--surface)" stroke-width="1.5">'
                    + "".join(f'<circle cx="{X(i):.1f}" cy="{Y(values[k]):.1f}" r="{r}"></circle>'
                              for i, (k, _) in enumerate(tenors)) + "</g>")

    # label placement: at each tenor, top point labelled above, the rest below
    labels = []
    for i, (k, _) in enumerate(tenors):
        stack = sorted(rows, key=lambda row: Y(row[0][k]))
        for slot, (values, colour, style) in enumerate(stack):
            dy = (-12, 16, 30, 44)[min(slot, 3)]
            weight = "600" if style.get("width", 2.2) > 2.3 else "400"
            labels.append(
                f'<text class="dotlabel" fill="var(--{colour})" text-anchor="middle" '
                f'font-weight="{weight}" x="{X(i):.1f}" y="{Y(values[k])+dy:.1f}">'
                f'{values[k]:.2f}</text>')

    xlab = "".join(f'<text x="{X(i):.1f}" y="{H-14}">{esc(label)}</text>'
                   for i, (_, label) in enumerate(tenors))

    return f'''<div class="svgwrap"><svg viewBox="0 0 {W} {H}" role="img" aria-label="{esc(aria)}">
<g class="axtext" text-anchor="end">{gtext}</g>{grid}
<line class="ax" x1="{PAD_L}" y1="{BOT}" x2="{W-PAD_R}" y2="{BOT}"></line>
<line class="ax" x1="{PAD_L}" y1="{TOP}" x2="{PAD_L}" y2="{BOT}"></line>
{"".join(body)}{"".join(labels)}
<g class="axtext" text-anchor="middle">{xlab}</g>
</svg></div>'''


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
UST_TENORS = [("m1", "1 month"), ("y2", "2 year"), ("y10", "10 year"), ("y30", "30 year")]
JGB_TENORS = [("y1", "1 year"), ("y2", "2 year"), ("y10", "10 year"), ("y30", "30 year")]
CURVE_STYLE = [("yr3_ago", "muted", {"width": 1.8, "r": 3.6, "dash": True}),
               ("yr_ago", "gold", {"width": 2.1, "r": 4.2}),
               ("now", "accent", {"width": 2.8, "r": 5.4})]


def curve_block(curves, tenors, what):
    rows = [(curves[key], colour, style) for key, colour, style in CURVE_STYLE]
    aria = "; ".join(
        f'{label} {curves["yr3_ago"][k]:.2f} in {curves["yr3_ago"]["date"]}, '
        f'{curves["yr_ago"][k]:.2f} in {curves["yr_ago"]["date"]}, '
        f'{curves["now"][k]:.2f} in {curves["now"]["date"]}' for k, label in tenors)
    return curve_chart(rows, tenors, aria=f"{what} yield curve. {aria}")


def render(s):
    r = gauges.read(s)
    g1, g2, g3 = r["gauges"]
    m1, m2, m3 = g1.metrics, g2.metrics, g3.metrics
    gold = r["gold"]
    kr, jp = s["asia"]["korea"], s["asia"]["japan"]
    ny, ay, a3 = s["yields"]["now"], s["yields"]["yr_ago"], s["yields"]["yr3_ago"]
    hz = s.get("window_years", 3)
    hs = kr["housing"]
    fed = s["fed"]
    jy = jp["yields"]

    tiles = "".join(
        f'<div class="tile"><span class="g">Gauge {i} · {n}</span>{pill(g.status)}'
        f'<span class="n">{esc(g.headline)}</span></div>'
        for i, (g, n) in enumerate(
            zip(r["gauges"], ["Debt service", "Supply vs demand", "Monetization"]), 1))

    notes = lambda g: "".join(f'<div class="note"><p>{esc(n)}</p></div>' for n in g.notes)

    fed_chart = ts_chart(
        [{"label": "Fed balance sheet", "points": fed["monthly"], "colour": "accent",
          "scale": 1 / 1e6, "fill": True, "end_fmt": "${:.2f}T", "mark_max": True,
          "width": 2.4}],
        left_fmt="${:.1f}T", x_ticks=5,
        aria=(f"Federal Reserve total assets, month-end, {fed['monthly'][0][0]} to "
              f"{fed['monthly'][-1][0]}: peak ${fed['peak_usd_mn']/1e6:.2f}T in "
              f"{fed['peak_date']}, latest ${fed['balance_sheet_usd_mn']/1e6:.2f}T"))

    buffer_chart = ts_chart(
        [{"label": "Fixed share", "points": kr["fixed_share_series"], "colour": "accent",
          "end_fmt": "{:.1f}%", "width": 2.4, "mark_max": True},
         {"label": "가계신용", "points": kr["household_credit_series"], "colour": "crit",
          "axis": "right", "scale": 1 / 1000, "end_fmt": "{:,.0f}조", "width": 2.2}],
        left_fmt="{:.0f}%", right_fmt="{:,.0f}조", x_ticks=4, left_range=(20, 100),
        aria=(f"Share of new Korean mortgages written at a fixed rate against total "
              f"household credit, {kr['fixed_share_series'][0][0]} to "
              f"{kr['fixed_share_date']}: fixed share {kr['fixed_share_peak']:.1f}% to "
              f"{kr['fixed_share']:.1f}%, 가계신용 "
              f"{kr['household_credit_series'][0][1]/1000:,.0f}조 to "
              f"{kr['household_credit']/1000:,.0f}조"))

    housing_chart = ts_chart(
        [{"label": "실거래", "points": hs["series"]["real"], "colour": "accent",
          "end_fmt": "{:.0f}", "width": 2.4},
         {"label": "매매", "points": hs["series"]["sale"], "colour": "gold",
          "end_fmt": "{:.0f}"},
         {"label": "전세", "points": hs["series"]["jeonse"], "colour": "ok",
          "end_fmt": "{:.0f}"},
         {"label": "월세", "points": hs["series"]["wolse"], "colour": "muted",
          "end_fmt": "{:.0f}"}],
        left_fmt="{:.0f}", x_ticks=4, left_pad=(0.06, 0.03),
        aria=(f"Seoul apartment indices rebased to 100 at {hs['window'][0]}, through "
              f"{hs['window'][1]}: 실거래 {100+hs['chg_pct']['real']:.0f}, 매매 "
              f"{100+hs['chg_pct']['sale']:.0f}, 전세 {100+hs['chg_pct']['jeonse']:.0f}, "
              f"월세 {100+hs['chg_pct']['wolse']:.0f}"))

    body = f'''<div class="wrap">
<header class="top">
  <span class="eyebrow">Ray Dalio · How Countries Go Broke · gauge readings</span>
  <h1>Big Debt Cycle Monitor</h1>
  <p class="lede">Dalio says the late stage of a debt cycle is measurable, and that
  almost nobody measures it. These are his three gauges plus his market-action
  markers, read against live data — including where the tape disagrees with the
  narrative.</p>
  <div class="stamp"><span>Data as of <strong class="num">{s["as_of"]}</strong></span>
  <span>Fiscal: US Treasury</span><span>Rates: US Treasury &amp; 財務省</span>
  <span>Korea: 한국은행 · 한국부동산원</span></div>
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
    <figure>{chart_head("The repricing pipeline",
        "What Treasury pays on its stock of debt, against what the market charges today")}
    {legend(("accent", "Average rate paid"), ("gold", "Market rate today"),
            ("gold", "Committed repricing gap", "ghost"))}
    {gap_scale(m1["avg_rate"], ny["y10"], ny["y30"])}
    <figcaption>Roughly $10T of principal rolls every year. Each maturity that rolls
    moves the average rate paid toward the market rate — the gap is arithmetic
    already committed, not a forecast.</figcaption></figure>
  </div>
  {notes(g1)}
</section>

<section>{sechead("GAUGE 2", "Selling relative to demand")}
  <p>Dalio's market signature for this stage is rates rising <em>led by the long
  end</em>. That is a testable claim, so the tracker tests it — on twelve months
  and on {hz} years, because the two horizons currently disagree.</p>
  <div class="card striped s-{PILL[g2.status]}">
    <figure>{chart_head("US Treasury curve, three dates",
        f'{a3["date"]} · {ay["date"]} · {ny["date"]}, percent')}
    {legend(("accent", ny["date"]), ("gold", ay["date"]),
            ("muted", a3["date"], "dashed"))}
    {curve_block(s["yields"], UST_TENORS, "US Treasury")}
    <figcaption>Read left to right, the curve un-inverted. Three years ago the
    2-year paid {a3["y2"]:.2f}% against the 30-year's {a3["y30"]:.2f}% — money was
    dearest at the front. Today the 30-year pays {ny["y30"]:.2f}% and the 2-year
    {ny["y2"]:.2f}%. Over {hz} years the long end rose {m2["d30_3y_bp"]:+.0f}bp
    against the 2-year's {m2["d2_3y_bp"]:+.0f}bp; over the last twelve,
    {m2["d30_bp"]:+.0f}bp against {m2["d2_bp"]:+.0f}bp.</figcaption></figure>
  </div>
  {metrics(
      metric("30-year", f"{m2['y30']:.2f}%",
             f"{m2['d30_bp']:+.0f}bp over 12m · {m2['d30_3y_bp']:+.0f}bp over {hz}y"),
      metric("2-year", f"{m2['y2']:.2f}%",
             f"{m2['d2_bp']:+.0f}bp over 12m · {m2['d2_3y_bp']:+.0f}bp over {hz}y"),
      metric("30y − 2y", f"{m2['curve_bp']:+.0f}bp",
             f"{m2['curve_bp_3y_ago']:+.0f}bp {hz}y ago · {m2['curve_bp_ago']:+.0f}bp a year ago"),
      metric(f"Long end led, {hz}y", "Yes" if m2["long_end_leads_3y"] else "No",
             f"By {m2['d30_3y_bp'] - m2['d2_3y_bp']:+.0f}bp · "
             f"{m2['d30_bp'] - m2['d2_bp']:+.0f}bp over 12m"))}
  {notes(g2)}
</section>

<section>{sechead("GAUGE 3", "Central-bank monetization")}
  <p>The gauge that decides which exit the cycle takes — and the only one of the
  three whose reading is a <em>slope</em> rather than a level. Scored over
  {m3["trend_months"]} months, because the weekly H.4.1 print swings on repo and
  Treasury-account operations and would flip this gauge in both directions while
  the trend did one thing.</p>
  <div class="card striped s-{PILL[g3.status]}">{pill(g3.status)}
  {metrics(
      metric("Fed balance sheet", f"${m3['balance_sheet']/1e6:.2f}T",
             f"{m3['off_peak']:+.1%} versus the {fed['peak_date'][:7]} peak"),
      metric(f"Change over {m3['trend_months']} months", f"{m3['trend_pct']:+.1f}%",
             f"{m3['wow_change']/1e3:+,.1f}bn on the week — noise at this scale"),
      metric("Since the trough", f"{m3['since_trough_pct']:+.1f}%",
             f"Bottomed ${m3['trough']/1e6:.2f}T in {m3['trough_date'][:7]}, "
             f"{m3['months_since_trough']} months ago"),
      metric("Change over 12 months",
             f"{(fed['balance_sheet_usd_mn'] - fed['yr_ago_usd_mn'])/1e6:+.2f}T",
             f"From ${fed['yr_ago_usd_mn']/1e6:.2f}T"))}
    <figure>{chart_head("Federal Reserve total assets",
        f"Month-end, {fed['monthly'][0][0][:7]} to {fed['monthly'][-1][0][:7]}")}
    {fed_chart}
    <figcaption>The shape is the reading, and the shape changed. Quantitative
    tightening took ${(fed["peak_usd_mn"] - m3["trough"])/1e6:.2f}T off the balance
    sheet between {fed["peak_date"][:7]} and {m3["trough_date"][:7]}; since then the
    line has turned and risen {m3["since_trough_pct"]:+.1f}%. A single week's print
    would not show that in either direction — this is the reading the previous
    version of this page got wrong by testing week over week.</figcaption></figure>
  {notes(g3)}
  </div>
</section>

<section>{sechead("MARKER", "The measuring stick")}
  <p>A currency's decline is invisible measured against other currencies that are
  declining too. Gold rose {gold["gold_yoy_pct"]:.1f}% in dollars over twelve months.</p>
  <div class="card striped s-crit">
    <figure>{chart_head("What each currency lost against gold", f'Twelve months to {s["as_of"]}')}
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

<section>{sechead("MARKER", "The Korean buffer")}
  <p>A US homeowner on a thirty-year fixed mortgage is short the bond: inflation
  transfers wealth from the lender to them, which is why American housing absorbs
  a rate shock through volume rather than price. Whether a Korean household has
  any version of that buffer is a measurable question, and the answer has changed
  fast — while the stock of debt the buffer was protecting kept growing.</p>

  <div class="card striped s-crit">
    <figure>{chart_head("The buffer against the balance it protects",
        f'고정금리 비중, 예금은행 주택담보대출 신규취급액 (left) · 가계신용 잔액 (right) · '
        f'{kr["fixed_share_series"][0][0][:7]} to {kr["fixed_share_date"][:7]}')}
    {legend(("accent", "Fixed share of new mortgages (left)"),
            ("crit", "가계신용, 조원 (right)"))}
    {buffer_chart}
    <figcaption>Two series, two axes, one question. Fixed-rate lending has fallen
    from {kr['fixed_share_peak']:.1f}% of new mortgages in {kr['fixed_share_peak_date'][:7]}
    to {kr['fixed_share']:.1f}%, most of it in the last eight months as the Bank of
    Korea began tightening. Over the same window 가계신용 rose
    {kr['household_credit_chg_pct']:+.1f}% to {kr['household_credit']/1000:,.0f}조원. The
    share being repriced is rising against a balance that is also rising. Note that
    Korean 고정형 is typically 혼합형 — fixed five years, then floating — so the
    buffer was always far shorter-dated than the US thirty-year.</figcaption></figure>
  </div>

  {metrics(
      metric("Fixed share, new loans", f"{kr['fixed_share']:.1f}%",
             f"From {kr['fixed_share_yr_ago']:.1f}% a year ago"),
      metric("Fixed premium", f"{kr['fixed_premium_pp']:+.2f}pp",
             f"고정 {kr['mortgage_fixed']:.2f}% vs 변동 {kr['mortgage_floating']:.2f}%"),
      metric("BOK base rate", f"{kr['base_rate']:.2f}%",
             f"As of {kr['base_rate_date'][:7]}"),
      metric("가계신용", f"{kr['household_credit']/1000:,.0f}조",
             f"{kr['household_credit_chg_pct']:+.1f}% over {hz} years"))}

  <div class="note"><p>The premium flipped sign. Through 2025 fixed-rate mortgages
  were <em>cheaper</em> than floating and roughly nine in ten new borrowers took
  them; fixed now costs {kr['fixed_premium_pp']:+.2f}pp more and fewer than one in three
  do. Lenders are pricing the rate path before borrowers are — which is what the
  withdrawal of a buffer looks like while it is happening.</p></div>

  <div class="card striped s-warn" style="margin-top:22px">
    <figure>{chart_head("Seoul apartments: price, 전세, 월세",
        f'한국부동산원 monthly indices, rebased to 100 at {hs["window"][0][:7]} · '
        f'through {hs["window"][1][:7]}')}
    {legend(("accent", "실거래가격지수"), ("gold", "매매가격지수 (조사)"),
            ("ok", "전세가격지수"), ("muted", "월세통합가격지수"))}
    {housing_chart}
    <figcaption>Ranked, and the ranking is the finding: what buyers actually
    transacted at rose {hs['chg_pct']['real']:.1f}% over {hz} years, the survey index
    {hs['chg_pct']['sale']:.1f}%, 전세 {hs['chg_pct']['jeonse']:.1f}% and 월세
    {hs['chg_pct']['wolse']:.1f}%. Prices outran the rent on the same apartments by
    {hs['jeonse_lag_pp']:.1f}pp against 전세 and
    {hs['chg_pct']['sale'] - hs['chg_pct']['wolse']:.1f}pp against 월세. A price
    rising faster than the rent it can earn is not being paid for out of income —
    it is being paid for out of credit, which is the same buffer question in a
    different denominator.</figcaption></figure>
  </div>

  {metrics(
      metric("실거래가격지수", f"{hs['chg_pct']['real']:+.1f}%", f"Over {hz} years, 서울 아파트"),
      metric("매매가격지수", f"{hs['chg_pct']['sale']:+.1f}%",
             f"Survey lags transactions by {hs['survey_gap_pp']:.1f}pp"),
      metric("전세가격지수", f"{hs['chg_pct']['jeonse']:+.1f}%",
             f"{hs['jeonse_lag_pp']:.1f}pp behind 매매"),
      metric("월세통합가격지수", f"{hs['chg_pct']['wolse']:+.1f}%",
             f"{hs['wolse_lag_pp']:.1f}pp behind 전세"))}
</section>

<section>{sechead("MARKER", "Japan, the same measurement")}
  <p>Japan carries roughly 215% debt-to-GDP on the assumption that yields stay near
  zero. That assumption is being withdrawn at the long end first, which is exactly
  the shape Gauge 2 looks for — so it is worth reading on the same axes as the US
  curve rather than as a single 10-year print.</p>
  <div class="card striped s-crit">
    <figure>{chart_head("JGB curve, three dates",
        f'{jy["yr3_ago"]["date"]} · {jy["yr_ago"]["date"]} · {jy["now"]["date"]}, percent')}
    {legend(("accent", jy["now"]["date"]), ("gold", jy["yr_ago"]["date"]),
            ("muted", jy["yr3_ago"]["date"], "dashed"))}
    {curve_block(jy, JGB_TENORS, "Japanese government bond")}
    <figcaption>Three years ago the 2-year JGB paid {jy["yr3_ago"]["y2"]:.2f}% and the
    30-year {jy["yr3_ago"]["y30"]:.2f}%. Today they pay {jy["now"]["y2"]:.2f}% and
    {jy["now"]["y30"]:.2f}%. The 30-year has risen
    {(jy["now"]["y30"] - jy["yr3_ago"]["y30"])*100:+.0f}bp over {hz} years and
    {jp["jgb30_chg_12m"]*100:+.0f}bp over twelve months — a bond market that spent a
    generation at zero repricing duration in public. Source: 財務省 daily par
    yields, the issuer's own numbers.</figcaption></figure>
  </div>
  {metrics(
      metric("30-year JGB", f"{jy['now']['y30']:.2f}%",
             f"{jp['jgb30_chg_12m']*100:+.0f}bp over 12 months"),
      metric("10-year JGB", f"{jy['now']['y10']:.2f}%",
             f"{jp['jgb10_chg_12m']*100:+.0f}bp over 12 months"),
      metric("30y − 2y", f"{(jy['now']['y30'] - jy['now']['y2'])*100:+.0f}bp",
             f"From {(jy['yr3_ago']['y30'] - jy['yr3_ago']['y2'])*100:+.0f}bp {hz} years ago"),
      metric("As of", jy["now"]["date"], "Daily, 財務省"))}
  <div class="note"><p>Dalio's Q7 asks what happens when the country that proved
  large debts can be carried cheaply stops being able to. The US 30-year is
  {ny['y30']:.2f}% and the JGB 30-year is {jy['now']['y30']:.2f}%. The gap between
  them has closed to {(ny['y30'] - jy['now']['y30'])*100:.0f}bp from
  {(a3['y30'] - jy['yr3_ago']['y30'])*100:.0f}bp {hz} years ago — which is the
  hedged-yield arithmetic that has historically sent Japanese capital abroad,
  running in reverse.</p></div>
</section>

<footer><p>Gauge definitions from Ray Dalio, <em>How Countries Go Broke: The Big
Cycle</em> (2025). Readings computed from US Treasury, Federal Reserve, 財務省, ECB,
한국은행 and 한국부동산원 primary sources. A monitor, not a forecast, and not
investment advice.</p></footer>
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
