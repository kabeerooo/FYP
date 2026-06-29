import os
from datetime import datetime, timezone
import threading
from firebase_admin import firestore
import auth_routes

db = auth_routes.db

def get_model_status():
    """Get the status of all ML models"""
    status_ref = db.collection('model_status').document('latest').get()
    if status_ref.exists:
        return status_ref.to_dict()
    
    # Default status if none found
    return {
        "AAPL": {"last_trained": None, "accuracy": None, "status": "Ready", "version": "1.0"},
        "NVDA": {"last_trained": None, "accuracy": None, "status": "Ready", "version": "1.0"},
        "TSLA": {"last_trained": None, "accuracy": None, "status": "Ready", "version": "1.0"},
        "GOLD": {"last_trained": None, "accuracy": None, "status": "Ready", "version": "1.0"}
    }

def set_model_status(symbol, status_update):
    """Update model status in Firestore"""
    try:
        doc_ref = db.collection('model_status').document('latest')
        
        if not doc_ref.get().exists:
            current_status = get_model_status()
            current_status[symbol].update(status_update)
            doc_ref.set(current_status)
        else:
            doc_ref.update({
                f"{symbol}.{k}": v for k, v in status_update.items()
            })
            
        # Also log the training event
        if status_update.get("status") == "Completed":
            db.collection('model_training_logs').add({
                "symbol": symbol,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "accuracy": status_update.get("accuracy"),
                "version": status_update.get("version", "1.0"),
            })
            
        return True
    except Exception as e:
        print(f"Error updating model status for {symbol}: {e}")
        return False

def _run_retrain_script(symbol=None):
    """Retrain one or all models using prediction_engine.retrain_asset()."""
    try:
        import sys, os
        from pathlib import Path
        base_dir = Path(__file__).resolve().parent
        if str(base_dir) not in sys.path:
            sys.path.insert(0, str(base_dir))
        import prediction_engine as pe

        symbols_to_train = ["AAPL", "NVDA", "TSLA", "GOLD"] if (not symbol or symbol == "ALL") else [symbol.upper()]

        for sym in symbols_to_train:
            try:
                result = pe.retrain_asset(sym)
                if result.get("success"):
                    mae  = result.get("mae", 0)
                    rmse = result.get("rmse", 0)
                    # Estimate a display accuracy from RMSE (return-mode gives % values)
                    acc_val = max(50.0, min(99.0, 100.0 - float(rmse)))
                    set_model_status(sym, {
                        "status":       "Completed",
                        "last_trained": datetime.now(timezone.utc).isoformat(),
                        "accuracy":     f"{acc_val:.1f}%",
                        "version":      "2.0",
                    })
                else:
                    set_model_status(sym, {"status": "Failed"})
                    print(f"Retrain returned failure for {sym}: {result.get('message')}")
            except Exception as e:
                set_model_status(sym, {"status": "Failed"})
                print(f"Retrain error for {sym}: {e}")

    except Exception as e:
        print(f"_run_retrain_script error: {e}")
        if symbol and symbol != "ALL":
            set_model_status(symbol, {"status": "Failed"})

def trigger_retraining(symbol: str):
    """Trigger background retraining for a symbol"""
    symbol = symbol.upper()
    valid_symbols = ["AAPL", "NVDA", "TSLA", "GOLD", "ALL"]
    if symbol not in valid_symbols:
        return False, "Invalid symbol"
        
    # Mark as training
    if symbol == "ALL":
        for s in valid_symbols[:-1]:
            set_model_status(s, {"status": "Training"})
    else:
        set_model_status(symbol, {"status": "Training"})
        
    # Start background thread
    thread = threading.Thread(target=_run_retrain_script, args=(symbol,))
    thread.daemon = True
    thread.start()
    
    return True, "Retraining started in background"
