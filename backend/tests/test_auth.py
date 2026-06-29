"""
test_auth.py  -  Tests for /api/auth/* and /api/admin/login endpoints
=======================================================================
Covers:
  - POST /api/auth/register    valid, duplicate, missing fields
  - POST /api/auth/login       success, bad password, unverified, not found
  - POST /api/admin/login      admin success, wrong role, wrong password
"""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime
from passlib.context import CryptContext

# Password hasher — same scheme as auth_routes.py
_pwd = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


# ══════════════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════════════

def _user_doc(
    doc_id="u1",
    email="user@example.com",
    password="UserPass@123",
    role="user",
    verified=True,
):
    doc = MagicMock()
    doc.id = doc_id
    doc.exists = True
    doc.to_dict.return_value = {
        "name":          "Test User",
        "email":         email,
        "password_hash": _pwd.hash(password),
        "role":          role,
        "is_verified":   verified,
        "created_at":    datetime.utcnow(),
    }
    doc.reference = MagicMock()
    return doc


def _no_user():
    """Simulate Firestore returning no documents."""
    q = MagicMock()
    q.stream.return_value = iter([])
    q.get.return_value = []
    q.limit.return_value = q
    q.where.return_value = q
    return q


def _one_user(doc):
    """Simulate Firestore returning exactly one document."""
    q = MagicMock()
    q.stream.return_value = iter([doc])
    q.get.return_value = [doc]
    q.limit.return_value = q
    q.where.return_value = q
    return q


# ══════════════════════════════════════════════════════════════════════
#  Registration
# ══════════════════════════════════════════════════════════════════════

class TestRegister:
    ENDPOINT = "/api/auth/register"
    VALID_PAYLOAD = {
        "name":     "Alice",
        "email":    "alice@example.com",
        "password": "AlicePass@99",
    }

    def test_missing_email_returns_422(self, client):
        resp = client.post(self.ENDPOINT, json={"name": "Bob", "password": "x"})
        assert resp.status_code == 422

    def test_missing_password_returns_422(self, client):
        resp = client.post(self.ENDPOINT, json={"name": "Bob", "email": "b@x.com"})
        assert resp.status_code == 422

    def test_missing_name_returns_422(self, client):
        resp = client.post(self.ENDPOINT, json={"email": "b@x.com", "password": "x"})
        assert resp.status_code == 422

    def test_empty_body_returns_422(self, client):
        resp = client.post(self.ENDPOINT, json={})
        assert resp.status_code == 422

    def test_valid_registration_creates_user(self, client, mock_firebase_db):
        new_doc_ref = MagicMock()
        new_doc_ref.id = "new-user-001"

        mock_firebase_db.collection.return_value.where.return_value = _no_user()
        mock_firebase_db.collection.return_value.document.return_value = new_doc_ref

        with patch("auth_routes.db", mock_firebase_db), \
             patch("auth_routes.send_verification_email", return_value=None):
            resp = client.post(self.ENDPOINT, json=self.VALID_PAYLOAD)

        assert resp.status_code in (200, 201)
        body = resp.json()
        assert "message" in body or "user_id" in body

    def test_duplicate_email_returns_400(self, client, mock_firebase_db):
        existing = _user_doc(email=self.VALID_PAYLOAD["email"])
        mock_firebase_db.collection.return_value.where.return_value = _one_user(existing)

        with patch("auth_routes.db", mock_firebase_db):
            resp = client.post(self.ENDPOINT, json=self.VALID_PAYLOAD)

        assert resp.status_code == 400

    def test_short_password_returns_error(self, client, mock_firebase_db):
        payload = {**self.VALID_PAYLOAD, "password": "short"}
        mock_firebase_db.collection.return_value.where.return_value = _no_user()

        with patch("auth_routes.db", mock_firebase_db):
            resp = client.post(self.ENDPOINT, json=payload)

        # Either 422 (Pydantic validation) or 400 (manual check)
        assert resp.status_code in (400, 422)


# ══════════════════════════════════════════════════════════════════════
#  Regular User Login
# ══════════════════════════════════════════════════════════════════════

class TestLogin:
    ENDPOINT = "/api/auth/login"

    def test_valid_credentials_returns_token(self, client, mock_firebase_db):
        doc = _user_doc(email="user@example.com", password="UserPass@123", verified=True)
        mock_firebase_db.collection.return_value.where.return_value = _one_user(doc)

        with patch("auth_routes.db", mock_firebase_db):
            resp = client.post(self.ENDPOINT, json={
                "email":    "user@example.com",
                "password": "UserPass@123",
            })

        assert resp.status_code == 200
        body = resp.json()
        assert "token" in body or "access_token" in body

    def test_wrong_password_returns_401(self, client, mock_firebase_db):
        doc = _user_doc(email="user@example.com", password="UserPass@123", verified=True)
        mock_firebase_db.collection.return_value.where.return_value = _one_user(doc)

        with patch("auth_routes.db", mock_firebase_db):
            resp = client.post(self.ENDPOINT, json={
                "email":    "user@example.com",
                "password": "WrongPassword!",
            })

        assert resp.status_code == 401

    def test_unknown_email_returns_404_or_401(self, client, mock_firebase_db):
        mock_firebase_db.collection.return_value.where.return_value = _no_user()

        with patch("auth_routes.db", mock_firebase_db):
            resp = client.post(self.ENDPOINT, json={
                "email":    "ghost@example.com",
                "password": "whatever",
            })

        assert resp.status_code in (401, 404)

    def test_unverified_user_is_rejected(self, client, mock_firebase_db):
        doc = _user_doc(email="unverified@x.com", password="Pass@123", verified=False)
        mock_firebase_db.collection.return_value.where.return_value = _one_user(doc)

        with patch("auth_routes.db", mock_firebase_db):
            resp = client.post(self.ENDPOINT, json={
                "email":    "unverified@x.com",
                "password": "Pass@123",
            })

        assert resp.status_code in (401, 403)

    def test_empty_body_returns_422(self, client):
        resp = client.post(self.ENDPOINT, json={})
        assert resp.status_code == 422


# ══════════════════════════════════════════════════════════════════════
#  Admin Login
# ══════════════════════════════════════════════════════════════════════

class TestAdminLogin:
    ENDPOINT = "/api/admin/login"
    ADMIN_EMAIL    = "admin@neurosight.ai"
    ADMIN_PASSWORD = "NeuroAdmin@2026!"

    def test_valid_admin_credentials_succeed(self, client, mock_firebase_db):
        doc = _user_doc(
            email=self.ADMIN_EMAIL,
            password=self.ADMIN_PASSWORD,
            role="admin",
            verified=True,
        )
        mock_firebase_db.collection.return_value.where.return_value = _one_user(doc)

        with patch("auth_routes.db", mock_firebase_db):
            resp = client.post(self.ENDPOINT, json={
                "email":    self.ADMIN_EMAIL,
                "password": self.ADMIN_PASSWORD,
            })

        assert resp.status_code == 200
        body = resp.json()
        # Should get back some kind of auth token or success indicator
        assert "token" in body or "admin" in str(body).lower()

    def test_wrong_admin_password_returns_401(self, client, mock_firebase_db):
        doc = _user_doc(
            email=self.ADMIN_EMAIL,
            password=self.ADMIN_PASSWORD,
            role="admin",
            verified=True,
        )
        mock_firebase_db.collection.return_value.where.return_value = _one_user(doc)

        with patch("auth_routes.db", mock_firebase_db):
            resp = client.post(self.ENDPOINT, json={
                "email":    self.ADMIN_EMAIL,
                "password": "WrongPassword!",
            })

        assert resp.status_code == 401

    def test_non_admin_role_is_rejected(self, client, mock_firebase_db):
        """A regular user should not be able to log in via the admin endpoint."""
        doc = _user_doc(
            email="user@example.com",
            password="UserPass@123",
            role="user",         # <-- not admin
            verified=True,
        )
        mock_firebase_db.collection.return_value.where.return_value = _one_user(doc)

        with patch("auth_routes.db", mock_firebase_db):
            resp = client.post(self.ENDPOINT, json={
                "email":    "user@example.com",
                "password": "UserPass@123",
            })

        assert resp.status_code in (401, 403)

    def test_admin_login_does_not_require_is_verified(self, client, mock_firebase_db):
        """
        Admin login intentionally skips the is_verified check
        (see auth_routes.py admin_login).
        An unverified admin should still be able to log in.
        """
        doc = _user_doc(
            email=self.ADMIN_EMAIL,
            password=self.ADMIN_PASSWORD,
            role="admin",
            verified=False,   # <-- unverified admin
        )
        mock_firebase_db.collection.return_value.where.return_value = _one_user(doc)

        with patch("auth_routes.db", mock_firebase_db):
            resp = client.post(self.ENDPOINT, json={
                "email":    self.ADMIN_EMAIL,
                "password": self.ADMIN_PASSWORD,
            })

        assert resp.status_code == 200

    def test_no_admin_document_returns_error(self, client, mock_firebase_db):
        mock_firebase_db.collection.return_value.where.return_value = _no_user()

        with patch("auth_routes.db", mock_firebase_db):
            resp = client.post(self.ENDPOINT, json={
                "email":    self.ADMIN_EMAIL,
                "password": self.ADMIN_PASSWORD,
            })

        assert resp.status_code in (401, 404)
