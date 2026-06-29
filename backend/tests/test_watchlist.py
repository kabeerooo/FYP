"""
test_watchlist.py  -  Tests for /api/watchlist/* endpoints
===========================================================
Covers:
  - GET  /api/watchlist         list user's watchlist
  - POST /api/watchlist         add symbol
  - DELETE /api/watchlist/{sym} remove symbol
  - GET  /api/watchlist/alerts  price alerts list
  - POST /api/watchlist/alerts  create alert
"""

import pytest
from unittest.mock import MagicMock, patch


# ══════════════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════════════

USER_ID = "test-user-id-001"

# All watchlist routes expect this header to identify the user
AUTH_HEADERS = {"X-User-Id": USER_ID}

SAMPLE_WATCHLIST = ["AAPL", "NVDA", "TSLA"]


def _wl_doc(symbols: list):
    """Return a Firestore document mock containing a watchlist."""
    doc = MagicMock()
    doc.exists = True
    doc.to_dict.return_value = {"watchlist": symbols, "user_id": USER_ID}
    doc.reference = MagicMock()
    doc.reference.update = MagicMock()
    return doc


def _alert_doc(symbol: str, target_price: float, direction: str = "above"):
    doc = MagicMock()
    doc.id = f"alert-{symbol}"
    doc.to_dict.return_value = {
        "user_id":      USER_ID,
        "symbol":       symbol,
        "target_price": target_price,
        "direction":    direction,
        "created_at":   "2024-01-01T00:00:00",
        "triggered":    False,
    }
    return doc


# ══════════════════════════════════════════════════════════════════════
#  Watchlist – Read
# ══════════════════════════════════════════════════════════════════════

class TestGetWatchlist:
    ENDPOINT = "/api/watchlist"

    def test_returns_200_with_user_header(self, client, mock_firebase_db):
        doc = _wl_doc(SAMPLE_WATCHLIST)
        mock_firebase_db.collection.return_value.document.return_value.get.return_value = doc

        with patch("user_preferences.db", mock_firebase_db):
            resp = client.get(self.ENDPOINT, headers=AUTH_HEADERS)

        assert resp.status_code == 200

    def test_response_is_list_of_symbols(self, client, mock_firebase_db):
        doc = _wl_doc(SAMPLE_WATCHLIST)
        mock_firebase_db.collection.return_value.document.return_value.get.return_value = doc

        with patch("user_preferences.db", mock_firebase_db):
            resp = client.get(self.ENDPOINT, headers=AUTH_HEADERS)

        body = resp.json()
        assert isinstance(body, list) or "watchlist" in body

    def test_empty_watchlist_returns_empty_list(self, client, mock_firebase_db):
        doc = _wl_doc([])
        mock_firebase_db.collection.return_value.document.return_value.get.return_value = doc

        with patch("user_preferences.db", mock_firebase_db):
            resp = client.get(self.ENDPOINT, headers=AUTH_HEADERS)

        assert resp.status_code == 200
        body = resp.json()
        watchlist = body if isinstance(body, list) else body.get("watchlist", [])
        assert watchlist == []

    def test_missing_user_header_returns_error(self, client):
        """Without X-User-Id the endpoint must return 4xx."""
        resp = client.get(self.ENDPOINT)
        assert resp.status_code >= 400


# ══════════════════════════════════════════════════════════════════════
#  Watchlist – Add symbol
# ══════════════════════════════════════════════════════════════════════

class TestAddToWatchlist:
    ENDPOINT = "/api/watchlist"

    def test_add_valid_symbol_returns_success(self, client, mock_firebase_db):
        existing = _wl_doc(["AAPL"])
        existing.reference.update = MagicMock()
        mock_firebase_db.collection.return_value.document.return_value.get.return_value = existing

        with patch("user_preferences.db", mock_firebase_db):
            resp = client.post(
                self.ENDPOINT,
                json={"symbol": "NVDA"},
                headers=AUTH_HEADERS,
            )

        assert resp.status_code in (200, 201)

    def test_add_duplicate_symbol_returns_error_or_idempotent(self, client, mock_firebase_db):
        """Adding an already-watched symbol should not crash the server."""
        existing = _wl_doc(["AAPL", "NVDA"])
        existing.reference.update = MagicMock()
        mock_firebase_db.collection.return_value.document.return_value.get.return_value = existing

        with patch("user_preferences.db", mock_firebase_db):
            resp = client.post(
                self.ENDPOINT,
                json={"symbol": "AAPL"},
                headers=AUTH_HEADERS,
            )

        # Either 200 (idempotent) or 400 (duplicate rejected) — both are fine
        assert resp.status_code in (200, 400)

    def test_add_missing_symbol_field_returns_422(self, client):
        resp = client.post(self.ENDPOINT, json={}, headers=AUTH_HEADERS)
        assert resp.status_code == 422

    def test_add_without_auth_header_returns_error(self, client):
        resp = client.post(self.ENDPOINT, json={"symbol": "TSLA"})
        assert resp.status_code >= 400


# ══════════════════════════════════════════════════════════════════════
#  Watchlist – Remove symbol
# ══════════════════════════════════════════════════════════════════════

class TestRemoveFromWatchlist:
    def test_remove_existing_symbol_returns_success(self, client, mock_firebase_db):
        existing = _wl_doc(["AAPL", "NVDA", "TSLA"])
        existing.reference.update = MagicMock()
        mock_firebase_db.collection.return_value.document.return_value.get.return_value = existing

        with patch("user_preferences.db", mock_firebase_db):
            resp = client.delete("/api/watchlist/NVDA", headers=AUTH_HEADERS)

        assert resp.status_code in (200, 204)

    def test_remove_non_existing_symbol(self, client, mock_firebase_db):
        existing = _wl_doc(["AAPL"])
        existing.reference.update = MagicMock()
        mock_firebase_db.collection.return_value.document.return_value.get.return_value = existing

        with patch("user_preferences.db", mock_firebase_db):
            resp = client.delete("/api/watchlist/FAKESYM", headers=AUTH_HEADERS)

        # Should not crash — 200, 204, or 404 all acceptable
        assert resp.status_code in (200, 204, 404)

    def test_remove_without_auth_header_returns_error(self, client):
        resp = client.delete("/api/watchlist/AAPL")
        assert resp.status_code >= 400


# ══════════════════════════════════════════════════════════════════════
#  Price Alerts
# ══════════════════════════════════════════════════════════════════════

class TestPriceAlerts:
    LIST_ENDPOINT   = "/api/watchlist/alerts"
    CREATE_ENDPOINT = "/api/watchlist/alerts"

    # ── list ──

    def test_list_alerts_returns_200(self, client, mock_firebase_db):
        alerts = [_alert_doc("AAPL", 200.0, "above"), _alert_doc("TSLA", 150.0, "below")]
        q = MagicMock()
        q.stream.return_value = iter(alerts)
        q.where.return_value = q
        q.order_by.return_value = q
        mock_firebase_db.collection.return_value.where.return_value = q

        with patch("user_preferences.db", mock_firebase_db):
            resp = client.get(self.LIST_ENDPOINT, headers=AUTH_HEADERS)

        assert resp.status_code == 200

    def test_list_alerts_returns_list_type(self, client, mock_firebase_db):
        q = MagicMock()
        q.stream.return_value = iter([])
        q.where.return_value = q
        q.order_by.return_value = q
        mock_firebase_db.collection.return_value.where.return_value = q

        with patch("user_preferences.db", mock_firebase_db):
            resp = client.get(self.LIST_ENDPOINT, headers=AUTH_HEADERS)

        body = resp.json()
        alerts = body if isinstance(body, list) else body.get("alerts", [])
        assert isinstance(alerts, list)

    def test_list_alerts_without_header_returns_error(self, client):
        resp = client.get(self.LIST_ENDPOINT)
        assert resp.status_code >= 400

    # ── create ──

    def test_create_alert_with_valid_data(self, client, mock_firebase_db):
        new_doc = MagicMock()
        new_doc.id = "new-alert-001"
        mock_firebase_db.collection.return_value.document.return_value = new_doc
        new_doc.set = MagicMock()

        with patch("user_preferences.db", mock_firebase_db):
            resp = client.post(
                self.CREATE_ENDPOINT,
                json={
                    "symbol":       "AAPL",
                    "target_price": 210.0,
                    "direction":    "above",
                },
                headers=AUTH_HEADERS,
            )

        assert resp.status_code in (200, 201)

    def test_create_alert_missing_symbol_returns_422(self, client):
        resp = client.post(
            self.CREATE_ENDPOINT,
            json={"target_price": 200.0, "direction": "above"},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 422

    def test_create_alert_missing_target_price_returns_422(self, client):
        resp = client.post(
            self.CREATE_ENDPOINT,
            json={"symbol": "AAPL", "direction": "above"},
            headers=AUTH_HEADERS,
        )
        assert resp.status_code == 422

    def test_create_alert_invalid_direction_returns_error(self, client, mock_firebase_db):
        with patch("user_preferences.db", mock_firebase_db):
            resp = client.post(
                self.CREATE_ENDPOINT,
                json={
                    "symbol":       "AAPL",
                    "target_price": 200.0,
                    "direction":    "sideways",   # invalid direction
                },
                headers=AUTH_HEADERS,
            )

        assert resp.status_code in (400, 422)
