"""
Admin Password Reset Utility
Run: python reset_admin_password.py
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

import firebase_admin
from firebase_admin import credentials, firestore
from passlib.context import CryptContext

# ── Init Firebase ─────────────────────────────────────────────────────────────
cred_path = os.path.join(os.path.dirname(__file__), "firebase-service-account.json")
if not firebase_admin._apps:
    firebase_admin.initialize_app(credentials.Certificate(cred_path))

db  = firestore.client()
pwd = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

# ── Find all admin users ──────────────────────────────────────────────────────
print("\n🔍 Searching for admin accounts in Firebase...\n")
admins = db.collection("users").where("role", "==", "admin").get()

if not admins:
    print("❌  No admin user found in Firestore.")
    print("    Make sure a user document has  role = 'admin'  in the 'users' collection.")
    sys.exit(1)

for doc in admins:
    u = doc.to_dict()
    print(f"  ✅  Found admin: {u.get('email')}  (doc id: {doc.id})")

# ── Pick which admin to reset ────────────────────────────────────────────────
if len(admins) == 1:
    target = admins[0]
else:
    email_input = input("\nMultiple admins found. Enter the email to reset: ").strip().lower()
    target = next((d for d in admins if d.to_dict().get("email") == email_input), None)
    if not target:
        print("❌  Email not found among admins.")
        sys.exit(1)

admin_email = target.to_dict().get("email")
print(f"\n🔐  Resetting password for: {admin_email}")

# ── New password input ────────────────────────────────────────────────────────
while True:
    new_pass = input("   Enter new password (min 8 chars): ")
    confirm  = input("   Confirm new password             : ")
    if new_pass != confirm:
        print("   ❌  Passwords don't match. Try again.\n")
        continue
    if len(new_pass) < 8:
        print("   ❌  Password must be at least 8 characters.\n")
        continue
    break

# ── Hash and save ─────────────────────────────────────────────────────────────
new_hash = pwd.hash(new_pass)
target.reference.update({"password_hash": new_hash})

print(f"\n✅  Password successfully reset for  {admin_email}")
print("    You can now log in at  /admin_login.html  with the new password.\n")
