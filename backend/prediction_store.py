"""
prediction_store.py  –  NeuroSight Persistent Prediction Cache
==============================================================
Stores the most recent prediction result for each asset as JSON on disk
so that /api/predictions/{symbol} can respond instantly without running
full ML inference on every request.

Thread-safe: all reads/writes go through _store_lock.
Prediction TTL: 8 hours (a single trading session).  After TTL the
next request triggers a fresh prediction, which is then cached again.

Stored file: backend/predictions_cache.json
Format:
{
  "AAPL": {
    "generated_at": "2026-06-22T09:30:00",
    "source":        "retrain" | "manual" | "api",
    "data":          { ...predict_asset() result... }
  },
  ...
}
"""

import json
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

# ── storage path ─────────────────────────────────────────────────────
_STORE_FILE = Path(__file__).resolve().parent / "predictions_cache.json"
_store_lock = threading.Lock()

# Predictions older than this are considered stale and will be
# re-generated on the next GET /api/predictions/{symbol} request.
_PREDICTION_TTL_HOURS = 8


# =====================================================================
#  Low-level read / write
# =====================================================================

def _read_store() -> dict:
    """Read raw store dict from disk.  Returns {} on any error."""
    try:
        if _STORE_FILE.exists():
            return json.loads(_STORE_FILE.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def _write_store(store: dict) -> None:
    """Write store dict to disk atomically (write to .tmp then rename)."""
    tmp = _STORE_FILE.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(store, indent=2, default=str), encoding="utf-8")
        tmp.replace(_STORE_FILE)
    except Exception as exc:
        print(f"[prediction_store] write error: {exc}")
        try:
            tmp.unlink(missing_ok=True)
        except Exception:
            pass


# =====================================================================
#  Public API
# =====================================================================

def save_prediction(ticker: str, data: dict, source: str = "api") -> None:
    """Persist a prediction result for *ticker*.

    Args:
        ticker: e.g. "AAPL"
        data:   the dict returned by predict_asset()
        source: "retrain" | "manual" | "api"  (informational only)
    """
    ticker = ticker.upper()
    entry = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source": source,
        "data": data,
    }
    with _store_lock:
        store = _read_store()
        store[ticker] = entry
        _write_store(store)


def load_prediction(ticker: str, max_age_hours: float = _PREDICTION_TTL_HOURS) -> Optional[dict]:
    """Return the cached prediction for *ticker* if it is fresh enough.

    Returns:
        dict with keys: generated_at, source, data
        None if not cached or older than max_age_hours
    """
    ticker = ticker.upper()
    with _store_lock:
        store = _read_store()

    entry = store.get(ticker)
    if not entry:
        return None

    try:
        generated_at = datetime.fromisoformat(entry["generated_at"])
        if datetime.now() - generated_at > timedelta(hours=max_age_hours):
            return None   # stale
    except Exception:
        return None

    return entry


def load_all_predictions(max_age_hours: float = _PREDICTION_TTL_HOURS) -> Dict[str, Optional[dict]]:
    """Return cached predictions for all 4 assets.

    Keys are always present.  Value is None when not cached / stale.
    """
    from prediction_engine import ASSET_CONFIG  # lazy to avoid circular import
    result = {}
    for ticker in ASSET_CONFIG:
        result[ticker] = load_prediction(ticker, max_age_hours=max_age_hours)
    return result


def refresh_prediction(ticker: str, source: str = "api") -> dict:
    """Run predict_asset() for *ticker* and persist the result.

    Returns the fresh prediction dict (or a dict with 'error' key on failure).
    Safe to call from background threads.
    """
    ticker = ticker.upper()
    try:
        from prediction_engine import predict_asset
        result = predict_asset(ticker, period="7d")
        save_prediction(ticker, result, source=source)
        print(f"[prediction_store] cached {ticker} prediction  source={source}  "
              f"price=${result.get('current_price', '?')}  "
              f"predicted=${result.get('predicted_price', '?')}")
        return result
    except Exception as exc:
        print(f"[prediction_store] ERROR refreshing {ticker}: {exc}")
        return {"ticker": ticker, "error": str(exc)}


def refresh_all_predictions(source: str = "retrain") -> dict:
    """Run predict_asset() for all 4 assets and persist results.

    Returns dict: { ticker: result_or_error_dict }
    """
    from prediction_engine import ASSET_CONFIG  # lazy
    results = {}
    for ticker in ASSET_CONFIG:
        results[ticker] = refresh_prediction(ticker, source=source)
    return results


# =====================================================================
#  Status helper (used by /api/retrain/status)
# =====================================================================

def get_system_status() -> dict:
    """Return a summary of model file ages and cached prediction freshness."""
    from prediction_engine import ASSET_CONFIG, MODELS_DIR  # lazy

    tickers_status = {}
    for ticker, cfg in ASSET_CONFIG.items():
        model_path = MODELS_DIR / cfg["model_file"]
        feat_path  = MODELS_DIR / cfg["scaler_feat"]
        tgt_path   = MODELS_DIR / cfg["scaler_tgt"]

        # Model file info
        if model_path.exists():
            mtime       = datetime.fromtimestamp(model_path.stat().st_mtime)
            model_age_d = (datetime.now() - mtime).days
            model_ok    = model_age_d <= 7
        else:
            mtime       = None
            model_age_d = -1
            model_ok    = False

        # Scaler existence
        scalers_ok = feat_path.exists() and tgt_path.exists()

        # Cached prediction info
        cached = load_prediction(ticker, max_age_hours=_PREDICTION_TTL_HOURS)
        if cached:
            pred_age_s = int(
                (datetime.now() - datetime.fromisoformat(cached["generated_at"])).total_seconds()
            )
            pred_price  = cached["data"].get("predicted_price")
            pred_source = cached["source"]
            pred_fresh  = True
        else:
            pred_age_s  = None
            pred_price  = None
            pred_source = None
            pred_fresh  = False

        tickers_status[ticker] = {
            "model_exists":       model_path.exists(),
            "scalers_exist":      scalers_ok,
            "model_last_trained": mtime.isoformat(timespec="seconds") if mtime else None,
            "model_age_days":     model_age_d,
            "model_fresh":        model_ok,
            "architecture":       cfg["architecture"],
            "predict_mode":       cfg.get("predict_mode", "price"),
            "prediction_cached":  pred_fresh,
            "prediction_age_s":   pred_age_s,
            "predicted_price":    pred_price,
            "prediction_source":  pred_source,
        }

    return {
        "checked_at":    datetime.now().isoformat(timespec="seconds"),
        "cache_file":    str(_STORE_FILE),
        "ttl_hours":     _PREDICTION_TTL_HOURS,
        "assets":        tickers_status,
    }
