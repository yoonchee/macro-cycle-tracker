"""SQLite time-series store.

One table, one row per (series, date). Re-running a fetch is idempotent, so the
history accumulates across refreshes even though most sources only serve the
recent window.
"""
import sqlite3
from contextlib import contextmanager
from .config import DB

SCHEMA = """
CREATE TABLE IF NOT EXISTS obs (
    series TEXT NOT NULL,
    date   TEXT NOT NULL,
    value  REAL,
    unit   TEXT,
    source TEXT,
    fetched_at TEXT DEFAULT (datetime('now')),
    PRIMARY KEY (series, date)
);
CREATE INDEX IF NOT EXISTS idx_obs_series_date ON obs(series, date DESC);

CREATE TABLE IF NOT EXISTS fetch_log (
    source TEXT NOT NULL,
    ran_at TEXT DEFAULT (datetime('now')),
    ok     INTEGER NOT NULL,
    n_rows INTEGER,
    detail TEXT
);
"""


@contextmanager
def conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    try:
        c.executescript(SCHEMA)
        yield c
        c.commit()
    finally:
        c.close()


def put(rows):
    """rows: iterable of dicts with series/date/value and optional unit/source."""
    rows = list(rows)
    if not rows:
        return 0
    with conn() as c:
        c.executemany(
            "INSERT INTO obs (series,date,value,unit,source) VALUES (?,?,?,?,?) "
            "ON CONFLICT(series,date) DO UPDATE SET "
            "value=excluded.value, unit=excluded.unit, source=excluded.source, "
            "fetched_at=datetime('now')",
            [
                (r["series"], str(r["date"]), _f(r.get("value")),
                 r.get("unit"), r.get("source"))
                for r in rows
            ],
        )
    return len(rows)


def _f(v):
    try:
        return None if v is None or v == "" else float(v)
    except (TypeError, ValueError):
        return None


def log(source, ok, n_rows=0, detail=""):
    with conn() as c:
        c.execute(
            "INSERT INTO fetch_log (source, ok, n_rows, detail) VALUES (?,?,?,?)",
            (source, 1 if ok else 0, n_rows, detail[:500]),
        )


def latest(series, on_or_before=None):
    """Most recent non-null observation for a series."""
    q = "SELECT date, value FROM obs WHERE series=? AND value IS NOT NULL"
    args = [series]
    if on_or_before:
        q += " AND date<=?"
        args.append(on_or_before)
    q += " ORDER BY date DESC LIMIT 1"
    with conn() as c:
        r = c.execute(q, args).fetchone()
    return (r["date"], r["value"]) if r else (None, None)


def series(name, since=None):
    q = "SELECT date, value FROM obs WHERE series=? AND value IS NOT NULL"
    args = [name]
    if since:
        q += " AND date>=?"
        args.append(since)
    q += " ORDER BY date"
    with conn() as c:
        return [(r["date"], r["value"]) for r in c.execute(q, args)]


def as_of_years_ago(name, ref_date, years=1):
    """Closest observation at or before (ref_date - `years`). Returns (date, value)."""
    from datetime import date as _d
    y, m, d = (int(x) for x in str(ref_date)[:10].split("-"))
    try:
        target = _d(y - years, m, d)
    except ValueError:            # 29 Feb
        target = _d(y - years, m, d - 1)
    return latest(name, on_or_before=target.isoformat())


def as_of_a_year_ago(name, ref_date):
    return as_of_years_ago(name, ref_date, 1)


def monthly(name, since=None):
    """Last observation of each calendar month — a weekly series read as a trend."""
    out = {}
    for date, value in series(name, since=since):
        out[date[:7]] = (date, value)
    return [out[k] for k in sorted(out)]


def coverage():
    """What the store holds — useful as a first check after a refresh."""
    with conn() as c:
        return [dict(r) for r in c.execute(
            "SELECT series, COUNT(*) n, MIN(date) first, MAX(date) last "
            "FROM obs GROUP BY series ORDER BY series"
        )]
