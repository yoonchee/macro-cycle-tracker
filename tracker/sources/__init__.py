"""Source registry.

Imports are lazy so a missing optional dependency (yfinance, say) disables one
source instead of breaking the whole run. Treasury is the backbone and needs no
credentials or third-party packages beyond requests.
"""
import importlib

REGISTRY_SPEC = {
    "treasury": ("treasury", "fetch_all"),  # no key needed — the backbone
    "fred":     ("fred", "fetch_all"),      # needs FRED_API_KEY
    "market":   ("market", "fetch_all"),    # yfinance, no key
    "korea":    ("korea", "fetch_all"),     # needs ECOS_API_KEY
}


def _loader(mod, fn):
    def call(*a, **kw):
        m = importlib.import_module(f".{mod}", __package__)
        return getattr(m, fn)(*a, **kw)
    return call


REGISTRY = {name: _loader(*spec) for name, spec in REGISTRY_SPEC.items()}
