"""
retrain_jobs.py  –  NeuroSight Standalone Auto-Retrain Service
==============================================================
Runs INDEPENDENTLY of the Flask backend.
Retrains AAPL, NVDA, TSLA, GOLD every Sunday at 02:00 AM using
the exact architectures defined in prediction_engine.py.

Usage:
    python retrain_jobs.py            # run the scheduler loop forever
    python retrain_jobs.py --now      # retrain immediately then exit
    python retrain_jobs.py --status   # show model ages and exit

Start automatically on Windows without the backend:
    Use start_retrain_service.bat  (double-click or add to Task Scheduler)
"""

import sys
import os
import time
import argparse
import logging
from pathlib import Path
from datetime import datetime, timedelta

# ── path setup so we can import prediction_engine directly ───────────
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))


# ── logging ──────────────────────────────────────────────────────────
LOG_DIR = BACKEND_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOG_FILE = LOG_DIR / "retrain.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("retrain_service")

# ── which assets to retrain ──────────────────────────────────────────
TICKERS = ["AAPL", "NVDA", "TSLA", "GOLD"]

# ── weekly schedule: Sunday 02:00 AM ────────────────────────────────
RETRAIN_WEEKDAY = 6   # Monday=0 … Sunday=6
RETRAIN_HOUR    = 2
RETRAIN_MINUTE  = 0


def _next_run_time() -> datetime:
    """Return the next Sunday 02:00 AM from now."""
    now = datetime.now()
    days_ahead = (RETRAIN_WEEKDAY - now.weekday()) % 7
    if days_ahead == 0 and (now.hour, now.minute) >= (RETRAIN_HOUR, RETRAIN_MINUTE):
        days_ahead = 7   # already past today's run → next week
    target = (now + timedelta(days=days_ahead)).replace(
        hour=RETRAIN_HOUR, minute=RETRAIN_MINUTE, second=0, microsecond=0
    )
    return target


def run_retrain_now() -> bool:
    """Import prediction_engine and retrain all 4 models right now."""
    log.info("=" * 60)
    log.info("Auto-Retrain starting  |  tickers: %s", TICKERS)
    log.info("=" * 60)

    try:
        import prediction_engine as pe
    except Exception as exc:
        log.error("Failed to import prediction_engine: %s", exc)
        return False

    overall_ok = True
    for ticker in TICKERS:
        log.info("  Retraining %s ...", ticker)
        try:
            result = pe.retrain_asset(ticker)
            if result.get("success"):
                log.info(
                    "  [PASS] %s  MAPE=%.2f%%  MAE=%.4f  took %.0fs",
                    ticker,
                    result.get("mape", 0),
                    result.get("mae",  0),
                    result.get("elapsed_s", 0),
                )
                # Generate and cache a fresh prediction immediately after
                # successful retrain so /api/predictions/{symbol} is current.
                try:
                    from prediction_store import refresh_prediction
                    pred = refresh_prediction(ticker, source="retrain")
                    if "error" in pred:
                        log.warning("  [PRED-FAIL] %s prediction: %s", ticker, pred["error"])
                    else:
                        log.info("  [PRED-OK]  %s  predicted=$%.2f",
                                 ticker, pred.get("predicted_price", 0))
                except Exception as pred_exc:
                    log.warning("  [PRED-WARN] %s: %s", ticker, pred_exc)
            else:
                log.warning("  [FAIL] %s  error=%s", ticker, result.get("error", "unknown"))
                overall_ok = False
        except Exception as exc:
            log.error("  [ERROR] %s  %s", ticker, exc)
            overall_ok = False

    status = "COMPLETE (all passed)" if overall_ok else "COMPLETE (some failed)"
    log.info("Retrain %s\n", status)
    return overall_ok


def show_status():
    """Print model file ages AND prediction cache freshness for all 4 assets."""
    try:
        from prediction_store import get_system_status
        info = get_system_status()
        print(f"\nNeuroSight Model + Prediction Status  [{info['checked_at']}]")
        print(f"Cache file: {info['cache_file']}")
        print()
        hdr = f"{'Ticker':<6}  {'Model age':>10}  {'Fresh?':>6}  {'Pred cached':>11}  {'Pred age':>10}  {'Predicted $':>12}"
        print(hdr)
        print("-" * len(hdr))
        for ticker, s in info["assets"].items():
            age_str   = f"{s['model_age_days']}d" if s["model_age_days"] >= 0 else "MISSING"
            fresh_str = "YES" if s["model_fresh"] else ("STALE" if s["model_age_days"] >= 0 else "MISSING")
            if s["prediction_cached"]:
                pred_age  = f"{s['prediction_age_s'] // 60}m ago"
                pred_price = f"${s['predicted_price']:.2f}" if s["predicted_price"] else "N/A"
            else:
                pred_age  = "none"
                pred_price = "N/A"
            print(f"{ticker:<6}  {age_str:>10}  {fresh_str:>6}  {'YES' if s['prediction_cached'] else 'NO':>11}  {pred_age:>10}  {pred_price:>12}")
        print()
    except Exception as exc:
        # Fallback: basic model-file-only status
        print(f"(prediction_store unavailable: {exc})")
        try:
            import prediction_engine as pe
        except Exception as pe_exc:
            print(f"Cannot import prediction_engine: {pe_exc}")
            return
        print(f"\n{'Ticker':<8}  {'Model file':<35}  {'Age (days)':<12}  Status")
        print("-" * 75)
        for ticker, cfg in pe.ASSET_CONFIG.items():
            path = pe.MODELS_DIR / cfg["model_file"]
            if path.exists():
                age = (datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)).days
                status = "OK" if age <= 7 else "STALE"
            else:
                age, status = -1, "MISSING"
            print(f"{ticker:<8}  {cfg['model_file']:<35}  {age:<12}  {status}")
        print()


def run_scheduler():
    """Loop forever, sleeping until the next scheduled run."""
    log.info("NeuroSight Auto-Retrain Service started")
    log.info("Schedule: every Sunday at %02d:%02d", RETRAIN_HOUR, RETRAIN_MINUTE)
    log.info("Log file: %s", LOG_FILE)

    # On first start, retrain any stale/missing models immediately
    try:
        import prediction_engine as pe
        stale = []
        for ticker, cfg in pe.ASSET_CONFIG.items():
            path = pe.MODELS_DIR / cfg["model_file"]
            if not path.exists():
                stale.append(ticker)
            elif (datetime.now() - datetime.fromtimestamp(path.stat().st_mtime)).days > 7:
                stale.append(ticker)
        if stale:
            log.info("Stale/missing on startup: %s  → retraining now", stale)
            for ticker in stale:
                try:
                    result = pe.retrain_asset(ticker)
                    if result.get("success"):
                        log.info("  [PASS] %s startup retrain", ticker)
                    else:
                        log.warning("  [FAIL] %s: %s", ticker, result.get("error"))
                except Exception as exc:
                    log.error("  [ERROR] %s: %s", ticker, exc)
        else:
            log.info("All models fresh at startup — no immediate retrain needed")
    except Exception as exc:
        log.warning("Startup staleness check failed: %s", exc)

    while True:
        next_run = _next_run_time()
        wait_sec = (next_run - datetime.now()).total_seconds()
        log.info(
            "Next retrain: %s  (in %.1fh)",
            next_run.strftime("%Y-%m-%d %H:%M"),
            wait_sec / 3600,
        )

        # Sleep in 60-second chunks so Ctrl-C is responsive
        while (next_run - datetime.now()).total_seconds() > 0:
            time.sleep(min(60, max(1, (next_run - datetime.now()).total_seconds())))

        run_retrain_now()


# ─────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NeuroSight Auto-Retrain Service")
    parser.add_argument("--now",         action="store_true",
                        help="Retrain all models immediately then exit")
    parser.add_argument("--status",      action="store_true",
                        help="Show model ages and prediction cache freshness, then exit")
    parser.add_argument("--predictions", action="store_true",
                        help="Generate and cache fresh predictions for all assets, then exit "
                             "(no retraining — use after manual model replacement)")
    args = parser.parse_args()

    if args.status:
        show_status()
    elif args.predictions:
        log.info("Generating fresh predictions for all assets (no retrain)...")
        try:
            from prediction_store import refresh_all_predictions
            results = refresh_all_predictions(source="manual")
            for t, r in results.items():
                if "error" in r:
                    log.warning("  [FAIL] %s: %s", t, r["error"])
                else:
                    log.info("  [OK]   %s  predicted=$%.2f  conf=%.1f%%",
                             t, r.get("predicted_price", 0), r.get("confidence_score", 0))
        except Exception as exc:
            log.error("Prediction refresh failed: %s", exc)
            sys.exit(1)
    elif args.now:
        ok = run_retrain_now()
        sys.exit(0 if ok else 1)
    else:
        run_scheduler()
