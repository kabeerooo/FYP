# main.py

# Fix Windows console encoding to support emojis in print() statements
import sys
import os
os.environ['PYTHONIOENCODING'] = 'utf-8'
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

import yfinance as yf
import numpy as np
import pandas as pd
import threading
import joblib
import requests
import nltk
from bs4 import BeautifulSoup
from nltk.sentiment.vader import SentimentIntensityAnalyzer
import httpx
from fastapi import Depends, FastAPI, Request, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.templating import Jinja2Templates
from jinja2 import select_autoescape
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pathlib import Path
from datetime import datetime
from typing import Optional
import asyncio
import re
from contextlib import asynccontextmanager

import auth_routes
db = auth_routes.db

# Import logging service
try:
    from logging_service import log_admin_action, log_system_event, log_chat_interaction, log_error
except ImportError:
    # Fallback if logging service not available
    def log_admin_action(*args, **kwargs): pass
    def log_system_event(*args, **kwargs): pass
    def log_chat_interaction(*args, **kwargs): pass
    def log_error(*args, **kwargs): pass

# Import session management
try:
    from session_manager import session_manager
except ImportError:
    session_manager = None
    print("⚠️ Session manager not available")

# Import activity tracking
try:
    from activity_tracker import activity_tracker
except ImportError:
    activity_tracker = None
    print("⚠️ Activity tracker not available")

# Import error logging
try:
    from error_logger import error_logger, ErrorCategory, ErrorSeverity
except ImportError:
    error_logger = None
    print("⚠️ Error logger not available")

# Import new modules
try:
    from user_preferences import UserPreferencesManager
    user_prefs_manager = UserPreferencesManager()
except ImportError:
    user_prefs_manager = None
    print("⚠️ User preferences manager not available")

try:
    from analytics_engine import AnalyticsEngine
    analytics_engine = AnalyticsEngine()
except ImportError:
    analytics_engine = None
    print("⚠️ Analytics engine not available")

try:
    from data_cache import DataCacheManager
    data_cache = DataCacheManager()
except ImportError:
    data_cache = None
    print("⚠️ Data cache manager not available")

# Import our enhanced LLM engine
from llm_engine_enhanced import enhanced_llm_engine

# Import prediction engine
try:
    from prediction_engine import predict_asset as engine_predict, retrain_asset, retrain_all, start_retrain_scheduler
    PREDICTION_ENGINE = True
except ImportError as e:
    PREDICTION_ENGINE = False
    print(f"⚠️ Prediction engine not available: {e}")

# Import Marketaux news service
try:
    from marketaux_service import fetch_market_news
except ImportError:
    fetch_market_news = None
    print("⚠️ Marketaux news service not available")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Create default admin account
    try:
        from passlib.context import CryptContext
        pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
        
        admin_email = os.getenv("ADMIN_EMAIL")
        admin_password = os.getenv("ADMIN_PASSWORD")

        if not admin_email or not admin_password:
            print("⚠️ ADMIN_EMAIL and ADMIN_PASSWORD env vars not set — skipping admin seed")
            yield
            return

        # Check if admin exists
        users_ref = db.collection("users")
        existing = users_ref.where(filter=auth_routes.firestore.FieldFilter("email", "==", admin_email)).limit(1).get()
        
        if len(existing) == 0:
            # Create admin account only if it doesn't exist
            users_ref.document().set({
                "name": "Admin",
                "email": admin_email,
                "password_hash": pwd_context.hash(admin_password),
                "role": "admin",
                "created_at": datetime.utcnow(),
                "is_verified": True,
            })
            print(f"✅ Default admin account created: {admin_email}")
        else:
            # Only ensure role=admin, never overwrite password
            existing_doc = existing[0]
            existing_doc.reference.update({
                "role": "admin",
                "is_verified": True,
            })
            print(f"✅ Admin account verified: {admin_email}")
    except Exception as e:
        print(f"⚠️ Error creating default admin: {e}")

    # Pull latest retrained models from Firebase Storage before serving predictions —
    # Railway's local disk doesn't survive restarts, so the bundled models could be stale.
    if PREDICTION_ENGINE:
        try:
            from model_sync import download_latest_models
            from prediction_engine import MODELS_DIR, ASSET_CONFIG
            download_latest_models(MODELS_DIR, ASSET_CONFIG)
        except Exception as e:
            print(f"⚠️ Could not sync models from Firebase Storage: {e}")

    # Start daily auto-retrain scheduler
    if PREDICTION_ENGINE:
        try:
            start_retrain_scheduler()
        except Exception as e:
            print(f"⚠️ Could not start retrain scheduler: {e}")
    
    yield
    # Shutdown: release shared HTTP client
    try:
        from finnhub_service import close_async_http_client
        await close_async_http_client()
    except Exception:
        pass

app = FastAPI(lifespan=lifespan)

_ALLOWED_ORIGINS = [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost,http://127.0.0.1").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# ===== ADMIN AUTHENTICATION DEPENDENCY =====
from fastapi import Header

async def require_admin(x_user_id: str = Header(default=None, alias="X-User-Id")):
    """Guard all /api/admin/* endpoints.
    Clients must send X-User-Id header; we verify role=admin in Firestore.
    """
    if not x_user_id:
        raise HTTPException(status_code=401, detail="Authentication required")
    try:
        user_doc = db.collection("users").document(x_user_id).get()
        if not user_doc.exists or user_doc.to_dict().get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin privileges required")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=503, detail="Auth check failed")

templates = Jinja2Templates(directory=str(Path(__file__).parent.parent / "templates"))
# Disable template caching to prevent unhashable type errors
templates.env.auto_reload = True
templates.env.cache = None
static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# ===== MODEL INFERENCE =====
# All ML inference is handled by prediction_engine.py.
# The old duplicated loading stack (MODEL_CACHE, SCALER_CACHE, _load_model_and_scaler,
# _find_scaler_paths, _fetch_features, _compute_sentiment) has been removed.
# Use engine_predict() / get_asset_prediction() below.


@app.get("/")
def home(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/index.html")
def index_page(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")

@app.get("/login.html")
def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html")

@app.get("/register")
def register_page(request: Request):
    return templates.TemplateResponse(request=request, name="register.html")

@app.get("/register.html")
def register_page_html(request: Request):
    return templates.TemplateResponse(request=request, name="register.html")

@app.get("/dashboard.html")
def dashboard_page(request: Request):
    return templates.TemplateResponse(request=request, name="dashboard.html")

@app.get("/market_news.html")
def market_news_page(request: Request):
    return templates.TemplateResponse(request=request, name="market_news.html")

@app.get("/chatbot.html")
def chatbot_page(request: Request):
    return templates.TemplateResponse(request=request, name="chatbot.html")

@app.get("/chatbot")
def chatbot_redirect(request: Request):
    return templates.TemplateResponse(request=request, name="chatbot.html")

@app.get("/asset_prediction.html")
def asset_prediction_page(request: Request):
    return templates.TemplateResponse(request=request, name="asset_prediction.html")

@app.get("/admin_login.html")
def admin_login_page(request: Request):
    return templates.TemplateResponse(request=request, name="admin_login.html")

@app.get("/admin_dashboard.html")
def admin_dashboard_page(request: Request):
    return templates.TemplateResponse(request=request, name="admin_dashboard.html")

@app.get("/forgot_password.html")
def forgot_password_page(request: Request):
    return templates.TemplateResponse(request=request, name="forgot_password.html")

@app.get("/reset_password.html")
def reset_password_page(request: Request):
    return templates.TemplateResponse(request=request, name="reset_password.html")

@app.get("/verify_email.html")
def verify_email_page(request: Request):
    return templates.TemplateResponse(request=request, name="verify_email.html")

@app.get("/api_test.html")
def api_test_page(request: Request):
    return templates.TemplateResponse(request=request, name="api_test.html")

@app.get("/favicon.ico")
def favicon():
    return Response(status_code=204)

@app.get("/test_market_cap.html")
async def test_market_cap():
    """Test page to verify market cap is being returned correctly"""
    with open(Path(__file__).parent / "test_market_cap.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.get("/debug_market_cap.html")
async def debug_market_cap():
    """Debug page with cache busting to verify market cap"""
    with open(Path(__file__).parent / "debug_market_cap.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

# ===== CREATE DEFAULT ADMIN ACCOUNT =====
# Admin account creation moved to lifespan context manager above

# ===== ADMIN DASHBOARD API ENDPOINTS =====
@app.get("/api/admin/stats", dependencies=[Depends(require_admin)])
async def get_admin_stats():
    """Get admin dashboard statistics"""
    try:
        # Get total users count
        users_ref = db.collection('users')
        users = list(users_ref.stream())
        total_users = len(users)
        
        # Get total chat logs (API calls)
        chats_ref = db.collection('chat_logs')
        chats = list(chats_ref.stream())
        total_api_calls = len(chats)
        
        # System load and active predictions are placeholders for now
        # In production, you'd get these from actual monitoring systems
        system_load = 0  # Can be calculated from server metrics
        active_predictions = 0  # Can be tracked in a separate collection
        
        return {
            "total_users": total_users,
            "active_predictions": active_predictions,
            "system_load": system_load,
            "api_calls": total_api_calls
        }
    except Exception as e:
        print(f"Error fetching admin stats: {e}")
        return {
            "total_users": 0,
            "active_predictions": 0,
            "system_load": 0,
            "api_calls": 0
        }

@app.get("/api/admin/system-performance", dependencies=[Depends(require_admin)])
async def get_system_performance():
    """Get real-time system performance metrics"""
    try:
        import psutil
        import time
        
        # CPU metrics
        cpu_percent = psutil.cpu_percent(interval=0.1)
        cpu_count = psutil.cpu_count()
        cpu_freq = psutil.cpu_freq()
        
        # Memory metrics
        memory = psutil.virtual_memory()
        memory_percent = memory.percent
        memory_used_gb = memory.used / (1024 ** 3)
        memory_total_gb = memory.total / (1024 ** 3)
        
        # Disk metrics
        disk = psutil.disk_usage('/')
        disk_percent = disk.percent
        disk_used_gb = disk.used / (1024 ** 3)
        disk_total_gb = disk.total / (1024 ** 3)
        
        # Network metrics
        net_io = psutil.net_io_counters()
        
        # Process metrics
        process = psutil.Process()
        process_memory = process.memory_info().rss / (1024 ** 2)  # MB
        process_cpu = process.cpu_percent(interval=0.1)
        
        # API call rate (from recent chat logs)
        chats_ref = db.collection('chat_logs')
        recent_chats = list(chats_ref.order_by('timestamp', direction='DESCENDING').limit(100).stream())
        api_call_rate = len(recent_chats)
        
        return {
            "timestamp": time.time(),
            "cpu": {
                "percent": round(cpu_percent, 2),
                "count": cpu_count,
                "frequency": round(cpu_freq.current, 2) if cpu_freq else 0
            },
            "memory": {
                "percent": round(memory_percent, 2),
                "used_gb": round(memory_used_gb, 2),
                "total_gb": round(memory_total_gb, 2)
            },
            "disk": {
                "percent": round(disk_percent, 2),
                "used_gb": round(disk_used_gb, 2),
                "total_gb": round(disk_total_gb, 2)
            },
            "network": {
                "bytes_sent": net_io.bytes_sent,
                "bytes_recv": net_io.bytes_recv
            },
            "process": {
                "memory_mb": round(process_memory, 2),
                "cpu_percent": round(process_cpu, 2)
            },
            "api_calls": api_call_rate
        }
    except Exception as e:
        print(f"Error fetching system performance: {e}")
        log_error("Failed to fetch system performance", str(e))
        return {
            "timestamp": 0,
            "cpu": {"percent": 0, "count": 0, "frequency": 0},
            "memory": {"percent": 0, "used_gb": 0, "total_gb": 0},
            "disk": {"percent": 0, "used_gb": 0, "total_gb": 0},
            "network": {"bytes_sent": 0, "bytes_recv": 0},
            "process": {"memory_mb": 0, "cpu_percent": 0},
            "api_calls": 0
        }

@app.get("/api/admin/recent-users", dependencies=[Depends(require_admin)])
async def get_recent_users():
    """Get recent registered users"""
    try:
        users_ref = db.collection('users').order_by('created_at', direction='DESCENDING').limit(10)
        users = users_ref.stream()
        
        user_list = []
        for user in users:
            user_data = user.to_dict()
            user_list.append({
                "user_id": user.id,
                "name": user_data.get('name', 'Unknown'),
                "email": user_data.get('email', 'No email'),
                "created_at": user_data.get('created_at', 'Unknown'),
                "status": "active"  # Can be enhanced with last_login tracking
            })
        
        return {"users": user_list}
    except Exception as e:
        print(f"Error fetching recent users: {e}")
        return {"users": []}

@app.get("/api/admin/system-logs", dependencies=[Depends(require_admin)])
async def get_system_logs():
    """Get recent system logs with enhanced categorization"""
    try:
        # Get logs from the new system_logs collection
        logs_ref = db.collection('system_logs').order_by('timestamp', direction='DESCENDING').limit(50)
        logs = logs_ref.stream()
        
        log_list = []
        for log in logs:
            log_data = log.to_dict()
            
            # Format timestamp to be more readable
            timestamp = log_data.get('timestamp', 'Unknown')
            try:
                if timestamp != 'Unknown':
                    dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                    timestamp = dt.strftime('%Y-%m-%d %H:%M:%S')
            except:
                pass
            
            log_list.append({
                "message": log_data.get('message', 'No message'),
                "timestamp": timestamp,
                "type": log_data.get('type', 'info'),
                "category": log_data.get('category', 'general'),
                "user_id": log_data.get('user_id'),
                "details": log_data.get('details', {})
            })
        
        return {"logs": log_list}
    except Exception as e:
        print(f"Error fetching system logs: {e}")
        log_error("Failed to fetch system logs", str(e))
        return {"logs": []}

@app.get("/api/admin/users", dependencies=[Depends(require_admin)])
async def get_all_users():
    """Get all registered users"""
    try:
        users_ref = db.collection('users').stream()
        
        user_list = []
        for user_doc in users_ref:
            user_data = user_doc.to_dict()
            user_list.append({
                "id": user_doc.id,
                "name": user_data.get('name', 'Unknown User'),
                "email": user_data.get('email', 'No email'),
                "created_at": user_data.get('created_at', 'Unknown'),
                "status": user_data.get('status', 'active')
            })
        
        # Sort by creation date (newest first)
        user_list.sort(key=lambda x: x.get('created_at', ''), reverse=True)
        
        return user_list
    except Exception as e:
        print(f"Error fetching all users: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch users: {str(e)}")

@app.post("/api/admin/refresh-cache", dependencies=[Depends(require_admin)])
async def refresh_cache():
    """Refresh system cache"""
    try:
        log_admin_action("system", "Cache refresh requested")
        
        # In production, this would clear Redis cache, restart services, etc.
        # For now, we'll just return a success message
        timestamp = datetime.now().isoformat()
        
        log_system_event("System cache refreshed", "success")
        
        return {
            "success": True,
            "message": "Cache refreshed successfully",
            "timestamp": timestamp
        }
    except Exception as e:
        print(f"Error refreshing cache: {e}")
        log_error("Cache refresh failed", str(e))
        raise HTTPException(status_code=500, detail="Failed to refresh cache")

@app.get("/api/admin/export-data", dependencies=[Depends(require_admin)])
async def export_data():
    """Export admin data as JSON"""
    try:
        log_admin_action("system", "Data export requested")
        
        # Get all data
        users_ref = db.collection('users')
        users = list(users_ref.stream())
        
        chats_ref = db.collection('chat_logs')
        chats = list(chats_ref.stream())
        
        # Prepare export data
        export_data = {
            "export_date": datetime.now().isoformat(),
            "total_users": len(users),
            "total_chats": len(chats),
            "users": [{"id": u.id, **u.to_dict()} for u in users],
            "chat_logs": [{"id": c.id, **c.to_dict()} for c in chats]
        }
        
        log_system_event("Data exported successfully", "success", 
                        {"total_users": len(users), "total_chats": len(chats)})
        
        return export_data
    except Exception as e:
        print(f"Error exporting data: {e}")
        log_error("Data export failed", str(e))
        raise HTTPException(status_code=500, detail="Failed to export data")

# System settings defaults — persisted to Firestore on first write.
# Do NOT use a module-level mutable dict as the live source of truth:
# it would reset on every restart and not work across multiple workers.
_DEFAULT_SYSTEM_SETTINGS = {
    "auto_refresh": True,
    "email_notifications": False,
    "debug_mode": False,
    "maintenance_mode": False,
    "data_retention": 90,
}

@app.get("/api/admin/settings", dependencies=[Depends(require_admin)])
async def get_system_settings():
    """Get current system settings"""
    try:
        # In production, fetch from Firebase
        settings_ref = db.collection('system_settings').document('config')
        settings_doc = settings_ref.get()
        
        if settings_doc.exists:
            return settings_doc.to_dict()
        else:
            # Return default settings
            settings_ref.set(_DEFAULT_SYSTEM_SETTINGS)
            return _DEFAULT_SYSTEM_SETTINGS
    except Exception as e:
        print(f"Error fetching settings: {e}")
        return _DEFAULT_SYSTEM_SETTINGS

@app.post("/api/admin/settings", dependencies=[Depends(require_admin)])
async def update_system_settings(settings: dict):
    """Update system settings"""
    try:
        settings_ref = db.collection('system_settings').document('config')
        settings_ref.set(settings, merge=True)
        
        # Apply settings effects
        if settings.get('maintenance_mode'):
            # In production, this would block non-admin users
            print("⚠️ MAINTENANCE MODE ENABLED - User access restricted")
        
        if settings.get('debug_mode'):
            # Enable verbose logging
            print("🔧 DEBUG MODE ENABLED - Verbose logging activated")
        
        return {
            "success": True,
            "message": "Settings updated successfully",
            "settings": settings
        }
    except Exception as e:
        print(f"Error updating settings: {e}")
        raise HTTPException(status_code=500, detail="Failed to update settings")

# ===== MODEL MANAGER ENDPOINTS =====
try:
    from model_manager import get_model_status, trigger_retraining
except ImportError:
    pass

@app.get("/api/admin/models/status", dependencies=[Depends(require_admin)])
async def api_model_status():
    try:
        return {"success": True, "data": get_model_status()}
    except Exception as e:
        raise HTTPException(500, str(e))

@app.post("/api/admin/models/retrain/{symbol}", dependencies=[Depends(require_admin)])
async def api_retrain_model(symbol: str):
    valid_symbols = ["AAPL", "NVDA", "TSLA", "GOLD", "ALL"]
    if symbol.upper() not in valid_symbols:
        raise HTTPException(400, "Invalid symbol")
    
    try:
        success, msg = trigger_retraining(symbol.upper())
        if not success:
            raise HTTPException(400, msg)
        return {"success": True, "message": msg}
    except Exception as e:
        raise HTTPException(500, str(e))

# ===== PREDICTION HELPER =====
def get_asset_prediction(ticker: str) -> dict:
    """Legacy helper – delegates to prediction_engine when available."""
    if PREDICTION_ENGINE:
        try:
            return engine_predict(ticker)
        except Exception as e:
            print(f"Prediction engine error for {ticker}: {e}")
    # fallback
    return {
        "ticker": ticker,
        "predicted_price": 0.0,
        "sentiment": 0.0,
        "error": "Prediction engine unavailable",
    }

# ===== CHAT REQUEST MODEL (with user_id) =====
class ChatRequest(BaseModel):
    message: str
    user_id: str  # ✅ REQUIRED: Firestore document ID
    context: dict = None
    session_id: str = None  # Optional: Session ID for conversation threading


class PredictRequest(BaseModel):
    ticker: str


@app.post("/predict")
def predict_asset_post(req: PredictRequest):
    return get_asset_prediction(req.ticker.upper())


@app.get("/api/predict/{symbol}")
async def get_prediction_for_asset(symbol: str, period: str = "7d"):
    """Full prediction with N-day forecast, chart data and AI insights.
    
    Query param: period = '1d' | '3d' | '7d' | '30d' | '90d'  (default '7d')
    
    PERF FIX: runs in a thread-pool worker so the event loop is never blocked.
    """
    try:
        model_ticker = "GOLD" if symbol.upper() in ("GC=F", "GOLD") else symbol.upper()

        if PREDICTION_ENGINE:
            # asyncio.to_thread keeps the event loop free during the 2-9 s prediction
            result = await asyncio.to_thread(engine_predict, model_ticker, period)
            return result
        else:
            raise HTTPException(500, "Prediction engine not loaded")

    except HTTPException:
        raise
    except Exception as e:
        print(f"Error in /api/predict/{symbol}: {e}")
        raise HTTPException(500, str(e))


@app.post("/api/retrain/{symbol}")
def api_retrain_asset(symbol: str):
    """Manually trigger retraining for a single asset (or ALL)."""
    if not PREDICTION_ENGINE:
        raise HTTPException(500, "Prediction engine not loaded")
    sym = symbol.upper()
    if sym == "ALL":
        results = retrain_all()
        return {"success": True, "results": results}
    if sym not in ("AAPL", "NVDA", "TSLA", "GOLD"):
        raise HTTPException(400, f"Unsupported symbol: {sym}")
    result = retrain_asset(sym)
    return result


# ===== CACHED PREDICTION ENDPOINTS ==============================================
# /api/predictions/{symbol}  – instant response from disk cache (8-h TTL).
#   Falls back to live prediction (2-9 s) on cache miss, then saves result.
# /api/predictions            – all 4 assets in one call.
# /api/retrain/status         – model file ages + cached prediction freshness.
# ===============================================================================

try:
    from prediction_store import (
        load_prediction, load_all_predictions,
        refresh_prediction, get_system_status,
    )
    PREDICTION_STORE = True
except ImportError:
    PREDICTION_STORE = False

_VALID_SYMBOLS = {"AAPL", "NVDA", "TSLA", "GOLD"}


@app.get("/api/predictions/{symbol}")
async def get_cached_prediction(symbol: str, period: str = "7d", force: bool = False):
    """Return the latest cached prediction for *symbol*.

    - Normally responds in <5 ms from disk cache (8-hour TTL).
    - On cache miss (first call, or after 8 h) runs live ML inference (~5 s)
      and stores the result — subsequent calls are instant.
    - ?force=true skips the cache and always runs fresh inference.
    - ?period= is forwarded to the live inference engine on cache miss.

    Symbols: AAPL | NVDA | TSLA | GOLD
    """
    sym = symbol.upper()
    if sym not in _VALID_SYMBOLS:
        raise HTTPException(400, f"Unsupported symbol: {sym}. Valid: {sorted(_VALID_SYMBOLS)}")

    if not PREDICTION_ENGINE:
        raise HTTPException(503, "Prediction engine not available")

    # 1 ── try the cache (skip if force=true)
    if PREDICTION_STORE and not force:
        cached = load_prediction(sym)
        if cached:
            return {
                **cached["data"],
                "_cached":       True,
                "_generated_at": cached["generated_at"],
                "_source":       cached["source"],
            }

    # 2 ── cache miss → run live prediction
    try:
        result = await asyncio.to_thread(engine_predict, sym, period)
    except Exception as exc:
        raise HTTPException(500, f"Prediction failed for {sym}: {exc}")

    # 3 ── persist to cache for next call
    if PREDICTION_STORE:
        try:
            from prediction_store import save_prediction
            save_prediction(sym, result, source="api")
        except Exception:
            pass   # cache failure must never break the response

    return {**result, "_cached": False, "_generated_at": datetime.now().isoformat()}


@app.get("/api/predictions")
async def get_all_cached_predictions(force: bool = False):
    """Return latest cached predictions for all 4 assets.

    Assets with no cache entry run live inference in parallel.
    ?force=true refreshes all 4 (slow — use sparingly).
    """
    if not PREDICTION_ENGINE:
        raise HTTPException(503, "Prediction engine not available")

    async def _one(sym: str) -> tuple[str, dict]:
        try:
            if PREDICTION_STORE and not force:
                cached = load_prediction(sym)
                if cached:
                    return sym, {
                        **cached["data"],
                        "_cached":       True,
                        "_generated_at": cached["generated_at"],
                        "_source":       cached["source"],
                    }
            # live inference
            result = await asyncio.to_thread(engine_predict, sym, "7d")
            if PREDICTION_STORE:
                try:
                    from prediction_store import save_prediction
                    save_prediction(sym, result, source="api")
                except Exception:
                    pass
            return sym, {**result, "_cached": False}
        except Exception as exc:
            return sym, {"symbol": sym, "error": str(exc)}

    tasks = [_one(sym) for sym in _VALID_SYMBOLS]
    pairs = await asyncio.gather(*tasks)
    return dict(pairs)


@app.get("/api/retrain/status")
async def get_retrain_status():
    """Return model file ages, training history, and prediction cache freshness.

    Does NOT require admin auth — safe to expose publicly (no sensitive data).
    """
    if not PREDICTION_STORE:
        raise HTTPException(503, "Prediction store not available")
    try:
        status = await asyncio.to_thread(get_system_status)
        return status
    except Exception as exc:
        raise HTTPException(500, str(exc))


# ===== SAVE USER PREDICTION TO FIREBASE =====
class SavePredictionRequest(BaseModel):
    user_id: str
    symbol: str
    predicted_price: float
    current_price: float
    prediction_change_percent: float
    confidence_score: float
    trend_direction: str
    period: str
    rsi: Optional[float] = None
    news_sentiment: Optional[float] = None

@app.post("/api/predictions/save")
async def save_user_prediction(req: SavePredictionRequest):
    """Save a prediction result under users/{user_id}/predictions in Firestore."""
    try:
        user_ref = db.collection("users").document(req.user_id)
        if not user_ref.get().exists:
            raise HTTPException(status_code=404, detail="User not found")
        user_ref.collection("predictions").add({
            "symbol":                    req.symbol,
            "predicted_price":           req.predicted_price,
            "current_price":             req.current_price,
            "prediction_change_percent": req.prediction_change_percent,
            "confidence_score":          req.confidence_score,
            "trend_direction":           req.trend_direction,
            "period":                    req.period,
            "rsi":                       req.rsi,
            "news_sentiment":            req.news_sentiment,
            "timestamp":                 datetime.utcnow(),
        })
        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error saving prediction for user {req.user_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")

# ===== HELPER: GET STOCK INSIGHT =====
def get_stock_insight(ticker: str) -> str:
    insights = {
        "AAPL": "Apple's ecosystem and services growth provide strong stability. A solid long-term hold.",
        "NVDA": "NVIDIA is riding the AI wave hard. Demand for data center GPUs remains explosive.",
        "TSLA": "Tesla innovates fast, but faces rising EV competition. High reward, high risk.",
        "GC=F": "Gold shines when uncertainty rises. A classic hedge against inflation and market stress.",
        "BTC-USD": "Bitcoin's volatility is legendary. Only allocate what you can afford to lose."
    }
    return insights.get(ticker, "Market dynamics are complex. Always do your own research.")

# ===== HELPER: GET LIVE STOCK DATA =====
def get_live_stock_info(ticker: str, name: str):
    try:
        # Try to get from cache first
        cached_price = None
        if data_cache:
            cached_price = data_cache.get_cached_price(ticker)
        
        if cached_price:
            current = cached_price['price']
            change = cached_price['change']
            pct_change = cached_price['change_percent']
            volume = cached_price['volume']
        else:
            # Fetch fresh data
            stock = yf.Ticker(ticker)
            hist = stock.history(period="1d", interval="1m")
            if hist.empty:
                hist = stock.history(period="2d")
            if len(hist) < 2:
                return f"⚠️ Live data for **{name}** is temporarily unavailable.", None

            current = hist['Close'][-1]
            prev_close = hist['Close'][-2] if len(hist) >= 2 else current
            change = current - prev_close
            pct_change = (change / prev_close) * 100
            volume = stock.info.get('volume', 0)
            
            # Cache the fresh data
            if data_cache:
                data_cache.cache_current_price(ticker, {
                    'price': current,
                    'change': change,
                    'change_percent': pct_change,
                    'volume': volume
                })

        arrow = "📈" if change >= 0 else "📉"
        formatted_pct = f"+{pct_change:.2f}%" if pct_change >= 0 else f"{pct_change:.2f}%"
        formatted_volume = f"{volume:,}" if volume else "N/A"

        insight = get_stock_insight(ticker)
        reply = (
            f"Let me check **{name}** for you...\n\n"
            f"{arrow} **Price**: ${current:.2f} ({formatted_pct})\n"
            f"**Volume**: {formatted_volume}\n\n"
            f"{insight}\n\n"
            f"⚠️ _Not financial advice._"
        )
        return reply, ticker
    except Exception as e:
        print(f"Stock error for {ticker}: {e}")
        return f"⚠️ Unable to fetch live data for **{name}** right now.", None

# ===== MAIN CHAT ENDPOINT WITH ENHANCED LLM =====
@app.post("/api/chat")
async def chat(request: ChatRequest):
    user_msg = request.message.strip()
    user_id = request.user_id.strip()
    session_id = getattr(request, 'session_id', None)  # Optional session ID
    
    if not user_msg:
        return JSONResponse({
            "reply": "I didn't catch that. Could you rephrase?",
            "stock_mentioned": None,
            "timestamp": datetime.now().strftime("%I:%M %p")
        })
    
    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")

    # === SESSION MANAGEMENT: Get or create session ===
    conversation_context = []
    if session_manager:
        try:
            session = session_manager.get_or_create_session(user_id, session_id)
            session_id = session.session_id
            conversation_context = session.get_context(num_messages=5)  # Last 5 messages for context
        except Exception as e:
            print(f"Session management error: {e}")
            session_id = None
    else:
        session_id = None

    user_msg_lower = user_msg.lower()
    context = request.context or {}
    # Add conversation history to context
    if conversation_context:
        context['conversation_history'] = conversation_context
    stock_data = None
    intent = "GENERAL"
    confidence = 0.85  # Default confidence

    # Fetch watchlist once for the entire request (avoids 3 redundant Firestore calls)
    _watchlist_cache: list | None = None
    async def _get_watchlist() -> list:
        nonlocal _watchlist_cache
        if _watchlist_cache is None:
            _watchlist_cache = await get_user_watchlist(user_id)
        return _watchlist_cache

    # === Check if user is asking about LIVE stock prices ===
    is_price_query = any(word in user_msg_lower for word in [
        "price", "what is", "what's", "current", "now", "today", "stock at", "trading at"
    ])
    
    if is_price_query:
        intent = "PRICE_QUERY"
        confidence = 0.95
        # Detect which stock and get live data
        if "apple" in user_msg_lower or "aapl" in user_msg_lower:
            reply, stock_mentioned = get_live_stock_info("AAPL", "Apple Inc.")
        elif "nvidia" in user_msg_lower or "nvda" in user_msg_lower:
            reply, stock_mentioned = get_live_stock_info("NVDA", "NVIDIA Corporation")
        elif "tesla" in user_msg_lower or "tsla" in user_msg_lower:
            reply, stock_mentioned = get_live_stock_info("TSLA", "Tesla, Inc.")
        elif "gold" in user_msg_lower or "xau" in user_msg_lower:
            reply, stock_mentioned = get_live_stock_info("GC=F", "Gold")
        elif "bitcoin" in user_msg_lower or "btc" in user_msg_lower:
            reply, stock_mentioned = get_live_stock_info("BTC-USD", "Bitcoin")
        else:
            # No specific stock mentioned, let enhanced LLM handle it
            watchlist = await _get_watchlist()
            result = enhanced_llm_engine.generate_response(
                user_msg, user_id, stock_data, watchlist, context
            )
            reply = result["reply"]
            stock_mentioned = result.get("stock_mentioned")
            intent = result.get("intent", intent)
            confidence = result.get("confidence", confidence)
    
    # === Check for PREDICTION requests ===
    elif re.search(r"predict|forecast|compare.*stock|compare.*asset|which.*better|best.*stock|rank.*stock|compare.*predict", user_msg_lower):
        intent = "PREDICTION"
        confidence = 0.92

        # Check for comparison / cross-asset requests
        is_compare = any(w in user_msg_lower for w in ["compare", "which", "better", "best", "rank", "all", "vs", "versus"])
        
        if is_compare:
            # Cross-asset comparison
            intent = "COMPARISON"
            confidence = 0.94
            try:
                assets = ["AAPL", "NVDA", "TSLA", "GOLD"]
                ranked = []
                for sym in assets:
                    pred = get_asset_prediction(sym)
                    cur = pred.get("current_price", 0)
                    prd = pred.get("predicted_price", 0)
                    pct = ((prd - cur) / cur * 100) if cur else 0
                    ranked.append({"sym": sym, "name": {"AAPL": "Apple", "NVDA": "NVIDIA", "TSLA": "Tesla", "GOLD": "Gold"}[sym], "cur": cur, "pred": prd, "pct": pct, "dir": pred.get("direction", "")})
                ranked.sort(key=lambda x: x["pct"], reverse=True)
                medals = ["🥇", "🥈", "🥉", "4️⃣"]
                lines = ["📊 **7-Day AI Forecast Comparison**\n"]
                for i, r in enumerate(ranked):
                    arrow = "📈" if r["pct"] >= 0 else "📉"
                    sign = "+" if r["pct"] >= 0 else ""
                    lines.append(f"{medals[i]} **{r['name']}** ({r['sym']}): ${r['pred']:.2f} ({sign}{r['pct']:.2f}%) {arrow}")
                best = ranked[0]
                lines.append(f"\n💡 **Top Pick**: {best['name']} with a projected {'+' if best['pct']>=0 else ''}{best['pct']:.2f}% move.")
                lines.append("\n⚠️ _AI predictions are estimates. Not financial advice._")
                reply = "\n".join(lines)
                stock_mentioned = best["sym"]
            except Exception as e:
                reply = "⚠️ Could not generate comparison right now. Please try again."
                stock_mentioned = None

        elif "apple" in user_msg_lower or "aapl" in user_msg_lower:
            pred = get_asset_prediction("AAPL").get("predicted_price", 0.0)
            reply = f"🔮 **Apple (AAPL) AI Forecast**: ${pred:.2f} in 7 days.\n\nOur LSTM model analyzes historical trends and market sentiment to generate this prediction.\n\n⚠️ _Not financial advice._"
            stock_mentioned = "AAPL"
        elif "nvidia" in user_msg_lower or "nvda" in user_msg_lower:
            pred = get_asset_prediction("NVDA").get("predicted_price", 0.0)
            reply = f"🔮 **NVIDIA (NVDA) AI Forecast**: ${pred:.2f} in 7 days.\n\nPowered by our custom deep learning model.\n\n⚠️ _Not financial advice._"
            stock_mentioned = "NVDA"
        elif "tesla" in user_msg_lower or "tsla" in user_msg_lower:
            pred = get_asset_prediction("TSLA").get("predicted_price", 0.0)
            reply = f"🔮 **Tesla (TSLA) AI Forecast**: ${pred:.2f} in 7 days.\n\nBased on technical and sentiment analysis.\n\n⚠️ _Not financial advice._"
            stock_mentioned = "TSLA"
        elif "gold" in user_msg_lower:
            pred = get_asset_prediction("GOLD").get("predicted_price", 0.0)
            reply = f"🔮 **Gold (GC=F) AI Forecast**: ${pred:.2f}/oz in 7 days.\n\nModel considers inflation and rate signals.\n\n⚠️ _Not financial advice._"
            stock_mentioned = "GC=F"
        else:
            watchlist = await _get_watchlist()
            result = enhanced_llm_engine.generate_response(
                user_msg, user_id, stock_data, watchlist, context
            )
            reply = result["reply"]
            stock_mentioned = result.get("stock_mentioned")
            intent = result.get("intent", intent)
            confidence = result.get("confidence", confidence)
    
    # === Check for NEWS requests ===
    elif any(w in user_msg_lower for w in ["news", "latest", "update", "market update"]):
        intent = "NEWS_QUERY"
        confidence = 0.90
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://newsapi.org/v2/everything",
                    params={
                        "q": "finance OR stock market OR investing OR AI stocks",
                        "sortBy": "publishedAt",
                        "language": "en",
                        "apiKey": NEWS_API_KEY,
                        "pageSize": 1
                    },
                    timeout=8.0
                )
            if resp.status_code == 200 and resp.json().get("articles"):
                article = resp.json()["articles"][0]
                title = article["title"]
                url = article["url"]
                reply = f"📰 **Latest Finance News**:\n\n**{title}**\n\n[Read more]({url})\n\n⚠️ _Always verify information from multiple sources._"
                stock_mentioned = None
            else:
                reply = "💡 Markets are active! AI, clean energy, and rate decisions are key themes.\n\n⚠️ _Not financial advice._"
                stock_mentioned = None
        except Exception as e:
            print("News fetch failed:", e)
            reply = "💡 **Market Insight**: Volatility is elevated. Diversification remains wise.\n\n⚠️ _Not financial advice._"
            stock_mentioned = None
    
    # === Let Enhanced LLM handle everything else (with all advanced features) ===
    else:
        watchlist = await _get_watchlist()
        result = enhanced_llm_engine.generate_response(
            user_msg, user_id, stock_data, watchlist, context
        )
        reply = result["reply"]
        stock_mentioned = result.get("stock_mentioned")
        intent = result.get("intent", intent)
        confidence = result.get("confidence", confidence)
        
        # Add personalized recommendations if available
        if result.get("recommendations"):
            reply += f"\n\n---\n**✨ Personalized for You:**\n{result['recommendations']}"

    # === ADD MESSAGE TO SESSION ===
    if session_manager and session_id:
        try:
            session = session_manager.get_or_create_session(user_id, session_id)
            session.add_message("user", user_msg, intent, confidence)
            session.add_message("assistant", reply, intent, confidence)
            
            # Log activity
            if activity_tracker:
                activity_tracker.log_activity(user_id, 'CHAT', {
                    'intent': intent,
                    'confidence': confidence,
                    'stock_mentioned': stock_mentioned
                })
            
            # Track analytics
            if analytics_engine:
                analytics_engine.track_query_pattern(user_id, user_msg, intent, stock_mentioned)
                if stock_mentioned:
                    analytics_engine.track_stock_interest(stock_mentioned, user_id, intent)
                    
        except Exception as e:
            print(f"Error updating session: {e}")
            if error_logger:
                error_logger.log_error(e, ErrorCategory.CHAT, ErrorSeverity.LOW, user_id=user_id)

    # === LOG TO FIRESTORE WITH ENHANCED METADATA ===
    try:
        user_ref = db.collection("users").document(user_id)
        if user_ref.get().exists:
            user_ref.collection("chat_logs").add({
                "user_message": user_msg,
                "bot_reply": reply,
                "timestamp": datetime.utcnow(),
                "stocks_mentioned": stock_mentioned,
                "intent": intent,
                "confidence": confidence,
                "session_id": session_id
            })
            
            # Log chat interaction to system logs
            log_chat_interaction(user_id, user_msg, intent)
            
    except Exception as e:
        print("⚠️ Firestore logging failed:", str(e))
        if error_logger:
            error_logger.log_error(e, ErrorCategory.DATABASE, ErrorSeverity.MEDIUM, user_id=user_id, context={'action': 'chat_logging'})
        else:
            log_error("Chat logging failed", str(e), user_id)

    return JSONResponse({
        "reply": reply,
        "stock_mentioned": stock_mentioned,
        "timestamp": datetime.now().strftime("%I:%M %p"),
        "intent": intent,
        "confidence": confidence,
        "session_id": session_id
    })

def generate_suggested_questions(intent: str, stock_mentioned: str = None) -> list:
    """Generate contextual follow-up questions based on intent"""
    suggestions = []
    
    if intent == "PRICE_QUERY" and stock_mentioned:
        stock_name = {
            "AAPL": "Apple",
            "NVDA": "NVIDIA", 
            "TSLA": "Tesla",
            "MSFT": "Microsoft",
            "GC=F": "Gold"
        }.get(stock_mentioned, stock_mentioned)
        
        suggestions = [
            f"Show me {stock_name} historical trends",
            f"What are the latest {stock_name} news?",
            "Compare with other tech stocks"
        ]
    elif intent == "PREDICTION":
        suggestions = [
            "What factors influence this stock?",
            "Show me current market price",
            "What's the historical performance?"
        ]
    elif intent == "NEWS_QUERY":
        suggestions = [
            "What's Apple stock at today?",
            "Show me NVIDIA price",
            "What is Tesla trading at?"
        ]
    else:
        suggestions = [
            "What's NVIDIA price right now?",
            "Show me Apple stock trends",
            "What is Tesla stock at?"
        ]
    
    return suggestions[:3]  # Return max 3 suggestions

# Helper function to get user watchlist
async def get_user_watchlist(user_id: str) -> list:
    """Helper to fetch user watchlist"""
    try:
        user_ref = db.collection("users").document(user_id)
        user_doc = user_ref.get()
        if user_doc.exists:
            return user_doc.to_dict().get("watchlist", [])
    except Exception as e:
        print(f"Error fetching watchlist: {e}")
    return []


# ===== CHATBOT ALIAS FOR BACKWARD COMPATIBILITY =====
@app.post("/api/chatbot")
async def chatbot_alias(request: ChatRequest):
    """Alias endpoint for /api/chat to maintain backward compatibility"""
    return await chat(request)


# Import profile routes
import profile_routes

app.include_router(auth_routes.router, prefix="/api")
app.include_router(profile_routes.router, prefix="/api")

# ===== WATCHLIST ENDPOINTS =====
class WatchlistRequest(BaseModel):
    user_id: str
    watchlist: list

@app.post("/api/watchlist")
async def save_watchlist(request: WatchlistRequest):
    """Save user's watchlist to Firestore"""
    try:
        user_ref = db.collection("users").document(request.user_id)
        user_ref.update({
            "watchlist": request.watchlist,
            "watchlist_updated": datetime.utcnow()
        })
        return JSONResponse({
            "success": True,
            "message": "Watchlist saved successfully"
        })
    except Exception as e:
        print(f"Error saving watchlist: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/watchlist")
async def get_watchlist(user_id: str):
    """Get user's watchlist from Firestore"""
    try:
        user_ref = db.collection("users").document(user_id)
        user_doc = user_ref.get()
        
        if user_doc.exists:
            user_data = user_doc.to_dict()
            watchlist_updated = user_data.get("watchlist_updated")
            # Convert datetime to ISO string if it exists
            if watchlist_updated:
                if hasattr(watchlist_updated, 'isoformat'):
                    watchlist_updated = watchlist_updated.isoformat()
                else:
                    watchlist_updated = str(watchlist_updated)
            return JSONResponse({
                "watchlist": user_data.get("watchlist", []),
                "updated": watchlist_updated
            })
        else:
            return JSONResponse({"watchlist": []})
    except Exception as e:
        print(f"Error retrieving watchlist: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ===== USER INFO ENDPOINT =====
@app.get("/api/user/{user_id}/info")
async def get_user_info(user_id: str):
    """Get user information including join date"""
    try:
        user_ref = db.collection("users").document(user_id)
        user_doc = user_ref.get()
        
        if user_doc.exists:
            user_data = user_doc.to_dict()
            return JSONResponse({
                "user_id": user_id,
                "name": user_data.get("name"),
                "email": user_data.get("email"),
                "join_date": user_data.get("created_at", datetime.utcnow()).isoformat() if isinstance(user_data.get("created_at"), datetime) else user_data.get("created_at"),
                "role": user_data.get("role", "user")
            })
        else:
            raise HTTPException(status_code=404, detail="User not found")
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error retrieving user info: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ===== LIVE STOCK DATA ENDPOINT (FOR DASHBOARD) =====
# 🚀 Using Finnhub API for fast real-time data (<100ms vs 2-5s with yfinance!)
try:
    from finnhub_service import get_stock_quote, get_company_profile, get_stock_quote_async
    FINNHUB_SERVICE_AVAILABLE = True
except ImportError:
    get_stock_quote = None
    get_company_profile = None
    get_stock_quote_async = None
    FINNHUB_SERVICE_AVAILABLE = False

def _fetch_stock_via_yfinance(symbol: str, include_volume: bool = False) -> dict:
    try:
        stock = yf.Ticker(symbol)
        hist = stock.history(period="5d")
        if hist.empty:
            return {"error": f"No data available for {symbol}"}

        current_price = float(hist["Close"].iloc[-1])
        prev_close = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else current_price
        day_change = current_price - prev_close
        day_change_percent = (day_change / prev_close * 100) if prev_close else 0.0
        day_high = float(hist["High"].max())
        day_low = float(hist["Low"].min())
        day_open = float(hist["Open"].iloc[0])

        # Use volume from history directly — avoids the slow stock.info call
        volume = int(hist["Volume"].iloc[-1]) if "Volume" in hist and not hist["Volume"].empty else 0

        return {
            "symbol": symbol,
            "current_price": current_price,
            "day_change_percent": day_change_percent,
            "day_change": day_change,
            "volume": volume,
            "market_cap": 0,
            "day_high": day_high,
            "day_low": day_low,
            "day_open": day_open,
        }
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/stock/{symbol}")
async def get_stock_data(symbol: str, include_volume: bool = False):
    """
    Get real-time stock data for dashboard - FAST with Finnhub!
    
    Args:
        symbol: Stock symbol (e.g., AAPL, NVDA)
        include_volume: If True, fetch accurate volume from yfinance (slower)
    """
    from fastapi.responses import JSONResponse
    
    try:
        # Try cache first (5-minute cache)
        cached_data = None
        if data_cache:
            cached_data = data_cache.get_cached_price(symbol)
        
        if cached_data and not include_volume:
            response_data = {
                "symbol": symbol,
                "current_price": cached_data['price'],
                "day_change_percent": cached_data['change_percent'],
                "day_change": cached_data['change'],
                "volume": cached_data.get('volume', 0),
                "market_cap": cached_data.get('market_cap', 0),
                "day_high": cached_data.get('high', cached_data['price']),
                "day_low": cached_data.get('low', cached_data['price']),
                "day_open": cached_data.get('open', cached_data['price'])
            }
            # ✅ Add browser cache headers (cache for 2 minutes)
            return JSONResponse(
                content=response_data,
                headers={
                    "Cache-Control": "public, max-age=120",  # 2 minutes
                    "ETag": f"{symbol}-{int(cached_data['price'] * 100)}"
                }
            )
        
        # 🚀 Fetch fresh data from Finnhub (FAST: <100ms!)
        if get_stock_quote is None:
            fallback = _fetch_stock_via_yfinance(symbol, include_volume=include_volume)
            if "error" in fallback:
                raise HTTPException(status_code=404, detail=fallback["error"])
            quote = None
        else:
            quote = get_stock_quote(symbol)
            if not quote:
                fallback = _fetch_stock_via_yfinance(symbol, include_volume=include_volume)
                if "error" in fallback:
                    raise HTTPException(status_code=404, detail=fallback["error"])
                quote = None

        if quote is None:
            current_price = fallback["current_price"]
            day_change = fallback["day_change"]
            day_change_percent = fallback["day_change_percent"]
            day_high = fallback["day_high"]
            day_low = fallback["day_low"]
            day_open = fallback["day_open"]
            volume = fallback["volume"]
            market_cap = fallback["market_cap"]
        else:
            # Skip get_company_profile() — yf.Ticker.info is too slow (3-5s per call)
            market_cap = 0

            current_price = quote['current_price']
            day_change = quote['change']
            day_change_percent = quote['change_percent']
            day_high = quote['high']
            day_low = quote['low']
            day_open = quote['open']
            volume = quote.get('volume', 0)

        # If include_volume requested, fetch accurate volume from yfinance
        if include_volume and volume == 0:
            try:
                stock = yf.Ticker(symbol)
                info = stock.info
                volume = info.get('volume', info.get('regularMarketVolume', 0))
                print(f"📊 Fetched accurate volume for {symbol}: {volume:,}")
            except Exception as vol_error:
                print(f"⚠️ Could not fetch volume for {symbol}: {vol_error}")
        
        # Debug output
        print(f"⚡ {symbol}: ${current_price:.2f} ({day_change_percent:+.2f}%) | Market Cap: ${market_cap:,} | Volume: {volume:,}")
        
        # Cache the data (5-minute cache)
        if data_cache:
            data_cache.cache_current_price(symbol, {
                'price': current_price,
                'change': day_change,
                'change_percent': day_change_percent,
                'volume': volume,
                'market_cap': market_cap,
                'high': day_high,
                'low': day_low,
                'open': day_open
            })
        
        response_data = {
            "symbol": symbol,
            "current_price": float(current_price),
            "day_change_percent": float(day_change_percent),
            "day_change": float(day_change),
            "volume": volume,
            "market_cap": int(market_cap) if market_cap else 0,
            "day_high": float(day_high),
            "day_low": float(day_low),
            "day_open": float(day_open)
        }
        
        # ✅ Add browser cache headers
        return JSONResponse(
            content=response_data,
            headers={
                "Cache-Control": "public, max-age=120",  # 2 minutes
                "ETag": f"{symbol}-{int(current_price * 100)}"
            }
        )
        
    except Exception as e:
        print(f"❌ Error fetching stock {symbol}: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching data for {symbol}: {str(e)}")


# ===== BATCH STOCK DATA ENDPOINT (HIGH PERFORMANCE!) =====
from typing import List, Dict

class BatchStockRequest(BaseModel):
    symbols: List[str]

@app.post("/api/stock/batch")
async def get_stock_batch(request: BatchStockRequest):
    """
    Fetch multiple stocks in parallel - MUCH FASTER than individual requests!
    
    Example: POST /api/stock/batch
    Body: {"symbols": ["AAPL", "GOOGL", "MSFT"]}
    
    Returns: {
        "AAPL": {...stock data...},
        "GOOGL": {...stock data...},
        "MSFT": {...stock data...}
    }
    """
    symbols = request.symbols
    print(f"⚡ Batch request for {len(symbols)} stocks: {', '.join(symbols)}")
    
    async def fetch_one_stock(symbol: str) -> tuple[str, Dict]:
        """Fetch a single stock's data (returns tuple for easy dict construction)"""
        try:
            # Try cache first
            cached_data = None
            if data_cache:
                cached_data = data_cache.get_cached_price(symbol)
            
            if cached_data:
                return (symbol, {
                    "symbol": symbol,
                    "current_price": cached_data['price'],
                    "day_change_percent": cached_data['change_percent'],
                    "day_change": cached_data['change'],
                    "volume": cached_data.get('volume', 0),
                    "market_cap": cached_data.get('market_cap', 0),
                    "day_high": cached_data.get('high', cached_data['price']),
                    "day_low": cached_data.get('low', cached_data['price']),
                    "day_open": cached_data.get('open', cached_data['price']),
                    "cached": True
                })
            
            # ✅ PERFORMANCE FIX: Use async Finnhub for truly parallel requests
            if get_stock_quote_async is None:
                fallback = await asyncio.to_thread(_fetch_stock_via_yfinance, symbol, False)
                if "error" in fallback:
                    return (symbol, {"error": fallback["error"]})
                quote = None
            else:
                quote = await get_stock_quote_async(symbol)
                if not quote:
                    fallback = await asyncio.to_thread(_fetch_stock_via_yfinance, symbol, False)
                    if "error" in fallback:
                        return (symbol, {"error": fallback["error"]})
                    quote = None

            if quote is None:
                current_price = fallback["current_price"]
                day_change = fallback["day_change"]
                day_change_percent = fallback["day_change_percent"]
                day_high = fallback["day_high"]
                day_low = fallback["day_low"]
                day_open = fallback["day_open"]
                volume = fallback["volume"]
                market_cap = fallback["market_cap"]
            else:
                # Skip get_company_profile() — yf.Ticker.info is too slow (3-5s per call)
                market_cap = 0

                current_price = quote['current_price']
                day_change = quote['change']
                day_change_percent = quote['change_percent']
                day_high = quote['high']
                day_low = quote['low']
                day_open = quote['open']
                volume = quote.get('volume', 0)
            
            # Cache the data
            if data_cache:
                data_cache.cache_current_price(symbol, {
                    'price': current_price,
                    'change': day_change,
                    'change_percent': day_change_percent,
                    'volume': volume,
                    'market_cap': market_cap,
                    'high': day_high,
                    'low': day_low,
                    'open': day_open
                })
            
            return (symbol, {
                "symbol": symbol,
                "current_price": float(current_price),
                "day_change_percent": float(day_change_percent),
                "day_change": float(day_change),
                "volume": volume,
                "market_cap": int(market_cap) if market_cap else 0,
                "day_high": float(day_high),
                "day_low": float(day_low),
                "day_open": float(day_open),
                "cached": False
            })
            
        except Exception as e:
            print(f"❌ Error fetching {symbol} in batch: {e}")
            return (symbol, {"error": str(e)})
    
    # Fetch all stocks in parallel using asyncio
    from fastapi.responses import JSONResponse
    start_time = datetime.now()
    
    # Create tasks for all symbols
    tasks = [fetch_one_stock(symbol) for symbol in symbols]
    
    # Run all tasks concurrently
    results = await asyncio.gather(*tasks)
    
    # Convert list of tuples to dictionary
    stock_data = dict(results)
    
    elapsed_time = (datetime.now() - start_time).total_seconds()
    
    # Count successes and cached
    successes = sum(1 for data in stock_data.values() if "error" not in data)
    cached_count = sum(1 for data in stock_data.values() if data.get("cached", False))
    
    print(f"✅ Batch completed: {successes}/{len(symbols)} stocks in {elapsed_time:.2f}s ({cached_count} cached)")
    
    # ✅ Add browser cache headers for batch responses
    return JSONResponse(
        content=stock_data,
        headers={
            "Cache-Control": "public, max-age=120",  # 2 minutes
            "X-Response-Time": f"{elapsed_time:.2f}s",
            "X-Cache-Hits": str(cached_count)
        }
    )


@app.get("/api/stock/{symbol}/history")
async def get_stock_history(symbol: str):
    """5-min bar intraday chart — spiky & clean for all assets"""
    try:
        print(f"📈 Fetching intraday history for {symbol}...")

        def _fetch():
            stock = yf.Ticker(symbol)
            # Futures/commodities trade ~23h/day → 5m gives ~276 pts (already spiky)
            # Regular stocks trade 6.5h/day → 1m gives 390 pts to match spike density
            _FUTURES = {"GC=F", "SI=F", "CL=F", "BTC-USD", "ETH-USD"}
            interval = "5m" if symbol.upper() in _FUTURES else "1m"
            hist = stock.history(period="1d", interval=interval)
            if hist.empty:
                hist = stock.history(period="5d", interval="15m")
            return hist

        hist = await asyncio.to_thread(_fetch)

        if hist.empty:
            raise HTTPException(status_code=404, detail=f"No historical data available for {symbol}")

        prices = [
            {
                'timestamp': idx.isoformat(),
                'price': float(row['Close']),
                'volume': int(row['Volume']) if 'Volume' in row and row['Volume'] == row['Volume'] else 0,
                'open': float(row['Open']),
                'high': float(row['High']),
                'low': float(row['Low'])
            }
            for idx, row in hist.iterrows()
        ]

        print(f"✅ {len(prices)} price points for {symbol}")

        return {
            "symbol": symbol,
            "prices": prices,
            "period": "1d",
            "interval": "5m"
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Error fetching history for {symbol}: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching historical data: {str(e)}")


@app.get("/api/stock/{symbol}/marketcap")
async def get_stock_marketcap(symbol: str):
    """Lightweight market cap fetch using yfinance fast_info"""
    _NO_MCAP = {"GC=F", "SI=F", "CL=F", "BTC-USD", "ETH-USD"}
    if symbol.upper() in _NO_MCAP:
        return {"symbol": symbol, "market_cap": 0}
    try:
        def _fetch():
            ticker = yf.Ticker(symbol)
            # Try fast_info first (fast)
            try:
                mc = getattr(ticker.fast_info, 'market_cap', None)
                if mc and mc > 0:
                    return int(mc)
            except Exception:
                pass
            # Fall back to info dict (slower but reliable)
            try:
                mc = ticker.info.get('marketCap') or ticker.info.get('market_cap') or 0
                if mc and mc > 0:
                    return int(mc)
            except Exception:
                pass
            return 0
        market_cap = await asyncio.to_thread(_fetch)
        return {"symbol": symbol, "market_cap": market_cap}
    except Exception as e:
        print(f"⚠️ market cap fetch failed for {symbol}: {e}")
        return {"symbol": symbol, "market_cap": 0}


@app.get("/api/stock/{symbol}/news")
async def get_stock_news(symbol: str):
    """Get latest news for a specific stock"""
    print(f"\n📰 Fetching news for {symbol}...")
    try:
        # Map symbols to company names for better news search
        company_names = {
            'AAPL': 'Apple',
            'NVDA': 'NVIDIA',
            'TSLA': 'Tesla',
            'GC=F': 'Gold',
            'MSFT': 'Microsoft',
            'GOOGL': 'Google',
            'AMZN': 'Amazon',
            'META': 'Meta',
            'AMD': 'AMD'
        }
        
        company_name = company_names.get(symbol, symbol)
        print(f"Company: {company_name}")
        
        # Try to get news from yfinance
        stock = yf.Ticker(symbol)
        news_items = []
        
        # Get news from yfinance with better error handling
        try:
            if hasattr(stock, 'news'):
                print(f"Stock has news attribute")
                news = stock.news
                if news and isinstance(news, list) and len(news) > 0:
                    news_items = news[:5]  # Get top 5 news items
                    print(f"Found {len(news_items)} news items")
                else:
                    print(f"News attribute exists but is empty or invalid")
            else:
                print(f"Stock does not have news attribute")
        except Exception as news_error:
            print(f"Error accessing news: {news_error}")
        
        # If no news from yfinance, create a fallback
        if not news_items:
            print(f"Using fallback news for {symbol}")
            news_items = [{
                'title': f'{company_name} Market Update',
                'summary': f'Latest market movements and analysis for {company_name}',
                'link': f'https://finance.yahoo.com/quote/{symbol}',
                'published': datetime.now().isoformat(),
                'thumbnail': None
            }]
        
        result = {
            "symbol": symbol,
            "company": company_name,
            "news": news_items
        }
        print(f"✅ Returning news for {symbol}: {len(news_items)} items")
        return result
        
    except Exception as e:
        print(f"❌ Error fetching news for {symbol}: {e}")
        import traceback
        traceback.print_exc()
        # Return fallback news
        return {
            "symbol": symbol,
            "company": symbol,
            "news": [{
                'title': f'{symbol} Market Update',
                'summary': 'Latest market movements and analysis',
                'link': f'https://finance.yahoo.com/quote/{symbol}',
                'published': datetime.now().isoformat(),
                'thumbnail': None
            }]
        }


@app.get("/api/news/market")
async def get_market_news(symbols: Optional[str] = None, limit: int = 12):
    """
    Get real market news from Marketaux API
    
    Query params:
        - symbols: Comma-separated stock symbols (e.g., "AAPL,TSLA,NVDA")
        - limit: Number of articles (default: 12)
    
    Returns:
        JSON with articles array containing real news with images and URLs
    """
    try:
        if fetch_market_news is None:
            raise HTTPException(status_code=503, detail="News service not available")
        
        # Parse symbols
        symbol_list = None
        if symbols:
            symbol_list = [s.strip().upper() for s in symbols.split(",")]
            print(f"📰 Fetching news for symbols: {symbol_list}")
        
        # Fetch news from Marketaux
        articles = await fetch_market_news(symbols=symbol_list, limit=limit)
        
        return {
            "success": True,
            "count": len(articles),
            "articles": articles,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        print(f"❌ Error in market news endpoint: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error fetching news: {str(e)}")


# ===== MARKET NEWS ALIAS FOR BACKWARD COMPATIBILITY =====
@app.get("/api/market-news")
async def market_news_alias(symbols: Optional[str] = None, limit: int = 12):
    """Alias endpoint for /api/news/market to maintain backward compatibility"""
    return await get_market_news(symbols, limit)


# ===== SESSION MANAGEMENT ENDPOINTS =====
@app.post("/api/chat/session/start")
async def start_chat_session(request: Request):
    """Start a new chat session"""
    try:
        data = await request.json()
        user_id = data.get('user_id')
        session_id = data.get('session_id')  # Optional: resume existing session
        
        if not user_id:
            raise HTTPException(status_code=400, detail="user_id required")
        
        if session_manager:
            session = session_manager.get_or_create_session(user_id, session_id)
            
            # Log activity
            if activity_tracker:
                activity_tracker.log_activity(user_id, 'CHAT', {'action': 'session_started'})
            
            return JSONResponse({
                'session_id': session.session_id,
                'created_at': session.session_metadata['created_at'],
                'message_count': session.session_metadata['message_count']
            })
        else:
            raise HTTPException(status_code=503, detail="Session manager not available")
            
    except Exception as e:
        if error_logger:
            error_logger.log_error(e, ErrorCategory.CHAT, ErrorSeverity.MEDIUM, user_id=data.get('user_id'))
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/chat/sessions/{user_id}")
async def get_user_sessions(user_id: str):
    """Get all chat sessions for a user"""
    try:
        if session_manager:
            sessions = session_manager.get_user_sessions(user_id)
            return JSONResponse({'sessions': sessions})
        else:
            raise HTTPException(status_code=503, detail="Session manager not available")
    except Exception as e:
        if error_logger:
            error_logger.log_error(e, ErrorCategory.CHAT, ErrorSeverity.LOW, user_id=user_id)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/chat/session/{session_id}/messages")
async def get_session_messages(session_id: str, user_id: str = None):
    """Get all messages from a specific session (with user validation)"""
    try:
        if session_manager:
            # ✅ VALIDATE: Check if session belongs to the requesting user
            if user_id:
                try:
                    session_doc = db.collection('chat_sessions').document(session_id).get()
                    if session_doc.exists:
                        session_data = session_doc.to_dict()
                        session_user_id = session_data.get('user_id')
                        
                        if session_user_id != user_id:
                            raise HTTPException(
                                status_code=403, 
                                detail="You don't have permission to access this session"
                            )
                    else:
                        raise HTTPException(status_code=404, detail="Session not found")
                except HTTPException:
                    raise
                except Exception as e:
                    print(f"Session validation error: {e}")
            
            session = session_manager.get_or_create_session("", session_id)
            messages = session.get_full_conversation()
            return JSONResponse({'messages': messages})
        else:
            raise HTTPException(status_code=503, detail="Session manager not available")
    except HTTPException:
        raise
    except Exception as e:
        if error_logger:
            error_logger.log_error(e, ErrorCategory.CHAT, ErrorSeverity.LOW)
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/chat/session/{session_id}")
async def end_chat_session(session_id: str):
    """End a chat session"""
    try:
        if session_manager:
            session_manager.end_session(session_id)
            return JSONResponse({'success': True, 'message': 'Session ended'})
        else:
            raise HTTPException(status_code=503, detail="Session manager not available")
    except Exception as e:
        if error_logger:
            error_logger.log_error(e, ErrorCategory.CHAT, ErrorSeverity.LOW)
        raise HTTPException(status_code=500, detail=str(e))


# ===== ACTIVITY TRACKING ENDPOINTS =====
@app.post("/api/activity/log")
async def log_user_activity(request: Request):
    """Log a user activity"""
    try:
        data = await request.json()
        user_id = data.get('user_id')
        activity_type = data.get('activity_type')
        details = data.get('details', {})
        
        if not user_id or not activity_type:
            raise HTTPException(status_code=400, detail="user_id and activity_type required")
        
        if activity_tracker:
            success = activity_tracker.log_activity(user_id, activity_type, details)
            return JSONResponse({'success': success})
        else:
            raise HTTPException(status_code=503, detail="Activity tracker not available")
            
    except Exception as e:
        if error_logger:
            error_logger.log_error(e, ErrorCategory.SYSTEM, ErrorSeverity.LOW)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/activity/heatmap/{user_id}")
async def get_user_activity_heatmap(user_id: str, days: int = 30):
    """Get activity heatmap for a specific user"""
    try:
        if activity_tracker:
            heatmap_data = activity_tracker.get_user_heatmap_data(user_id, days)
            return JSONResponse(heatmap_data)
        else:
            raise HTTPException(status_code=503, detail="Activity tracker not available")
    except Exception as e:
        if error_logger:
            error_logger.log_error(e, ErrorCategory.SYSTEM, ErrorSeverity.MEDIUM, user_id=user_id)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/admin/activity/heatmap")
async def get_all_users_heatmap(days: int = 7):
    """Get aggregate activity heatmap for all users"""
    try:
        if activity_tracker:
            heatmap_data = activity_tracker.get_all_users_heatmap(days)
            return JSONResponse(heatmap_data)
        else:
            raise HTTPException(status_code=503, detail="Activity tracker not available")
    except Exception as e:
        if error_logger:
            error_logger.log_error(e, ErrorCategory.SYSTEM, ErrorSeverity.MEDIUM)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/activity/timeline/{user_id}")
async def get_activity_timeline(user_id: str, hours: int = 24):
    """Get recent activity timeline for a user"""
    try:
        if activity_tracker:
            timeline = activity_tracker.get_activity_timeline(user_id, hours)
            return JSONResponse({'timeline': timeline})
        else:
            raise HTTPException(status_code=503, detail="Activity tracker not available")
    except Exception as e:
        if error_logger:
            error_logger.log_error(e, ErrorCategory.SYSTEM, ErrorSeverity.LOW, user_id=user_id)
        raise HTTPException(status_code=500, detail=str(e))


# ===== ERROR MONITORING ENDPOINTS =====
@app.get("/api/admin/errors/dashboard")
async def get_error_dashboard(hours: int = 24):
    """Get error dashboard analytics"""
    try:
        if error_logger:
            dashboard_data = error_logger.get_error_dashboard_data(hours)
            return JSONResponse(dashboard_data)
        else:
            raise HTTPException(status_code=503, detail="Error logger not available")
    except Exception as e:
        print(f"Error getting error dashboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/admin/errors/{error_id}")
async def get_error_details(error_id: str):
    """Get details of a specific error"""
    try:
        if error_logger:
            error_details = error_logger.get_error_details(error_id)
            if error_details:
                return JSONResponse(error_details)
            else:
                raise HTTPException(status_code=404, detail="Error not found")
        else:
            raise HTTPException(status_code=503, detail="Error logger not available")
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error getting error details: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/admin/errors/{error_id}/resolve")
async def resolve_error(error_id: str, request: Request):
    """Mark an error as resolved"""
    try:
        data = await request.json()
        resolution_notes = data.get('resolution_notes', '')
        resolved_by = data.get('resolved_by', 'admin')
        
        if error_logger:
            success = error_logger.mark_error_resolved(error_id, resolution_notes, resolved_by)
            if success:
                log_admin_action(resolved_by, f"Resolved error {error_id}", {'error_id': error_id})
                return JSONResponse({'success': True, 'message': 'Error marked as resolved'})
            else:
                raise HTTPException(status_code=500, detail="Failed to resolve error")
        else:
            raise HTTPException(status_code=503, detail="Error logger not available")
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error resolving error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/admin/errors/trends")
async def get_error_trends(days: int = 7):
    """Get error trends over time"""
    try:
        if error_logger:
            trends = error_logger.get_error_trends(days)
            return JSONResponse(trends)
        else:
            raise HTTPException(status_code=503, detail="Error logger not available")
    except Exception as e:
        print(f"Error getting error trends: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== USER PREFERENCES & WATCHLIST ENDPOINTS ====================

@app.get("/api/user/{user_id}/preferences")
async def get_user_preferences(user_id: str):
    """Get user preferences"""
    try:
        if user_prefs_manager:
            prefs = user_prefs_manager.get_user_preferences(user_id)
            return JSONResponse(prefs)
        else:
            raise HTTPException(status_code=503, detail="Preferences manager not available")
    except Exception as e:
        print(f"Error getting preferences: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/user/{user_id}/preferences")
async def update_user_preferences(user_id: str, request: Request):
    """Update user preferences"""
    try:
        data = await request.json()
        if user_prefs_manager:
            success = user_prefs_manager.update_user_preferences(user_id, data)
            return JSONResponse({'success': success})
        else:
            raise HTTPException(status_code=503, detail="Preferences manager not available")
    except Exception as e:
        print(f"Error updating preferences: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/user/{user_id}/watchlist")
async def get_user_specific_watchlist(user_id: str):
    """Get user's watchlist"""
    try:
        if user_prefs_manager:
            watchlist = user_prefs_manager.get_user_watchlist(user_id)
            return JSONResponse({'watchlist': watchlist})
        else:
            raise HTTPException(status_code=503, detail="Preferences manager not available")
    except Exception as e:
        print(f"Error getting watchlist: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/user/{user_id}/watchlist")
async def add_to_watchlist(user_id: str, request: Request):
    """Add stock to watchlist"""
    try:
        data = await request.json()
        stock_symbol = data.get('stock_symbol')
        notes = data.get('notes', '')
        
        if user_prefs_manager:
            result = user_prefs_manager.add_to_watchlist(user_id, stock_symbol, notes)
            if result == "already_exists":
                return JSONResponse({'success': False, 'message': 'Stock already in watchlist'})
            elif result:
                if analytics_engine:
                    analytics_engine.track_event('watchlist_add', user_id, {'stock': stock_symbol})
                return JSONResponse({'success': True, 'watchlist_id': result})
            else:
                raise HTTPException(status_code=500, detail="Failed to add to watchlist")
        else:
            raise HTTPException(status_code=503, detail="Preferences manager not available")
    except Exception as e:
        print(f"Error adding to watchlist: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/user/watchlist/{watchlist_id}")
async def remove_from_watchlist(watchlist_id: str):
    """Remove stock from watchlist"""
    try:
        if user_prefs_manager:
            success = user_prefs_manager.remove_from_watchlist(watchlist_id)
            return JSONResponse({'success': success})
        else:
            raise HTTPException(status_code=503, detail="Preferences manager not available")
    except Exception as e:
        print(f"Error removing from watchlist: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/user/{user_id}/alerts")
async def get_price_alerts(user_id: str):
    """Get user's price alerts"""
    try:
        if user_prefs_manager:
            alerts = user_prefs_manager.get_user_alerts(user_id, status='active')
            return JSONResponse({'alerts': alerts})
        else:
            raise HTTPException(status_code=503, detail="Preferences manager not available")
    except Exception as e:
        print(f"Error getting alerts: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/user/{user_id}/alerts")
async def create_price_alert(user_id: str, request: Request):
    """Create price alert"""
    try:
        data = await request.json()
        stock_symbol = data.get('stock_symbol')
        alert_type = data.get('alert_type')  # 'above' or 'below'
        target_price = data.get('target_price')
        
        if user_prefs_manager:
            alert_id = user_prefs_manager.create_price_alert(user_id, stock_symbol, alert_type, target_price)
            if alert_id:
                return JSONResponse({'success': True, 'alert_id': alert_id})
            else:
                raise HTTPException(status_code=500, detail="Failed to create alert")
        else:
            raise HTTPException(status_code=503, detail="Preferences manager not available")
    except Exception as e:
        print(f"Error creating alert: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/user/{user_id}/alerts/{alert_id}")
async def delete_price_alert(user_id: str, alert_id: str):
    """Delete a price alert"""
    try:
        if user_prefs_manager:
            success = user_prefs_manager.delete_alert(alert_id)
            return JSONResponse({'success': success})
        else:
            raise HTTPException(status_code=503, detail="Preferences manager not available")
    except Exception as e:
        print(f"Error deleting alert: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==================== CROSS-ASSET COMPARISON ENDPOINT ====================

@app.get("/api/compare/predictions")
async def compare_all_predictions():
    """Compare predictions across all supported assets for AI chatbot integration."""
    assets = ["AAPL", "NVDA", "TSLA", "GOLD"]
    comparisons = []
    for sym in assets:
        try:
            pred = get_asset_prediction(sym)
            current = pred.get("current_price", 0)
            predicted = pred.get("predicted_price", 0)
            pct = ((predicted - current) / current * 100) if current else 0
            comparisons.append({
                "symbol": sym,
                "name": {"AAPL": "Apple", "NVDA": "NVIDIA", "TSLA": "Tesla", "GOLD": "Gold"}.get(sym, sym),
                "current_price": round(current, 2),
                "predicted_price": round(predicted, 2),
                "change_pct": round(pct, 2),
                "direction": pred.get("trend_direction", "UP" if pct >= 0 else "DOWN"),
                "confidence": pred.get("confidence_score", 0),
                "forecast_days": 7,
            })
        except Exception as e:
            comparisons.append({"symbol": sym, "error": str(e)})
    # Rank by predicted % change
    ranked = sorted([c for c in comparisons if "error" not in c], key=lambda x: x["change_pct"], reverse=True)
    return JSONResponse({
        "comparisons": comparisons,
        "best_performer": ranked[0]["symbol"] if ranked else None,
        "worst_performer": ranked[-1]["symbol"] if ranked else None,
        "summary": _build_comparison_summary(ranked),
    })

def _build_comparison_summary(ranked):
    if not ranked:
        return "No prediction data available."
    lines = ["📊 **7-Day AI Forecast Comparison**\n"]
    medals = ["🥇", "🥈", "🥉", "4️⃣"]
    for i, r in enumerate(ranked):
        arrow = "📈" if r["change_pct"] >= 0 else "📉"
        sign = "+" if r["change_pct"] >= 0 else ""
        lines.append(f"{medals[i] if i < 4 else ''} **{r['name']}** ({r['symbol']}): ${r['predicted_price']:.2f} ({sign}{r['change_pct']:.2f}%) {arrow}")
    best = ranked[0]
    lines.append(f"\n💡 **Top Pick**: {best['name']} with a projected {'+' if best['change_pct']>=0 else ''}{best['change_pct']:.2f}% move.")
    lines.append("\n⚠️ _AI predictions are estimates. Not financial advice._")
    return "\n".join(lines)

# ==================== QR CODE & NETWORK ACCESS ====================

@app.get("/api/qrcode")
async def get_qr_code():
    """Generate QR code for mobile access to the server on LAN."""
    import socket
    try:
        import qrcode
        import io
        import base64
    except ImportError:
        return JSONResponse({"error": "qrcode library not installed. Run: pip install qrcode[pil]"}, status_code=503)

    # Get LAN IP
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    
    url = f"http://{ip}:8000"
    qr = qrcode.make(url)
    buf = io.BytesIO()
    qr.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return JSONResponse({"url": url, "ip": ip, "qr_base64": f"data:image/png;base64,{b64}"})

@app.get("/api/analytics/trending-stocks")
async def get_trending_stocks(days: int = 7):
    """Get trending stocks based on user queries"""
    try:
        if analytics_engine:
            trending = analytics_engine.get_trending_stocks(days)
            return JSONResponse({'trending': trending, 'period_days': days})
        else:
            raise HTTPException(status_code=503, detail="Analytics engine not available")
    except Exception as e:
        print(f"Error getting trending stocks: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/analytics/stock/{stock_symbol}")
async def get_stock_analytics(stock_symbol: str, days: int = 30):
    """Get analytics for a specific stock"""
    try:
        if analytics_engine:
            breakdown = analytics_engine.get_stock_interest_breakdown(stock_symbol, days)
            return JSONResponse(breakdown)
        else:
            raise HTTPException(status_code=503, detail="Analytics engine not available")
    except Exception as e:
        print(f"Error getting stock analytics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/analytics/engagement")
async def get_engagement_metrics(days: int = 7):
    """Get user engagement metrics"""
    try:
        if analytics_engine:
            metrics = analytics_engine.get_user_engagement_summary(days)
            return JSONResponse(metrics)
        else:
            raise HTTPException(status_code=503, detail="Analytics engine not available")
    except Exception as e:
        print(f"Error getting engagement metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/analytics/popular-queries")
async def get_popular_queries(limit: int = 20):
    """Get most popular user queries"""
    try:
        if analytics_engine:
            queries = analytics_engine.get_popular_queries(limit)
            return JSONResponse({'queries': queries})
        else:
            raise HTTPException(status_code=503, detail="Analytics engine not available")
    except Exception as e:
        print(f"Error getting popular queries: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/analytics/intent-distribution")
async def get_intent_distribution(days: int = 7):
    """Get query intent distribution"""
    try:
        if analytics_engine:
            distribution = analytics_engine.get_intent_distribution(days)
            return JSONResponse(distribution)
        else:
            raise HTTPException(status_code=503, detail="Analytics engine not available")
    except Exception as e:
        print(f"Error getting intent distribution: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/analytics/feature-usage")
async def get_feature_usage(days: int = 30):
    """Get feature usage statistics"""
    try:
        if analytics_engine:
            usage = analytics_engine.get_feature_usage(days)
            return JSONResponse(usage)
        else:
            raise HTTPException(status_code=503, detail="Analytics engine not available")
    except Exception as e:
        print(f"Error getting feature usage: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==================== DATA CACHE ENDPOINTS ====================

@app.get("/api/cache/stats")
async def get_cache_stats():
    """Get cache statistics"""
    try:
        if data_cache:
            stats = data_cache.get_cache_stats()
            return JSONResponse(stats)
        else:
            raise HTTPException(status_code=503, detail="Data cache not available")
    except Exception as e:
        print(f"Error getting cache stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/cache/clear-expired")
async def clear_expired_cache():
    """Clear expired cache entries"""
    try:
        if data_cache:
            deleted_count = data_cache.clear_expired_cache()
            return JSONResponse({'success': True, 'deleted_count': deleted_count})
        else:
            raise HTTPException(status_code=503, detail="Data cache not available")
    except Exception as e:
        print(f"Error clearing cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/cache/invalidate/{stock_symbol}")
async def invalidate_stock_cache(stock_symbol: str):
    """Manually invalidate cache for a stock"""
    try:
        if data_cache:
            success = data_cache.invalidate_stock_cache(stock_symbol)
            return JSONResponse({'success': success})
        else:
            raise HTTPException(status_code=503, detail="Data cache not available")
    except Exception as e:
        print(f"Error invalidating cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/cache/batch-update")
async def batch_cache_stocks(request: Request):
    """Batch cache data for multiple stocks"""
    try:
        data = await request.json()
        stock_symbols = data.get('stocks', ['AAPL', 'NVDA', 'TSLA', 'MSFT', 'GC=F'])
        
        if data_cache:
            results = data_cache.batch_cache_stocks(stock_symbols)
            return JSONResponse(results)
        else:
            raise HTTPException(status_code=503, detail="Data cache not available")
    except Exception as e:
        print(f"Error batch caching: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Run server
if __name__ == "__main__":
    import uvicorn
    import socket
    groq_status = "✅ Enabled" if os.getenv("GROQ_API_KEY") else "⚠️ Disabled (no API key)"
    # Get LAN IP for mobile access
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        lan_ip = s.getsockname()[0]
        s.close()
    except Exception:
        lan_ip = "127.0.0.1"
    print("\n🚀 Starting NeuroSight Backend with Hybrid LLM Support...")
    print(f"📡 Local:   http://127.0.0.1:8000")
    print(f"📱 Network: http://{lan_ip}:8000  (use this on your phone)")
    print(f"🤖 Groq LLM: {groq_status}")
    print("\nPress Ctrl+C to stop\n")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")

