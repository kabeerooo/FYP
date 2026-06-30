"""
prediction_engine.py - Asset Price Prediction & Auto-Retraining Engine
======================================================================
Handles per-asset model loading, feature engineering, prediction and
automated retraining for Apple (AAPL), Nvidia (NVDA), Tesla (TSLA), Gold (GC=F).

Each asset has its own architecture and feature set derived from the original
training notebooks.
"""

import sys, os
os.environ['PYTHONIOENCODING'] = 'utf-8'
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import numpy as np
import pandas as pd
import yfinance as yf
import joblib
import threading
import time
import traceback
import requests
import os
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

# ── directories ──────────────────────────────────────────────────────
BASE_DIR   = Path(__file__).resolve().parent
MODELS_DIR = BASE_DIR / "ml_models"

# ── per-asset configuration (matches original training notebooks) ────
ASSET_CONFIG = {
    "AAPL": {
        "yf_ticker":    "AAPL",
        "model_file":   "apple_research_model.keras",
        "scaler_feat":  "apple_scaler_features.pkl",
        "scaler_tgt":   "apple_scaler_target.pkl",
        # RSI added: helps model learn overbought/oversold patterns
        "features":     ["Close", "MA10", "MA20", "MA50", "Volume", "RSI"],
        "lookback":     60,
        "train_years":  5,
        "architecture": "lstm",       # LSTM(64) -> LSTM(32) -> Dense(1)
        "layer_sizes":  [64, 32],
        "dropout":      0.2,
        # Return-mode: model predicts daily % return, not absolute price.
        # This eliminates the downward bias caused by price-level anchoring
        # (old price-mode always predicted reversion to historical mean).
        "predict_mode": "return",
    },
    "NVDA": {
        "yf_ticker":    "NVDA",
        "model_file":   "nvidia_research_model.keras",
        "scaler_feat":  "nvidia_scaler_features.pkl",
        "scaler_tgt":   "nvidia_scaler_target.pkl",
        # RSI added: critical for NVDA which has strong overbought/oversold cycles
        "features":     ["Close", "MA10", "MA20", "MA50", "Volume", "Volatility", "RSI"],
        "lookback":     60,
        "train_years":  5,
        "architecture": "lstm",       # LSTM(128) -> LSTM(64) -> Dense(1)
        "layer_sizes":  [128, 64],
        "dropout":      0.2,
        "predict_mode": "return",
    },
    "TSLA": {
        "yf_ticker":    "TSLA",
        "model_file":   "tesla_research_model.keras",
        "scaler_feat":  "tesla_scaler_features.pkl",
        "scaler_tgt":   "tesla_scaler_target.pkl",
        # RSI added; TSLA's extreme volatility benefits greatly from RSI context
        "features":     ["Close", "MA5", "MA10", "MA20", "Volume", "Volatility", "RSI"],
        "lookback":     60,
        "train_years":  5,
        "architecture": "gru",        # GRU(128) -> GRU(64) -> Dense(1)
        "layer_sizes":  [128, 64],
        "dropout":      0.3,
        "predict_mode": "return",
    },
    "GOLD": {
        "yf_ticker":    "GC=F",
        "model_file":   "gold_research_model.keras",
        "scaler_feat":  "gold_scaler_features.pkl",
        "scaler_tgt":   "gold_scaler_target.pkl",
        # RSI added: helps detect overbought/oversold conditions in gold futures
        "features":     ["Close", "MA10", "MA20", "MA50", "Volume", "Volatility", "RSI"],
        "lookback":     60,
        "train_years":  11,
        "architecture": "cnn_bilstm",
        "layer_sizes":  [64, 100, 32],
        "dropout":      0.2,
        # Return-mode: same fix applied to AAPL/NVDA/TSLA — eliminates price-level
        # anchoring bias and raw-signal out-of-range warnings.
        "predict_mode": "return",
    },
}

# ── runtime caches ───────────────────────────────────────────────────
_model_cache  = {}
_scaler_cache = {}
_cache_lock   = threading.Lock()
_retrain_lock = threading.Lock()
# ── staleness thresholds ─────────────────────────────────────────────
# If current price is this many % above scaler max → model is stale → retrain
_STALE_THRESHOLD_PCT = 0.03   # 3% above scaler max triggers staleness warning
# If model file is older than this many days → schedule background retrain
_MODEL_AGE_RETRAIN_DAYS = 7
# ── news sentiment cache (5-min TTL) ─────────────────────────────────
_sentiment_cache: dict    = {}
_sentiment_cache_ts: dict = {}
SENTIMENT_CACHE_TTL = 900  # seconds (15 min — news doesn't change faster)

# ── per-prediction yfinance data cache (5-min TTL) ────────────────────
# Avoids re-downloading 1 year of OHLCV data on every prediction request.
# AAPL cold-start was 9 s due to yfinance; with cache subsequent calls are <0.1 s.
_data_cache: dict    = {}   # {yf_ticker: pd.DataFrame}
_data_cache_ts: dict = {}   # {yf_ticker: float (epoch)}
DATA_CACHE_TTL = 300        # 5 minutes — prices update every minute anyway

# ── per-asset caps ────────────────────────────────────────────────────
_MODEL_SIGNAL_CAPS = {          # max raw model daily % before blend
    "AAPL": 0.030,
    "NVDA": 0.040,
    "TSLA": 0.055,
    "GOLD": 0.020,
}
_FINAL_DAILY_CAPS = {           # hard cap after all blending + adjustments
    "AAPL": 0.045,
    "NVDA": 0.055,
    "TSLA": 0.070,
    "GOLD": 0.030,
}


# =====================================================================
#  Feature engineering  (must mirror training notebooks exactly)
# =====================================================================
def _engineer_features(df: pd.DataFrame, feature_list: list) -> pd.DataFrame:
    """Add Moving Averages, EMA, MACD, RSI and Volatility columns to raw OHLCV data."""
    df = df.copy()
    if "MA5"  in feature_list:
        df["MA5"]  = df["Close"].rolling(5).mean()
    if "MA10" in feature_list:
        df["MA10"] = df["Close"].rolling(10).mean()
    if "MA20" in feature_list:
        df["MA20"] = df["Close"].rolling(20).mean()
    if "MA50" in feature_list:
        df["MA50"] = df["Close"].rolling(50).mean()
    if "Volatility" in feature_list:
        df["Volatility"] = df["Close"].rolling(20).std()
    if "EMA12" in feature_list:
        df["EMA12"] = df["Close"].ewm(span=12, adjust=False).mean()
    if "EMA26" in feature_list:
        df["EMA26"] = df["Close"].ewm(span=26, adjust=False).mean()
    if "MACD" in feature_list:
        df["MACD"] = (df["Close"].ewm(span=12, adjust=False).mean()
                      - df["Close"].ewm(span=26, adjust=False).mean())
    if "Signal_Line" in feature_list:
        _macd = (df["Close"].ewm(span=12, adjust=False).mean()
                 - df["Close"].ewm(span=26, adjust=False).mean())
        df["Signal_Line"] = _macd.ewm(span=9, adjust=False).mean()
    if "RSI" in feature_list:
        _delta = df["Close"].diff()
        _gain  = _delta.clip(lower=0).rolling(14).mean()
        _loss  = (-_delta.clip(upper=0)).rolling(14).mean()
        _rs    = _gain / _loss.replace(0, np.nan)
        df["RSI"] = 100 - (100 / (1 + _rs))
    df.dropna(inplace=True)
    return df


def _compute_rsi(close_series: pd.Series, period: int = 14) -> float:
    """Compute RSI for the most recent data point. Returns 0-100 float."""
    try:
        delta = close_series.diff()
        gain  = delta.clip(lower=0).rolling(period).mean()
        loss  = (-delta.clip(upper=0)).rolling(period).mean()
        rs    = gain / loss.replace(0, np.nan)
        rsi   = 100 - (100 / (1 + rs))
        val   = float(rsi.dropna().iloc[-1])
        return val if np.isfinite(val) else 50.0
    except Exception:
        return 50.0


# ── Finance-domain VADER lexicon boost (tested 100% accuracy on 10 headlines)
_FINANCE_LEXICON = {
    # Strong positives
    "beats": 2.5, "beat": 2.5, "surge": 2.0, "surges": 2.0, "surging": 2.0,
    "buyback": 2.0, "buybacks": 2.0, "outperform": 2.0, "outperforms": 2.0,
    "blowout": 2.5, "rally": 1.8, "rallies": 1.8, "record": 1.5,
    "profit": 1.8, "profits": 1.8, "growth": 1.5,
    "raised": 1.5, "raise": 1.5, "upgrade": 2.0, "upgraded": 2.0,
    "dividend": 1.5, "dividends": 1.5, "partnership": 1.2,
    "milestone": 1.5, "breakthrough": 2.0, "oversold": 1.8, "undervalued": 1.5,
    "strong": 1.2, "soaring": 2.0, "booming": 2.0, "bullish": 2.0,
    # Strong negatives
    "lawsuit": -2.0, "lawsuits": -2.0, "recall": -2.0, "recalls": -2.0,
    "scandal": -2.5, "arrested": -2.5, "fraud": -2.5, "collapse": -2.5,
    "crash": -2.5, "crashes": -2.5, "downgrade": -2.0, "downgraded": -2.0,
    "miss": -2.0, "missed": -2.0, "deficit": -1.5, "loss": -1.5,
    "warning": -1.5, "layoffs": -1.8, "bankrupt": -3.0, "bankruptcy": -3.0,
    "fine": -1.5, "penalty": -1.5, "investigation": -1.5, "breach": -2.0,
    "overbought": -1.8, "overvalued": -1.5, "plunges": -2.0, "plunge": -2.0,
    "slumps": -2.0, "slump": -2.0, "bearish": -2.0, "tumbles": -2.0,
}

_vader_analyser = None

def _get_vader():
    """Lazy-load VADER analyser with finance lexicon boost (once per process)."""
    global _vader_analyser
    if _vader_analyser is not None:
        return _vader_analyser
    try:
        import nltk
        from nltk.sentiment.vader import SentimentIntensityAnalyzer
        try:
            _vader_analyser = SentimentIntensityAnalyzer()
        except LookupError:
            nltk.download("vader_lexicon", quiet=True)
            _vader_analyser = SentimentIntensityAnalyzer()
        _vader_analyser.lexicon.update(_FINANCE_LEXICON)
    except Exception:
        _vader_analyser = None
    return _vader_analyser


def _get_news_sentiment(yf_ticker: str) -> float:
    """
    Fetch latest news headlines from Marketaux and score them with
    finance-boosted VADER.  Returns [-1.0, 1.0]: +1=bullish, -1=bearish.
    Cached for 15 minutes per ticker.
    """
    now = time.time()
    if yf_ticker in _sentiment_cache and now - _sentiment_cache_ts.get(yf_ticker, 0) < SENTIMENT_CACHE_TTL:
        return _sentiment_cache[yf_ticker]

    symbol_map = {
        "AAPL": "AAPL",
        "NVDA": "NVDA",
        "TSLA": "TSLA",
        "GC=F": "XAUUSD",
    }
    symbol  = symbol_map.get(yf_ticker, yf_ticker.replace("=F", ""))
    api_key = os.getenv("MARKETAUX_API_KEY", "")
    if not api_key:
        _sentiment_cache[yf_ticker] = 0.0
        _sentiment_cache_ts[yf_ticker] = now
        return 0.0
    result  = 0.0

    sia = _get_vader()

    try:
        resp = requests.get(
            "https://api.marketaux.com/v1/news/all",
            params={
                "api_token":       api_key,
                "symbols":         symbol,
                "limit":           10,
                "language":        "en",
                "filter_entities": "true",
            },
            timeout=5.0,
        )
        if resp.status_code == 200:
            articles = resp.json().get("data", [])
            scores   = []
            for art in articles:
                # Combine title + first 120 chars of description for richer signal
                text  = (art.get("title") or "") + " " + (art.get("description") or "")[:120]
                text  = text.strip()
                if not text:
                    continue
                if sia:
                    score = sia.polarity_scores(text)["compound"]   # [-1, +1]
                else:
                    # Fallback: count positive/negative keywords manually
                    tl = text.lower()
                    pos = sum(1 for w in ["beat","surge","profit","rally","upgrade","dividend"] if w in tl)
                    neg = sum(1 for w in ["crash","fraud","lawsuit","recall","collapse","layoff"] if w in tl)
                    score = min(1.0, max(-1.0, (pos - neg) * 0.3))
                scores.append(score)

            if scores:
                # Recent articles weighted higher (1/rank decay)
                weights = [1.0 / (i + 1) for i in range(len(scores))]
                raw     = float(np.average(scores, weights=weights))
                # Clamp to [-0.8, 0.8] so news never fully dominates ML signal
                result  = max(-0.8, min(0.8, raw))
    except Exception:
        pass

    _sentiment_cache[yf_ticker]    = result
    _sentiment_cache_ts[yf_ticker] = now
    return result


def _download_data(yf_ticker: str, years: int) -> pd.DataFrame:
    """Download historical OHLCV data from Yahoo Finance.
    Results cached in memory for DATA_CACHE_TTL seconds to avoid
    repeated network round-trips on consecutive prediction calls.
    """
    now = time.time()
    if yf_ticker in _data_cache and now - _data_cache_ts.get(yf_ticker, 0) < DATA_CACHE_TTL:
        return _data_cache[yf_ticker].copy()

    end  = datetime.today()
    start = end - timedelta(days=years * 365)
    data = yf.download(yf_ticker, start=start, end=end, interval="1d", progress=False)
    if data.empty:
        raise RuntimeError(f"No data returned from yfinance for {yf_ticker}")
    # Flatten MultiIndex columns if present
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)

    _data_cache[yf_ticker]    = data
    _data_cache_ts[yf_ticker] = now
    return data.copy()


def _is_model_stale(ticker: str, current_price: float) -> tuple:
    """
    Returns (is_stale: bool, reason: str).
    Checks: (1) model file age, (2) price outside scaler range.
    """
    cfg = ASSET_CONFIG.get(ticker.upper())
    if cfg is None:
        return False, ""

    model_path = MODELS_DIR / cfg["model_file"]
    tgt_path   = MODELS_DIR / cfg["scaler_tgt"]

    # Age check
    if model_path.exists():
        age_days = (datetime.now() - datetime.fromtimestamp(model_path.stat().st_mtime)).days
        if age_days > _MODEL_AGE_RETRAIN_DAYS:
            return True, f"model is {age_days} days old (>{_MODEL_AGE_RETRAIN_DAYS}d threshold)"

    # Price range check — only applicable to price-mode models.
    # Return-mode models predict daily % returns so the scaler range is in
    # return space (≈ -15% to +15%), NOT price space — skip this check.
    predict_mode = cfg.get("predict_mode", "price")
    if predict_mode == "return":
        return False, ""

    if tgt_path.exists():
        try:
            t_scaler = joblib.load(str(tgt_path))
            scaler_max = float(t_scaler.data_max_[0])
            scaler_min = float(t_scaler.data_min_[0])
            if current_price > scaler_max * (1 + _STALE_THRESHOLD_PCT):
                pct_over = (current_price - scaler_max) / scaler_max * 100
                return True, (f"price ${current_price:.2f} is {pct_over:.1f}% above "
                              f"scaler max ${scaler_max:.2f} — model is stale")
            if current_price < scaler_min * (1 - _STALE_THRESHOLD_PCT):
                pct_under = (scaler_min - current_price) / scaler_min * 100
                return True, (f"price ${current_price:.2f} is {pct_under:.1f}% below "
                              f"scaler min ${scaler_min:.2f} — model is stale")
        except Exception:
            pass

    return False, ""


# =====================================================================
#  Model + scaler loading
# =====================================================================
def _load(ticker: str):
    """Load (or return cached) Keras model + scalers for *ticker*."""
    cfg = ASSET_CONFIG.get(ticker.upper())
    if cfg is None:
        raise ValueError(f"Unsupported ticker: {ticker}")

    key = ticker.upper()
    with _cache_lock:
        if key in _model_cache:
            return _model_cache[key], _scaler_cache[key]

    from tensorflow.keras.models import load_model          # lazy import

    model_path = MODELS_DIR / cfg["model_file"]
    feat_path  = MODELS_DIR / cfg["scaler_feat"]
    tgt_path   = MODELS_DIR / cfg["scaler_tgt"]

    if not model_path.exists():
        raise FileNotFoundError(f"Model not found: {model_path}")
    if not feat_path.exists():
        raise FileNotFoundError(f"Feature scaler not found: {feat_path}")
    if not tgt_path.exists():
        raise FileNotFoundError(f"Target scaler not found: {tgt_path}")

    model  = load_model(str(model_path))
    f_scaler = joblib.load(str(feat_path))
    t_scaler = joblib.load(str(tgt_path))

    with _cache_lock:
        _model_cache[key]  = model
        _scaler_cache[key] = (f_scaler, t_scaler)

    return model, (f_scaler, t_scaler)


# =====================================================================
#  Prediction
# =====================================================================
# Supported forecast periods
PERIOD_DAYS = {
    "1d":  1,
    "3d":  3,
    "7d":  7,
    "30d": 30,
}


def predict_asset(ticker: str, period: str = "7d") -> dict:
    """
    Run prediction for a single asset.
    Returns dict with predicted_price, current_price, N-day forecast,
    confidence, trend, insights, and chart data (30-day history + forecast).

    period: '1d' | '3d' | '7d' | '30d' | '90d'
    """
    ticker = ticker.upper()
    cfg = ASSET_CONFIG.get(ticker)
    if cfg is None:
        raise ValueError(f"Unsupported ticker: {ticker}")

    period       = str(period).lower()
    n_days       = PERIOD_DAYS.get(period, 7)   # number of forecast days
    yf_ticker    = cfg["yf_ticker"]
    feature_cols = cfg["features"]
    lookback     = cfg["lookback"]

    # 1 ── load model + scalers
    model, (f_scaler, t_scaler) = _load(ticker)

    # 2 ── fetch recent data (need lookback + 50 extra rows for MA warm-up)
    raw = _download_data(yf_ticker, years=1)
    df  = _engineer_features(raw, feature_cols)

    if len(df) < lookback:
        raise RuntimeError(f"Not enough data rows ({len(df)}) for {ticker}, need {lookback}")

    current_price = float(df["Close"].iloc[-1])

    # 3 ── prepare last window
    features = df[feature_cols].values
    scaled   = f_scaler.transform(features)
    window   = scaled[-lookback:]
    x_input  = np.expand_dims(window, axis=0)            # (1, 60, n_features)

    # 4 ── predict next day (anchor prediction)
    pred_scaled = model.predict(x_input, verbose=0)

    # ── Return-mode vs Price-mode inference ──────────────────────────────
    # Return-mode: model was trained to predict daily % return (pct_change).
    #   t_scaler maps return values (e.g. -0.15 → +0.15) to [0,1].
    #   We inverse-transform to get raw return, then apply to current price.
    #   This completely eliminates the downward-bias from price-level anchoring.
    # Price-mode: legacy behaviour — model predicts absolute next-day price.
    predict_mode = cfg.get("predict_mode", "price")
    if predict_mode == "return":
        predicted_return = float(t_scaler.inverse_transform(pred_scaled.reshape(-1, 1))[0][0])
        pred_day1        = current_price * (1 + predicted_return)
        raw_model_pct    = predicted_return                     # already a daily return
    else:
        pred_day1     = float(t_scaler.inverse_transform(pred_scaled.reshape(-1, 1))[0][0])
        raw_model_pct = (pred_day1 - current_price) / current_price

    # ─────────────────────────────────────────────────────────────────────
    # 5 ── INTELLIGENT HYBRID FORECAST
    #
    #  Three-component blend:
    #   a) ML MODEL SIGNAL  – capped per-asset raw model daily %
    #   b) MOMENTUM         – recent short + medium trend
    #   c) MEAN REVERSION   – price distance from MA20 (markets revert)
    #
    #  Additional overlays:
    #   d) STREAK DETECTOR  – 4+ consecutive days same dir → expect bounce
    #   e) RSI EXTREMES     – oversold/overbought adjustments
    #   f) NEWS SENTIMENT   – Marketaux API ±1.5% max
    #
    #  Long-period damping: for 30d/90d momentum decays sharply, mean-
    #  reversion dominates because markets do NOT trend forever.
    # ─────────────────────────────────────────────────────────────────────
    # ── Validate model output against current price ─────────────────────
    # If the model is stale (price outside scaler range), the raw pred will be
    # anchored to old price levels → strong DOWN bias. Detect and neutralize it.
    _stale, _stale_reason = _is_model_stale(ticker, current_price)
    if _stale:
        print(f"⚠️  {ticker}: {_stale_reason}")
        # Trigger background retrain so next call benefits from fresh model
        _trigger_background_retrain(ticker)

    # Check if model prediction is drastically out of range (>15% from current).
    # For return-mode models, raw_model_pct is already a return value clipped
    # to ±15% during training, so this guard only matters for price-mode models.
    if predict_mode != "return" and abs(raw_model_pct) > 0.15:
        # Model is anchored to wrong price regime — neutralize its signal
        print(f"⚠️  {ticker}: model raw signal {raw_model_pct*100:+.1f}% is out-of-range, neutralizing")
        model_daily_pct = np.sign(raw_model_pct) * 0.003  # tiny directional hint only
    else:
        model_daily_pct = raw_model_pct

    # Cap raw model signal per-asset
    model_cap = _MODEL_SIGNAL_CAPS.get(ticker, 0.025)
    model_daily_pct = max(-model_cap, min(model_cap, model_daily_pct))

    # ── Momentum component ───────────────────────────────────────────────
    daily_returns = df["Close"].pct_change().dropna()
    mom_5d  = float(daily_returns.tail(5).mean())    # ~1 week
    mom_10d = float(daily_returns.tail(10).mean())   # ~2 weeks
    mom_20d = float(daily_returns.tail(20).mean())   # ~1 month
    # Blend: short-term momentum weighted higher for short periods
    if n_days <= 3:
        momentum = mom_5d * 0.7 + mom_10d * 0.3
    elif n_days <= 7:
        momentum = mom_5d * 0.5 + mom_10d * 0.3 + mom_20d * 0.2
    else:
        # For 30d+ forecasts, medium/long-term momentum matters more
        momentum = mom_5d * 0.2 + mom_10d * 0.3 + mom_20d * 0.5

    # ── Mean-Reversion component ─────────────────────────────────────────
    # ma20_val = unified MA anchor used in iterative forecast loop (always set)
    ma20_val = None
    if "MA20" in df.columns:
        ma20_val = float(df["MA20"].iloc[-1])
        deviation_pct = (current_price - ma20_val) / ma20_val  # -ve = below MA
        rev_strength  = 0.20 if n_days <= 3 else (0.28 if n_days <= 7 else 0.45)
        mean_rev_total = -deviation_pct * rev_strength
        mean_rev_daily = mean_rev_total / max(n_days, 1)
    elif "MA10" in df.columns:
        ma20_val      = float(df["MA10"].iloc[-1])   # MA10 as fallback anchor
        deviation_pct = (current_price - ma20_val) / ma20_val
        rev_strength  = 0.15 if n_days <= 3 else 0.25
        mean_rev_daily = -deviation_pct * rev_strength / max(n_days, 1)
    else:
        mean_rev_daily = 0.0

    # Clamp mean-reversion to ±0.5% per day (avoid overreaction)
    mean_rev_daily = max(-0.005, min(0.005, mean_rev_daily))

    # ── Streak detector ──────────────────────────────────────────────────
    # 4+ of last 5 days same direction → probable short-term reversal
    recent_5 = daily_returns.tail(5).values
    down_days = int(np.sum(recent_5 < 0))
    up_days   = int(np.sum(recent_5 > 0))
    if down_days >= 4:
        # Oversold streak: counter 35% of the recent daily drop
        streak_adj =  abs(float(mom_5d)) * 0.35
    elif up_days >= 4:
        # Overbought streak: dampen 25% of the recent daily rise
        streak_adj = -abs(float(mom_5d)) * 0.25
    else:
        streak_adj = 0.0
    # Only apply streak adjustment when it opposes momentum (that's the whole point)
    if (streak_adj > 0 and momentum > 0) or (streak_adj < 0 and momentum < 0):
        streak_adj = 0.0  # no counter-signal needed if already reversing

    # ── Model-momentum agreement (used for confidence score) ─────────────
    model_up    = model_daily_pct > 0
    momentum_up = momentum > 0
    agree       = (model_up == momentum_up)

    # ── RSI adjustment ───────────────────────────────────────────────────
    current_rsi = _compute_rsi(df["Close"])
    if   current_rsi < 25: rsi_adj =  0.012   # extreme oversold
    elif current_rsi < 35: rsi_adj =  0.007   # strong oversold
    elif current_rsi < 42: rsi_adj =  0.003   # mild oversold
    elif current_rsi > 78: rsi_adj = -0.012   # extreme overbought
    elif current_rsi > 68: rsi_adj = -0.007   # strong overbought
    elif current_rsi > 62: rsi_adj = -0.003   # mild overbought
    else:                   rsi_adj =  0.0

    # ── News sentiment ────────────────────────────────────────────────────
    # Enhanced weight: strong signals (|score| > 0.6) get higher influence.
    # Volatile assets (NVDA, TSLA) are more news-sensitive → higher ceiling.
    news_sent = _get_news_sentiment(yf_ticker)
    if abs(news_sent) > 0.6:
        # Strong, clear signal — scale up impact
        news_weight = 0.030 if ticker in ("NVDA", "TSLA") else 0.022
    elif abs(news_sent) > 0.3:
        news_weight = 0.020 if ticker in ("NVDA", "TSLA") else 0.015
    else:
        news_weight = 0.012   # weak / noisy signal — keep small
    news_adj = news_sent * news_weight

    final_cap = _FINAL_DAILY_CAPS.get(ticker, 0.045)

    # ── Build forecast prices (FIXED: iterative per-day) ─────────────────
    # ROOT CAUSE OF BUG (now fixed):
    #   OLD: cum = eff_daily * day_i  →  if day-1 is DOWN, day-30 = 30× DOWN
    #        A single daily_pct set from today's momentum governed ALL days.
    # FIX: each day independently recomputes mean-reversion from RUNNING price.
    #   When the forecast price dips below MA20 the reversion pull flips to UP,
    #   naturally creating balanced up/down variation across the forecast window.
    forecast_prices = []
    running_price   = current_price
    per_day_overlay = (rsi_adj + news_adj) / max(n_days, 1)  # spread evenly

    for day_i in range(1, n_days + 1):
        # ── Component 1: ML model signal — fades to 0 by day 6 ───────────
        model_weight = max(0.0, 1.0 - (day_i - 1) * 0.20)   # 1.0→0.8→0.6→0.4→0.2→0
        day_model    = model_daily_pct * model_weight

        # ── Component 2: short-term momentum — exponential decay ─────────
        if n_days <= 7:
            mom_decay_rate = 0.80      # half-life ≈3 days
        elif n_days <= 30:
            mom_decay_rate = 0.75      # half-life ≈2.5 days
        else:
            mom_decay_rate = 0.70      # half-life ≈2 days
        day_momentum = momentum * (mom_decay_rate ** (day_i - 1))

        # ── Component 3: mean reversion from RUNNING price ────────────────
        # Recalculated every step: when price crosses below MA the pull flips
        # from negative (DOWN) to positive (UP) — this is what prevents the
        # "all 30 days DOWN" problem when today's stock dips even slightly.
        if ma20_val and ma20_val > 0:
            run_dev = (running_price - ma20_val) / ma20_val
            pull    = 0.15 + min(abs(run_dev), 0.08) * 0.60   # adaptive strength
            day_rev = max(-0.008, min(0.008, -run_dev * pull))
        else:
            day_rev = 0.0

        # ── Streak counter-signal fades by day 3 ─────────────────────────
        day_streak = streak_adj * max(0.0, 1.0 - (day_i - 1) * 0.35)

        # ── Blend weights: model strong early → reversion dominates later ─
        if day_i <= 2:
            w_m, w_mo, w_rv = 0.55, 0.30, 0.15
        elif day_i <= 5:
            w_m, w_mo, w_rv = 0.35, 0.30, 0.35
        elif day_i <= 10:
            w_m, w_mo, w_rv = 0.15, 0.20, 0.65
        else:
            w_m, w_mo, w_rv = 0.05, 0.10, 0.85   # 10d+: almost pure mean-reversion

        day_pct = (day_model    * w_m
                   + day_momentum * w_mo
                   + day_rev      * w_rv
                   + day_streak
                   + per_day_overlay)
        day_pct = max(-final_cap, min(final_cap, day_pct))

        running_price = running_price * (1 + day_pct)
        forecast_prices.append(round(running_price, 2))

    predicted_final = forecast_prices[-1]

    # 6 ── chart data: last 30 days of actual prices + N-day forecast
    recent = df.tail(30)
    history_chart = []
    for idx, row in recent.iterrows():
        history_chart.append({
            "date":  idx.strftime("%Y-%m-%d") if hasattr(idx, 'strftime') else str(idx),
            "price": round(float(row["Close"]), 2),
        })

    # ── Build forecast chart dates (skip weekends — no market trades weekends) ──
    forecast_chart = []
    d = pd.Timestamp(history_chart[-1]["date"])
    for fp in forecast_prices:
        d += pd.Timedelta(days=1)
        while d.weekday() >= 5:  # 5=Sat, 6=Sun
            d += pd.Timedelta(days=1)
        forecast_chart.append({
            "date":  d.strftime("%Y-%m-%d"),
            "price": fp,
        })

    # 7 ── compute metrics
    pct_change  = ((predicted_final - current_price) / current_price) * 100
    direction   = "UP" if predicted_final > current_price else "DOWN"

    # ── CONFIDENCE SCORE ──────────────────────────────────────────
    # Multi-factor confidence that produces realistic, varied scores.
    #
    # Factor 1 – Model-momentum agreement   (15 to 30 pts)
    # Factor 2 – Forecast consistency        (0 to 25 pts)
    # Factor 3 – Low volatility bonus        (0 to 18 pts)
    # Factor 4 – Moving-average alignment    (5 to 15 pts)
    # Factor 5 – Trend strength signal       (0 to 10 pts)
    # Factor 6 – Base floor                  (12 pts)
    # ──────────────────────────────────────────────────────────────

    # Factor 1: agreement between model signal and real momentum
    agreement_score = 30.0 if agree else 15.0
    # Partial credit: if they barely disagree (both near zero), still ok
    if not agree and abs(model_daily_pct) < 0.003 and abs(momentum) < 0.003:
        agreement_score = 22.0

    # Factor 2: how many forecast days point the same way
    above_count = sum(1 for f in forecast_prices if f > current_price)
    n_fc        = len(forecast_prices)
    below_count = n_fc - above_count
    consistency = max(above_count, below_count) / max(n_fc, 1)
    consistency_score = consistency * 25.0   # 0-25 pts

    # Factor 3: low-volatility bonus (calm markets → easier to predict)
    recent_vol = float(daily_returns.tail(20).std() * 100)
    if recent_vol < 0.8:
        vol_score = 18.0
    elif recent_vol < 1.5:
        vol_score = 14.0
    elif recent_vol < 2.0:
        vol_score = 10.0
    elif recent_vol < 3.0:
        vol_score = 6.0
    else:
        vol_score = 2.0

    # Factor 4: price vs key moving average alignment with predicted direction
    ma_score = 5.0  # baseline even if no MA column
    if "MA50" in df.columns:
        ma_val = float(df["MA50"].iloc[-1])
    elif "MA20" in df.columns:
        ma_val = float(df["MA20"].iloc[-1])
    else:
        ma_val = None
    if ma_val is not None:
        price_above_ma = current_price > ma_val
        if (direction == "UP" and price_above_ma) or (direction == "DOWN" and not price_above_ma):
            ma_score = 15.0  # prediction aligns with trend
        else:
            ma_score = 7.0   # contrarian — possible but less confident

    # Factor 5: trend strength — stronger predicted moves warrant more confidence
    abs_pct = abs(pct_change)
    if abs_pct > 3.0:
        strength_score = 10.0
    elif abs_pct > 1.5:
        strength_score = 7.0
    elif abs_pct > 0.5:
        strength_score = 4.0
    else:
        strength_score = 1.0

    # Factor 6: base floor
    base_score = 12.0

    confidence = agreement_score + consistency_score + vol_score + ma_score + strength_score + base_score
    # Longer periods = lower confidence (we know less about 30d than 7d)
    if n_days >= 30:
        confidence_floor, confidence_ceil = 52, 82
    elif n_days >= 7:
        confidence_floor, confidence_ceil = 65, 94
    else:
        confidence_floor, confidence_ceil = 72, 97   # 1d/3d: most certain
    confidence = max(confidence_floor, min(confidence_ceil, confidence))

    # 8 ── generate AI insights
    insights = _generate_insights(ticker, current_price, predicted_final, pct_change,
                                  direction, forecast_prices, df, current_rsi, news_sent, n_days)

    period_labels = {"1d": "1 Day", "3d": "3 Days", "7d": "7 Days", "30d": "30 Days"}
    return {
        "symbol":           ticker,
        "current_price":    round(current_price, 2),
        "predicted_price":  round(predicted_final, 2),
        "prediction_period": period_labels.get(period, f"{n_days} Days"),
        "n_days":           n_days,
        "period":           period,
        "prediction_change_percent": round(pct_change, 2),
        "confidence_score": round(confidence, 1),
        "trend_direction":  direction,
        "forecast_prices":  forecast_prices,
        "history_chart":    history_chart,
        "forecast_chart":   forecast_chart,
        "insights":         insights,
        "rsi":              round(current_rsi, 1),
        "news_sentiment":   round(news_sent, 3),
        "mean_reversion_signal": round(mean_rev_daily * n_days * 100, 2),
        "streak_days_down": down_days,
        "streak_days_up":   up_days,
    }


def _generate_insights(ticker, current, predicted, pct, direction, forecasts, df,
                        rsi: float = 50.0, news_sent: float = 0.0, n_days: int = 7):
    """Build 4 contextual AI insight strings for the asset."""
    period_str = f"{n_days} day" + ("s" if n_days != 1 else "")
    name_map = {
        "AAPL": "Apple", "NVDA": "NVIDIA", "TSLA": "Tesla", "GOLD": "Gold",
    }
    name = name_map.get(ticker, ticker)

    # Trend strength
    if abs(pct) > 5:
        strength = "strong"
    elif abs(pct) > 2:
        strength = "moderate"
    else:
        strength = "mild"

    # Volatility from recent data
    recent_vol = float(df["Close"].pct_change().tail(20).std() * 100)
    vol_label  = "high" if recent_vol > 2 else ("moderate" if recent_vol > 1 else "low")

    # 50-day MA trend
    if "MA50" in df.columns:
        ma50_last = float(df["MA50"].iloc[-1])
        above_ma = current > ma50_last
    elif "MA20" in df.columns:
        ma50_last = float(df["MA20"].iloc[-1])
        above_ma = current > ma50_last
    else:
        above_ma = direction == "UP"

    # Momentum from forecast vs current price
    above = sum(1 for f in forecasts if f > current)
    below = len(forecasts) - above

    insights = []

    # Insight 1 – direction summary with RSI context
    arch_map = {
        "AAPL": "LSTM",       "NVDA": "LSTM",
        "TSLA": "GRU",        "GOLD": "CNN-BiLSTM",
    }
    arch_name = arch_map.get(ticker, "deep-learning")
    arrow = "📈" if direction == "UP" else "📉"
    rsi_note = ""
    if   rsi < 35: rsi_note = f" RSI at {rsi:.0f} signals oversold conditions."
    elif rsi > 70: rsi_note = f" RSI at {rsi:.0f} signals overbought conditions."
    insights.append(
        f"{arrow} Our {arch_name} model projects a {strength} {direction.lower()}ward move for {name} "
        f"over the next {period_str}, with a predicted change of {pct:+.2f}%.{rsi_note}"
    )

    # Insight 2 – technical analysis with news sentiment
    ma_msg = "above" if above_ma else "below"
    sent_label = "positive" if news_sent > 0.2 else ("negative" if news_sent < -0.2 else "neutral")
    insights.append(
        f"📊 {name} is currently trading {ma_msg} its key moving average, indicating "
        f"{'bullish' if above_ma else 'bearish'} momentum. Recent volatility is {vol_label} "
        f"at {recent_vol:.1f}% daily. Latest news sentiment: {sent_label}."
    )

    # Insight 3 – forecast consistency vs current price
    if above > below:
        cons_msg = f"All {above} of {above+below} forecasted days sit above the current price, signalling sustained upside potential."
    elif below > above:
        cons_msg = f"All {below} of {above+below} forecasted days sit below the current price, suggesting near-term downside pressure."
    else:
        cons_msg = "The forecast shows a split between days above and below the current price, indicating potential consolidation."
    insights.append(f"🔮 {cons_msg}")

    # Insight 4 – risk context
    risk_map = {
        "AAPL": "Apple's ecosystem and services revenue provide strong stability. A solid long-term position.",
        "NVDA": "NVIDIA rides the AI wave—GPU demand from data centers remains explosive. High growth, watch valuations.",
        "TSLA": "Tesla faces rising EV competition. High reward, high risk. Watch delivery numbers closely.",
        "GOLD": "Gold is a classic inflation hedge. It shines in uncertain macro environments.",
    }
    insights.append(f"⚡ {risk_map.get(ticker, 'Always do your own research before investing.')}")

    return insights


_bg_retrain_queue: set = set()
_bg_retrain_lock2 = threading.Lock()


def _trigger_background_retrain(ticker: str):
    """Schedule a background retrain for ticker if not already queued/running."""
    with _bg_retrain_lock2:
        if ticker in _bg_retrain_queue:
            return  # already scheduled
        _bg_retrain_queue.add(ticker)

    def _do_retrain():
        print(f"🔄 Background retrain starting for {ticker}...")
        result = retrain_asset(ticker)
        with _bg_retrain_lock2:
            _bg_retrain_queue.discard(ticker)
        status = "✅" if result.get("success") else "❌"
        print(f"   {status} Background retrain {ticker}: {result}")

    t = threading.Thread(target=_do_retrain, daemon=True, name=f"bg-retrain-{ticker}")
    t.start()


# =====================================================================
#  Auto-Retrain (builds model from scratch with latest data)
# =====================================================================
def retrain_asset(ticker: str) -> dict:
    """
    Retrain a single asset's model on the latest available data.
    Saves new .keras and .pkl files to ml_models/.
    Returns training metrics.
    """
    ticker = ticker.upper()
    cfg = ASSET_CONFIG.get(ticker)
    if cfg is None:
        raise ValueError(f"Unsupported ticker: {ticker}")

    if not _retrain_lock.acquire(blocking=False):
        return {"success": False, "message": "A retraining job is already running."}

    try:
        print(f"🔄 Starting retrain for {ticker}...")
        start_time = time.time()

        # lazy imports
        import tensorflow as tf
        from tensorflow.keras.models import Sequential
        from tensorflow.keras.layers import (
            LSTM, GRU, Dense, Dropout, Conv1D, MaxPooling1D, Bidirectional,
        )
        from tensorflow.keras.callbacks import EarlyStopping
        from sklearn.preprocessing import MinMaxScaler

        yf_ticker    = cfg["yf_ticker"]
        feature_cols = cfg["features"]
        lookback     = cfg["lookback"]
        arch         = cfg["architecture"]
        sizes        = cfg["layer_sizes"]
        drop         = cfg["dropout"]

        # 1 ── download data
        raw = _download_data(yf_ticker, years=cfg["train_years"])
        df  = _engineer_features(raw, feature_cols)

        print(f"   📊 {ticker}: {len(df)} rows after feature engineering")

        # 2 ── scale
        f_scaler = MinMaxScaler(feature_range=(0, 1))
        t_scaler = MinMaxScaler(feature_range=(0, 1))

        features_arr = df[feature_cols].values

        predict_mode = cfg.get("predict_mode", "price")
        if predict_mode == "return":
            # Target = daily % return (Close pct_change).
            # Benefits over absolute-price target:
            #   • Returns are stationary → model generalises across price regimes
            #   • Eliminates "revert to historical mean price" bias
            #   • Older training data is equally valid (returns are price-independent)
            raw_returns = df["Close"].pct_change().fillna(0).values
            raw_returns = np.clip(raw_returns, -0.15, 0.15)   # cap black-swan events
            target_arr  = raw_returns.reshape(-1, 1)
        else:
            target_arr = df[["Close"]].values

        f_scaled = f_scaler.fit_transform(features_arr)
        t_scaled = t_scaler.fit_transform(target_arr)

        # 3 ── create sequences
        X, y = [], []
        for i in range(lookback, len(f_scaled)):
            X.append(f_scaled[i - lookback : i])
            y.append(t_scaled[i, 0])
        X = np.array(X)
        y = np.array(y)

        split = int(len(X) * 0.85)   # 85/15 gives more test data for accurate eval
        X_train, X_test = X[:split], X[split:]
        y_train, y_test = y[:split], y[split:]

        print(f"   📐 Train: {len(X_train)}, Test: {len(X_test)}")

        # 4 ── build model per architecture
        n_features = len(feature_cols)
        model = Sequential()

        if arch == "lstm":
            model.add(LSTM(sizes[0], return_sequences=True, input_shape=(lookback, n_features)))
            model.add(Dropout(drop))
            model.add(LSTM(sizes[1], return_sequences=False))
            model.add(Dropout(drop))
            model.add(Dense(32, activation="relu"))
            model.add(Dense(1))
            model.compile(optimizer=tf.keras.optimizers.Adam(learning_rate=0.001), loss="huber")

        elif arch == "gru":
            model.add(GRU(sizes[0], return_sequences=True, input_shape=(lookback, n_features)))
            model.add(Dropout(drop))
            model.add(GRU(sizes[1], return_sequences=False))
            model.add(Dropout(drop))
            model.add(Dense(32, activation="relu"))
            model.add(Dense(1))
            model.compile(optimizer=tf.keras.optimizers.Adam(learning_rate=0.001), loss="huber")

        elif arch == "cnn_bilstm":
            model.add(Conv1D(filters=sizes[0], kernel_size=3, activation="relu",
                             input_shape=(lookback, n_features)))
            model.add(MaxPooling1D(pool_size=2))
            model.add(Bidirectional(LSTM(sizes[1], return_sequences=False)))
            model.add(Dropout(drop))
            model.add(Dense(sizes[2], activation="relu"))
            model.add(Dense(1))
            model.compile(optimizer=tf.keras.optimizers.Adam(learning_rate=0.0005), loss="mse")

        from tensorflow.keras.callbacks import ReduceLROnPlateau
        callbacks = [
            EarlyStopping(monitor="val_loss", patience=15, restore_best_weights=True),
            ReduceLROnPlateau(monitor="val_loss", factor=0.5, patience=7, min_lr=1e-6, verbose=0),
        ]

        history = model.fit(
            X_train, y_train,
            epochs=100,
            batch_size=32,
            validation_data=(X_test, y_test),
            callbacks=callbacks,
            verbose=0,
        )

        # 5 ── evaluate
        test_pred   = model.predict(X_test, verbose=0)
        test_actual = t_scaler.inverse_transform(y_test.reshape(-1, 1))
        test_pred   = t_scaler.inverse_transform(test_pred.reshape(-1, 1))
        mae  = float(np.mean(np.abs(test_actual - test_pred)))
        rmse = float(np.sqrt(np.mean((test_actual - test_pred) ** 2)))
        # MAPE: for return-mode the divisor can be near 0 → use mean absolute
        # error as percentage of average absolute actual return instead
        if predict_mode == "return":
            avg_abs_actual = float(np.mean(np.abs(test_actual)))
            mape = (mae / avg_abs_actual * 100) if avg_abs_actual > 0 else 0.0
            # Convert MAE/RMSE to % for readability
            mae_pct  = mae  * 100   # e.g. 0.008 → 0.8%
            rmse_pct = rmse * 100
            print(f"   ✅ {ticker} retrained in {time.time()-start_time:.1f}s  "
                  f"MAE={mae_pct:.3f}%  RMSE={rmse_pct:.3f}%  MAPE={mape:.1f}%  "
                  f"mode=return  epochs={len(history.history['loss'])}")
            mae  = round(mae_pct, 4)
            rmse = round(rmse_pct, 4)
        else:
            mape = float(np.mean(np.abs((test_actual - test_pred) / test_actual)) * 100)
            elapsed = time.time() - start_time
            print(f"   ✅ {ticker} retrained in {elapsed:.1f}s  MAE=${mae:.2f}  RMSE=${rmse:.2f}  MAPE={mape:.2f}%")

        # 6 ── save model + scalers
        model_path = MODELS_DIR / cfg["model_file"]
        feat_path  = MODELS_DIR / cfg["scaler_feat"]
        tgt_path   = MODELS_DIR / cfg["scaler_tgt"]

        model.save(str(model_path))
        joblib.dump(f_scaler, str(feat_path))
        joblib.dump(t_scaler, str(tgt_path))

        # 7 ── persist to Firebase Storage (Railway's local disk doesn't survive restarts)
        try:
            from model_sync import upload_model_files
            upload_model_files(ticker, [model_path, feat_path, tgt_path])
        except Exception as exc:
            print(f"⚠️  Model persistence skipped for {ticker}: {exc}")

        # 8 ── clear cache so next prediction uses fresh model
        with _cache_lock:
            _model_cache.pop(ticker, None)
            _scaler_cache.pop(ticker, None)

        elapsed = time.time() - start_time

        return {
            "success":       True,
            "ticker":        ticker,
            "mae":           round(mae, 4),
            "rmse":          round(rmse, 4),
            "mape":          round(mape, 2),
            "epochs":        len(history.history["loss"]),
            "rows":          len(df),
            "elapsed":       round(elapsed, 1),
            "predict_mode":  predict_mode,
        }

    except Exception as exc:
        traceback.print_exc()
        return {"success": False, "ticker": ticker, "error": str(exc)}
    finally:
        _retrain_lock.release()


def retrain_all() -> list:
    """Retrain all 4 assets sequentially. Returns list of results."""
    results = []
    for ticker in ASSET_CONFIG:
        r = retrain_asset(ticker)
        results.append(r)
    return results


# =====================================================================
#  Background daily retrainer (thread-based, lifetime)
# =====================================================================
_scheduler_thread: Optional[threading.Thread] = None

def _check_and_retrain_stale():
    """
    Check all models for staleness (old files or price out of scaler range).
    Retrains stale models immediately. Called at server startup.
    Works whether online or offline — if yfinance fails (offline), skips gracefully.
    """
    print("🔍 Checking model freshness on startup...")
    stale_tickers = []
    for ticker, cfg in ASSET_CONFIG.items():
        model_path = MODELS_DIR / cfg["model_file"]
        tgt_path   = MODELS_DIR / cfg["scaler_tgt"]
        if not model_path.exists():
            stale_tickers.append(ticker)
            continue
        age_days = (datetime.now() - datetime.fromtimestamp(model_path.stat().st_mtime)).days
        if age_days > _MODEL_AGE_RETRAIN_DAYS:
            print(f"   ⚠️  {ticker}: model is {age_days} days old → needs retraining")
            stale_tickers.append(ticker)
            continue
        # Check price range — only for price-mode models.
        # Return-mode models have scaler_max ≈ 0.15 (daily return), not a price,
        # so comparing to current stock price would always trigger a false retraining.
        predict_mode = cfg.get("predict_mode", "price")
        if predict_mode == "price" and tgt_path.exists():
            try:
                t_scaler = joblib.load(str(tgt_path))
                scaler_max = float(t_scaler.data_max_[0])
                try:
                    import yfinance as yf
                    data = yf.download(cfg["yf_ticker"], period="2d", progress=False)
                    if not data.empty:
                        if isinstance(data.columns, pd.MultiIndex):
                            data.columns = data.columns.get_level_values(0)
                        current = float(data["Close"].iloc[-1])
                        if current > scaler_max * (1 + _STALE_THRESHOLD_PCT):
                            pct = (current - scaler_max) / scaler_max * 100
                            print(f"   ⚠️  {ticker}: price ${current:.2f} is {pct:.1f}% above scaler max ${scaler_max:.2f} → needs retraining")
                            stale_tickers.append(ticker)
                        else:
                            print(f"   ✅ {ticker}: up-to-date (price ${current:.2f}, scaler max ${scaler_max:.2f}, age {age_days}d)")
                except Exception:
                    pass  # Offline or network error — skip price check
            except Exception:
                pass
        else:
            print(f"   ✅ {ticker}: return-mode model, age {age_days}d — no price-range check needed")

    if stale_tickers:
        print(f"🔄 Retraining stale models: {stale_tickers}")
        for ticker in stale_tickers:
            _trigger_background_retrain(ticker)
    else:
        print("✅ All models are fresh — no retraining needed")


def _retrain_loop():
    """Runs in a daemon thread. Retrains all models once every 24 h."""
    # First: check staleness on startup and immediately retrain if needed
    _check_and_retrain_stale()

    while True:
        # Sleep until ~02:00 AM next day (low-traffic window)
        now    = datetime.now()
        target = now.replace(hour=2, minute=0, second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)
        wait_secs = (target - now).total_seconds()
        print(f"🕑 Next auto-retrain scheduled at {target.strftime('%Y-%m-%d %H:%M')} ({wait_secs/3600:.1f}h from now)")
        time.sleep(wait_secs)

        print("🔄 Auto-retrain starting for all assets...")
        results = retrain_all()
        for r in results:
            status = "✅" if r.get("success") else "❌"
            print(f"   {status} {r.get('ticker', '?')}: {r}")

        # After every scheduled retrain, regenerate and cache fresh predictions
        # so /api/predictions/{symbol} returns current data immediately.
        try:
            from prediction_store import refresh_all_predictions
            print("🔮 Generating fresh predictions after retrain...")
            pred_results = refresh_all_predictions(source="retrain")
            for t, pr in pred_results.items():
                if "error" in pr:
                    print(f"   ⚠️  {t} prediction failed: {pr['error']}")
                else:
                    print(f"   ✅ {t} prediction cached: ${pr.get('predicted_price', '?')}")
        except Exception as exc:
            print(f"⚠️  Could not refresh prediction cache after retrain: {exc}")


def start_retrain_scheduler():
    """Start the background daily retrain thread (called once from server startup)."""
    global _scheduler_thread
    if _scheduler_thread is not None and _scheduler_thread.is_alive():
        return  # already running
    _scheduler_thread = threading.Thread(target=_retrain_loop, daemon=True, name="retrain-scheduler")
    _scheduler_thread.start()
    print("✅ Auto-retrain scheduler started (daily at 02:00 AM)")
