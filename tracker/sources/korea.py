"""Korea — the household-debt and housing channel.

Bank of Korea ECOS  : https://ecos.bok.or.kr/api/   (free key)
한국부동산원 R-ONE   : https://www.data.go.kr        (free key)

Korea's exposure to this cycle is not sovereign — government debt is moderate.
It runs through floating-rate household debt, 전세, and the won.
"""
import requests
from ..config import ECOS_API_KEY, REB_API_KEY, UA, TIMEOUT

ECOS = "https://ecos.bok.or.kr/api/StatisticSearch/{key}/json/kr/1/{n}/{code}/{cycle}/{start}/{end}/{item}"

# ECOS statistic codes. Verify against the ECOS 통계코드 browser — BOK renumbers.
ECOS_SERIES = {
    "kr.base_rate":       ("722Y001", "M", "0101000"),   # 한국은행 기준금리
    "kr.household_credit":("151Y005", "Q", "1111000"),   # 가계신용 총액
    "kr.mortgage_rate":   ("121Y002", "M", "BECBLA03"),  # 예금은행 주택담보대출 금리
    "kr.cpi":             ("901Y009", "M", "0"),
}


def _ecos(code, cycle, item, start, end, n=500):
    url = ECOS.format(key=ECOS_API_KEY, n=n, code=code, cycle=cycle,
                      start=start, end=end, item=item)
    r = requests.get(url, headers=UA, timeout=TIMEOUT)
    r.raise_for_status()
    body = r.json()
    if "StatisticSearch" not in body:
        raise RuntimeError(f"ECOS returned no rows for {code}: {body}")
    return body["StatisticSearch"]["row"]


def fetch_all(start="201501", end="209912"):
    if not ECOS_API_KEY:
        raise RuntimeError("ECOS_API_KEY not set — skipping Korea series")
    out = []
    for name, (code, cycle, item) in ECOS_SERIES.items():
        s, e = (start, end) if cycle == "M" else (start[:4] + "Q1", "2099Q4")
        try:
            for row in _ecos(code, cycle, item, s, e):
                d = row["TIME"]
                iso = (f"{d[:4]}-{d[4:6]}-01" if len(d) == 6 else
                       f"{d[:4]}-{ {'Q1':'01','Q2':'04','Q3':'07','Q4':'10'}.get(d[4:],'01') }-01")
                out.append({"series": name, "date": iso, "value": row["DATA_VALUE"],
                            "source": "ecos"})
        except Exception as exc:                      # one bad code shouldn't kill the run
            print(f"  ! {name}: {exc}")
    return out


def housing_note():
    """한국부동산원 weekly apartment index.

    R-ONE's open API requires a data.go.kr service key and a specific 통계표 id.
    Register, pick 주택가격동향조사 > 아파트 매매가격지수, and wire it here. Until then
    the weekly figures in data/snapshot.json are entered by hand from
    https://www.reb.or.kr/r-one/ — which is fine at a weekly cadence.
    """
    return REB_API_KEY
