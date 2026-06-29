"""
conftest.py  -  shared pytest fixtures for NeuroSight tests
=============================================================
Run from the  backend/  directory:

    cd backend
    pytest tests/ -v

All Firebase and yfinance calls are mocked so tests run
without a real internet connection or service account.
"""

import sys
import os
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import datetime

import pandas as pd
import numpy as np
import pytest

# ── make sure  backend/  is on the path ───────────────────────────────
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))


# ══════════════════════════════════════════════════════════════════════
#  Firebase / Firestore mocks
#  Applied at session scope so the heavy Firebase SDK is never touched.
# ══════════════════════════════════════════════════════════════════════

def _make_mock_doc(doc_id: str, data: dict):
    """Return a MagicMock that behaves like a Firestore DocumentSnapshot."""
    doc = MagicMock()
    doc.id = doc_id
    doc.exists = True
    doc.to_dict.return_value = data
    doc.reference = MagicMock()
    doc.reference.update = MagicMock()
    doc.reference.delete = MagicMock()
    return doc


@pytest.fixture(scope="session")
def mock_firebase_db():
    """
    Session-scoped mock of the Firestore client.

    Usage in tests:
        def test_something(mock_firebase_db):
            mock_firebase_db.collection.return_value...
    """
    db = MagicMock()

    # Default: empty collection (no users found)
    empty_query = MagicMock()
    empty_query.get.return_value = []
    empty_query.stream.return_value = iter([])
    empty_query.limit.return_value = empty_query
    empty_query.where.return_value = empty_query
    empty_query.order_by.return_value = empty_query

    collection_mock = MagicMock()
    collection_mock.where.return_value = empty_query
    collection_mock.stream.return_value = iter([])
    collection_mock.order_by.return_value = empty_query
    collection_mock.document.return_value = MagicMock()

    db.collection.return_value = collection_mock
    return db


@pytest.fixture(scope="session")
def _firebase_patches(mock_firebase_db):
    """
    Patch firebase_admin so importing  main.py  never touches real Firebase.
    This runs once per test session.
    """
    mock_app = MagicMock()

    with (
        patch("firebase_admin._apps", {"[DEFAULT]": mock_app}),
        patch("firebase_admin.initialize_app", return_value=mock_app),
        patch("firebase_admin.credentials.Certificate", return_value=MagicMock()),
        patch("firebase_admin.firestore.client", return_value=mock_firebase_db),
        patch("firebase_admin.firestore.FieldFilter", side_effect=lambda f, op, v: (f, op, v)),
    ):
        yield


# ══════════════════════════════════════════════════════════════════════
#  FastAPI TestClient
# ══════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="session")
def client(_firebase_patches):
    """
    FastAPI TestClient with Firebase fully mocked.
    Import of  main.py  happens AFTER patches are active.
    """
    from fastapi.testclient import TestClient

    # Patch the prediction engine startup so no TensorFlow loading occurs
    with (
        patch("prediction_engine.start_retrain_scheduler"),
        patch("prediction_engine._check_and_retrain_stale"),
    ):
        import main as app_module
        # Override the module-level  db  with our mock
        app_module.db = _firebase_patches if hasattr(_firebase_patches, "collection") else MagicMock()

        with TestClient(app_module.app, raise_server_exceptions=False) as c:
            yield c


# ══════════════════════════════════════════════════════════════════════
#  yfinance mock data
# ══════════════════════════════════════════════════════════════════════

def _build_ohlcv(ticker: str, rows: int = 5) -> pd.DataFrame:
    """Build a minimal OHLCV DataFrame that mimics  yf.Ticker.history()."""
    prices = {
        "AAPL": 195.0,
        "NVDA": 480.0,
        "TSLA": 175.0,
        "GC=F": 2320.0,
        "BTC-USD": 67000.0,
    }
    base = prices.get(ticker, 100.0)
    idx = pd.date_range(end=datetime.today(), periods=rows, freq="B")
    return pd.DataFrame(
        {
            "Open":   np.linspace(base * 0.99, base, rows),
            "High":   np.linspace(base * 1.01, base * 1.02, rows),
            "Low":    np.linspace(base * 0.97, base * 0.98, rows),
            "Close":  np.linspace(base * 0.995, base, rows),
            "Volume": np.full(rows, 50_000_000, dtype=int),
        },
        index=idx,
    )


@pytest.fixture
def mock_yfinance_data():
    """
    Fixture that patches  yfinance.Ticker  for the duration of a single test.

    Usage:
        def test_price(client, mock_yfinance_data):
            mock_yfinance_data("AAPL")
            resp = client.get("/api/stock/AAPL")
    """
    active_patches = []

    def _activate(symbol: str = "AAPL"):
        df = _build_ohlcv(symbol)

        mock_ticker = MagicMock()
        mock_ticker.history.return_value = df
        mock_ticker.info = {
            "currentPrice": float(df["Close"].iloc[-1]),
            "regularMarketPrice": float(df["Close"].iloc[-1]),
            "marketCap": 3_000_000_000_000,
            "volume": 50_000_000,
            "regularMarketVolume": 50_000_000,
            "dayHigh": float(df["High"].iloc[-1]),
            "dayLow": float(df["Low"].iloc[-1]),
            "regularMarketChange": 1.5,
            "regularMarketChangePercent": 0.77,
        }

        p = patch("yfinance.Ticker", return_value=mock_ticker)
        p.start()
        active_patches.append(p)
        return mock_ticker

    yield _activate

    for p in active_patches:
        p.stop()


# ══════════════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════════════

@pytest.fixture
def admin_doc():
    """A Firestore DocumentSnapshot representing an admin user."""
    from passlib.context import CryptContext
    ctx = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
    return _make_mock_doc(
        "admin-doc-001",
        {
            "name": "Test Admin",
            "email": "admin@neurosight.ai",
            "password_hash": ctx.hash("NeuroAdmin@2026!"),
            "role": "admin",
            "is_verified": True,
            "created_at": datetime.utcnow(),
        },
    )


@pytest.fixture
def regular_user_doc():
    """A Firestore DocumentSnapshot representing a normal verified user."""
    from passlib.context import CryptContext
    ctx = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
    return _make_mock_doc(
        "user-doc-002",
        {
            "name": "Test User",
            "email": "user@example.com",
            "password_hash": ctx.hash("UserPass@123"),
            "role": "user",
            "is_verified": True,
            "created_at": datetime.utcnow(),
        },
    )
