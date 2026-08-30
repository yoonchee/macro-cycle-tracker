import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = ROOT / "out"
DB = DATA / "history.sqlite"
SNAPSHOT = DATA / "snapshot.json"

DATA.mkdir(exist_ok=True)
OUT.mkdir(exist_ok=True)

FRED_API_KEY = os.environ.get("FRED_API_KEY", "")
ECOS_API_KEY = os.environ.get("ECOS_API_KEY", "")
REB_API_KEY = os.environ.get("REB_API_KEY", "")

UA = {"User-Agent": "macro-cycle-tracker/0.1 (personal research)"}
TIMEOUT = 30
