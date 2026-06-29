"""
create_admin.py  -  NeuroSight Admin Account Creator
=====================================================
Run this script ONCE to create a working admin account in Firestore.

USAGE
-----
  python create_admin.py

The script will:
  1. Prompt for email and password (or use the hardcoded defaults below)
  2. Hash the password with pbkdf2_sha256  (same scheme used by auth_routes.py)
  3. Write a document to Firestore  users  collection with:
       email, password_hash, role="admin", is_verified=True, name, created_at
  4. Print the document ID so you can verify it in the Firebase console.

BEFORE RUNNING
--------------
  1. Open Firebase console  →  Firestore  →  users  collection
  2. Delete any existing document where  role == "admin"  (old broken entry)
  3. Run:   python create_admin.py
  4. When prompted, press ENTER to accept the recommended credentials below,
     OR type your own email / password.

RECOMMENDED CREDENTIALS (change after first login!)
-----------------------------------------------------
  Email    :  admin@neurosight.ai
  Password :  NeuroAdmin@2026!

These are the credentials you enter in the admin login page at:
  http://127.0.0.1:8000/admin_login.html
"""

import os
import sys
from pathlib import Path
from datetime import datetime

# ── ensure we can import Firebase even when run from outside backend/ ──
THIS_DIR = Path(__file__).resolve().parent
os.chdir(THIS_DIR)
sys.path.insert(0, str(THIS_DIR))

# ── password hashing (must match auth_routes.py exactly) ──────────────
from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

# ── Firebase init ──────────────────────────────────────────────────────
import firebase_admin
from firebase_admin import credentials, firestore

if not firebase_admin._apps:
    cred_path = THIS_DIR / "firebase-service-account.json"
    if not cred_path.exists():
        print(f"ERROR: Firebase service account not found at {cred_path}")
        sys.exit(1)
    firebase_admin.initialize_app(credentials.Certificate(str(cred_path)))

db = firestore.client()

# ══════════════════════════════════════════════════════════════════════
#  RECOMMENDED DEFAULT CREDENTIALS
#  Change these before deploying to production.
# ══════════════════════════════════════════════════════════════════════
DEFAULT_EMAIL    = "admin@neurosight.ai"
DEFAULT_PASSWORD = "NeuroAdmin@2026!"
DEFAULT_NAME     = "NeuroSight Admin"


def _prompt(label: str, default: str, secret: bool = False) -> str:
    """Prompt user for input, using *default* if they press ENTER."""
    if secret:
        import getpass
        val = getpass.getpass(f"{label} [leave blank = use default]: ").strip()
    else:
        val = input(f"{label} [default: {default}]: ").strip()
    return val if val else default


def _email_is_unique(email: str) -> bool:
    """Return True if no document with this email already exists in users."""
    docs = (
        db.collection("users")
        .where(filter=firestore.FieldFilter("email", "==", email))
        .limit(1)
        .get()
    )
    return len(docs) == 0


def main():
    print()
    print("=" * 55)
    print("  NeuroSight — Admin Account Creator")
    print("=" * 55)
    print()
    print("Press ENTER to use the recommended defaults,")
    print("or type new values and press ENTER.")
    print()

    email    = _prompt("Admin email   ", DEFAULT_EMAIL)
    name     = _prompt("Display name  ", DEFAULT_NAME)
    password = _prompt("Password      ", DEFAULT_PASSWORD, secret=True)

    # Validate
    if len(password) < 8:
        print("ERROR: Password must be at least 8 characters.")
        sys.exit(1)

    email = email.strip().lower()

    # Check uniqueness
    if not _email_is_unique(email):
        print()
        print(f"WARNING: A user with email '{email}' already exists in Firestore.")
        overwrite = input("Delete the old entry and recreate? [y/N]: ").strip().lower()
        if overwrite != "y":
            print("Aborted. Delete the old admin manually in the Firebase console first.")
            sys.exit(0)
        # Delete existing document(s) with this email
        docs = (
            db.collection("users")
            .where(filter=firestore.FieldFilter("email", "==", email))
            .get()
        )
        for doc in docs:
            doc.reference.delete()
            print(f"  Deleted old document: {doc.id}")

    # Hash the password exactly as auth_routes.py does
    hashed = pwd_context.hash(password)

    # Write the admin document
    doc_ref = db.collection("users").document()
    doc_ref.set({
        "name":          name,
        "email":         email,
        "password_hash": hashed,
        "role":          "admin",
        "is_verified":   True,
        "created_at":    datetime.utcnow(),
    })

    print()
    print("=" * 55)
    print("  Admin account created successfully!")
    print("=" * 55)
    print(f"  Firestore document ID : {doc_ref.id}")
    print(f"  Email                 : {email}")
    print(f"  Password              : {password}")
    print(f"  Role                  : admin")
    print()
    print("  Login at:  http://127.0.0.1:8000/admin_login.html")
    print()
    print("  IMPORTANT: Change your password after first login!")
    print()


if __name__ == "__main__":
    main()
