"""Korea — the household-debt and housing channel.

Bank of Korea ECOS  : https://ecos.bok.or.kr/api/   (free key)
한국부동산원 R-ONE   : https://www.data.go.kr        (free key)

Korea's exposure to this cycle is not sovereign — government debt is moderate.
It runs through floating-rate household debt, 전세, and the won.

The fixed-versus-floating series below are the ones that matter most. A US
homeowner with a 30-year fixed mortgage is short the bond: inflation transfers
wealth from the lender to them. A Korean household on a 변동금리 mortgage has the
opposite exposure. `kr.mortgage.fixed_share` is how much of that buffer Korean
borrowers actually have, and `kr.mortgage.fixed_premium` is what it costs them.

Statistic codes are verified against the live ECOS catalogue (StatisticTableList
/ StatisticItemList). BOK renumbers tables periodically and a stale code returns
INFO-200 "해당하는 데이터가 없습니다" rather than an error, so `python -m
tracker.sources.korea --catalog <keyword>` re-discovers them.
"""
import json
import urllib.request

import requests

from ..config import ECOS_API_KEY, REB_API_KEY, UA, TIMEOUT

BASE = "https://ecos.bok.or.kr/api"

# series name -> (통계표코드, 주기, 항목코드)
ECOS_SERIES = {
    # policy and prices
    "kr.base_rate":       ("722Y001", "M", "0101000"),      # 한국은행 기준금리
    "kr.cpi":             ("901Y009", "M", "0"),            # 소비자물가지수

    # household leverage — the actual transmission channel
    "kr.household_credit": ("151Y001", "Q", "1000000"),     # 가계신용 총액
    "kr.household_loans":  ("151Y001", "Q", "1100000"),     # 가계대출

    # mortgage rates, 신규취급액 기준
    "kr.mortgage_rate":          ("121Y006", "M", "BECBLA0302"),    # 주택담보대출 전체
    "kr.mortgage_rate.fixed":    ("121Y006", "M", "BECBLA030201"),  # 고정형
    "kr.mortgage_rate.floating": ("121Y006", "M", "BECBLA030202"),  # 변동형

    # the buffer: share of NEW mortgages written at a fixed rate
    "kr.mortgage.fixed_share":    ("121Y010", "M", "LN10000"),
    "kr.mortgage.floating_share": ("121Y010", "M", "LN20000"),
}

CYCLE_START = {"M": ("201001", "209912"), "Q": ("2010Q1", "2099Q4"),
               "A": ("2010", "2099"), "D": ("20100101", "20991231")}


def _iso(t):
    """ECOS TIME -> ISO date. Handles 202607, 2026Q2, 2026, 20260731."""
    t = str(t)
    if "Q" in t:
        q = {"Q1": "01", "Q2": "04", "Q3": "07", "Q4": "10"}[t[4:]]
        return f"{t[:4]}-{q}-01"
    if len(t) == 8:
        return f"{t[:4]}-{t[4:6]}-{t[6:]}"
    if len(t) == 6:
        return f"{t[:4]}-{t[4:6]}-01"
    return f"{t[:4]}-01-01"


def _call(service, *parts, n=1000):
    url = f"{BASE}/{service}/{ECOS_API_KEY}/json/kr/1/{n}/" + "/".join(str(p) for p in parts)
    if parts:
        url += "/"
    r = requests.get(url, headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    body = r.json()
    if "RESULT" in body:                       # ECOS reports errors with HTTP 200
        res = body["RESULT"]
        raise RuntimeError(f'{res.get("CODE")}: {res.get("MESSAGE")}')
    return next(iter(body.values()))["row"]


def fetch_all():
    if not ECOS_API_KEY:
        raise RuntimeError("ECOS_API_KEY not set — skipping Korea series")
    out, failed = [], []
    for name, (code, cycle, item) in ECOS_SERIES.items():
        start, end = CYCLE_START[cycle]
        try:
            for row in _call("StatisticSearch", code, cycle, start, end, item):
                if row.get("DATA_VALUE") in (None, ""):
                    continue
                out.append({"series": name, "date": _iso(row["TIME"]),
                            "value": row["DATA_VALUE"],
                            "unit": row.get("UNIT_NAME"), "source": "ecos"})
        except Exception as exc:               # one bad code shouldn't kill the run
            failed.append(f"{name} ({code}/{item}): {exc}")
    for f in failed:
        print(f"  ! {f}")
    if failed and not out:
        raise RuntimeError("every ECOS series failed — check the key and the codes")
    return out


# --- code discovery ---------------------------------------------------------
def catalog(keyword):
    """Find 통계표 whose name contains `keyword`. Use when a code goes stale."""
    hits = [r for r in _call("StatisticTableList", n=2000)
            if keyword in (r.get("STAT_NAME") or "")]
    return [(r.get("STAT_CODE"), r.get("CYCLE"), r.get("STAT_NAME")) for r in hits]


def items(stat_code, keyword=""):
    """List 항목 within a 통계표, optionally filtered by name."""
    rows = _call("StatisticItemList", stat_code, n=300)
    return [(r.get("ITEM_CODE"), r.get("CYCLE"), r.get("ITEM_NAME"),
             r.get("START_TIME"), r.get("END_TIME"))
            for r in rows if keyword in (r.get("ITEM_NAME") or "")]


def housing_note():
    """한국부동산원 weekly apartment index.

    R-ONE's open API needs a data.go.kr service key and a specific 통계표 id.
    Register, pick 주택가격동향조사 > 아파트 매매가격지수, and wire it here. Until
    then the weekly figures in data/snapshot.json are entered by hand from
    https://www.reb.or.kr/r-one/ — fine at a weekly cadence.
    """
    return REB_API_KEY


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 2 and sys.argv[1] == "--catalog":
        for c, cy, n in catalog(sys.argv[2]):
            print(f"{c!s:<12} {cy!s:<4} {n}")
    elif len(sys.argv) > 2 and sys.argv[1] == "--items":
        for i in items(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else ""):
            print(f"{i[0]!s:<14} {i[1]!s:<4} {i[2]}  [{i[3]}~{i[4]}]")
    else:
        rows = fetch_all()
        print(f"{len(rows)} rows across {len({r['series'] for r in rows})} series")
