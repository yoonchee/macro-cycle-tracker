#!/usr/bin/env python3
"""Fetch every wired source into the SQLite store, then report coverage.

    python refresh.py                  # everything that has credentials
    python refresh.py treasury market  # just these
    python refresh.py --coverage       # what the store already holds

Sources fail independently: a missing FRED key does not stop Treasury, which is
the backbone and needs no credentials at all.
"""
import sys
from tracker import store
from tracker.sources import REGISTRY


def main(argv):
    if "--coverage" in argv:
        for row in store.coverage():
            print(f"{row['series']:<28} {row['n']:>6} rows  {row['first']} .. {row['last']}")
        return 0

    names = [a for a in argv if not a.startswith("-")] or list(REGISTRY)
    failed = []
    for name in names:
        fn = REGISTRY.get(name)
        if not fn:
            print(f"?? unknown source: {name}"); continue
        try:
            rows = fn()
            n = store.put(rows)
            store.log(name, True, n)
            print(f"OK   {name:<10} {n:>6} rows")
        except Exception as exc:
            store.log(name, False, 0, str(exc))
            failed.append(name)
            print(f"SKIP {name:<10} {exc}")

    print("\nCoverage:")
    for row in store.coverage():
        print(f"  {row['series']:<28} {row['n']:>6}  {row['first']} .. {row['last']}")
    if failed:
        print(f"\n{len(failed)} source(s) skipped: {', '.join(failed)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
