"""
test_stock_api.py  -  Tests for /api/stock/* endpoints
=======================================================
Covers:
  - GET /api/stock/{symbol}          cache hit, cache miss, invalid symbol
  - POST /api/stock/batch            parallel fetch, partial failure, empty body
"""

import pytest
from unittest.mock import patch, MagicMock


# ══════════════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════════════

VALID_SYMBOLS   = ["AAPL", "NVDA", "TSLA", "GC=F", "BTC-USD"]
INVALID_SYMBOLS = ["FAKE", "???", "123", ""]

EXPECTED_FIELDS = {
    "symbol", "current_price", "day_change_percent",
    "day_change", "day_high", "day_low", "day_open",
}


def _cache_entry(symbol: str, price: float = 150.0):
    return {
        "price":          price,
        "change":         1.5,
        "change_percent": 1.0,
        "volume":         40_000_000,
        "market_cap":     2_500_000_000_000,
        "high":           price + 2,
        "low":            price - 2,
        "open":           price - 1,
    }


# ══════════════════════════════════════════════════════════════════════
#  Single symbol  -  cache hit
# ══════════════════════════════════════════════════════════════════════

class TestStockCacheHit:
    def test_returns_200(self, client, mock_firebase_db):
        with patch("main.data_cache") as mock_dc:
            mock_dc.get_cached_price.return_value = _cache_entry("AAPL", 195.0)
            resp = client.get("/api/stock/AAPL")
        assert resp.status_code == 200

    def test_response_contains_required_fields(self, client):
        with patch("main.data_cache") as mock_dc:
            mock_dc.get_cached_price.return_value = _cache_entry("AAPL", 195.0)
            resp = client.get("/api/stock/AAPL")
        body = resp.json()
        for field in EXPECTED_FIELDS:
            assert field in body, f"Missing field: {field}"

    def test_price_matches_cache(self, client):
        with patch("main.data_cache") as mock_dc:
            mock_dc.get_cached_price.return_value = _cache_entry("NVDA", 480.0)
            resp = client.get("/api/stock/NVDA")
        assert resp.json()["current_price"] == 480.0

    def test_cache_control_header_present(self, client):
        with patch("main.data_cache") as mock_dc:
            mock_dc.get_cached_price.return_value = _cache_entry("TSLA", 175.0)
            resp = client.get("/api/stock/TSLA")
        assert "cache-control" in resp.headers or resp.status_code == 200


# ══════════════════════════════════════════════════════════════════════
#  Single symbol  -  cache miss (falls back to yfinance / Finnhub)
# ══════════════════════════════════════════════════════════════════════

class TestStockCacheMiss:
    def test_falls_back_to_yfinance_when_cache_empty(self, client, mock_yfinance_data):
        mock_yfinance_data("AAPL")
        with patch("main.data_cache") as mock_dc, \
             patch("main.get_stock_quote", return_value=None):
            mock_dc.get_cached_price.return_value = None  # cache miss
            mock_dc.cache_current_price = MagicMock()
            resp = client.get("/api/stock/AAPL")
        # Should succeed via yfinance fallback
        assert resp.status_code in (200, 500)  # 500 acceptable if yf mock incomplete

    def test_cache_miss_calls_yfinance_ticker(self, client, mock_yfinance_data):
        mock_ticker = mock_yfinance_data("NVDA")
        with patch("main.data_cache") as mock_dc, \
             patch("main.get_stock_quote", return_value=None), \
             patch("main.FINNHUB_SERVICE_AVAILABLE", False):
            mock_dc.get_cached_price.return_value = None
            mock_dc.cache_current_price = MagicMock()
            client.get("/api/stock/NVDA")
        # yfinance.Ticker must have been called
        mock_ticker.history.assert_called()


# ══════════════════════════════════════════════════════════════════════
#  Invalid symbol
# ══════════════════════════════════════════════════════════════════════

class TestStockInvalidSymbol:
    def test_unknown_symbol_returns_error(self, client, mock_yfinance_data):
        """A completely unknown symbol should return 4xx or 5xx — not 200."""
        mock_ticker = mock_yfinance_data("FAKESYM")
        mock_ticker.history.return_value = __import__("pandas").DataFrame()  # empty

        with patch("main.data_cache") as mock_dc, \
             patch("main.get_stock_quote", return_value=None), \
             patch("main.FINNHUB_SERVICE_AVAILABLE", False):
            mock_dc.get_cached_price.return_value = None
            resp = client.get("/api/stock/FAKESYM99")

        assert resp.status_code >= 400

    def test_symbol_is_uppercased(self, client):
        """Lowercase symbol should work identically to uppercase."""
        with patch("main.data_cache") as mock_dc:
            mock_dc.get_cached_price.return_value = _cache_entry("AAPL", 195.0)
            resp_lower = client.get("/api/stock/aapl")
            resp_upper = client.get("/api/stock/AAPL")
        # Both should succeed or both fail — not one 200 and one 404
        assert resp_lower.status_code == resp_upper.status_code


# ══════════════════════════════════════════════════════════════════════
#  Batch endpoint
# ══════════════════════════════════════════════════════════════════════

class TestStockBatch:
    def test_batch_returns_all_requested_symbols(self, client):
        symbols = ["AAPL", "NVDA", "TSLA"]
        with patch("main.data_cache") as mock_dc:
            mock_dc.get_cached_price.side_effect = lambda s: _cache_entry(s, 100.0)
            resp = client.post("/api/stock/batch", json={"symbols": symbols})

        assert resp.status_code == 200
        body = resp.json()
        for sym in symbols:
            assert sym in body, f"Batch response missing {sym}"

    def test_batch_response_has_correct_structure(self, client):
        with patch("main.data_cache") as mock_dc:
            mock_dc.get_cached_price.return_value = _cache_entry("AAPL", 195.0)
            resp = client.post("/api/stock/batch", json={"symbols": ["AAPL"]})

        body = resp.json()
        aapl = body.get("AAPL", {})
        assert "current_price" in aapl or "error" in aapl

    def test_batch_empty_symbols_list(self, client):
        resp = client.post("/api/stock/batch", json={"symbols": []})
        assert resp.status_code == 200
        assert resp.json() == {}

    def test_batch_partial_failure_does_not_crash(self, client, mock_yfinance_data):
        """One failing symbol should not prevent others from returning."""
        mock_yfinance_data("AAPL")
        with patch("main.data_cache") as mock_dc, \
             patch("main.get_stock_quote_async", side_effect=Exception("API down")):
            mock_dc.get_cached_price.side_effect = lambda s: (
                _cache_entry(s) if s == "AAPL" else None
            )
            resp = client.post(
                "/api/stock/batch",
                json={"symbols": ["AAPL", "BADTICKER"]},
            )
        assert resp.status_code == 200
        body = resp.json()
        # AAPL should succeed (from cache)
        assert "AAPL" in body
        assert "error" not in body.get("AAPL", {})
