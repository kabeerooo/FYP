import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from dotenv import load_dotenv
load_dotenv()

import auth_routes
from firebase_admin import firestore

db = auth_routes.db
pwd_context = auth_routes.pwd_context

users_ref = db.collection("users")
query = users_ref.where(filter=firestore.FieldFilter("role", "==", "admin")).limit(1)
docs = query.get()

doc = docs[0]
user = doc.to_dict()
stored_hash = user.get("password_hash", "")

print(f"Email: {user.get('email')}")
print(f"Hash (first 50): {stored_hash[:50]}")
print(f"Hash scheme: {'pbkdf2' if 'pbkdf2' in stored_hash else 'bcrypt' if 'bcrypt' in stored_hash else 'unknown'}")
print()

# Test the password we just set
pw = "NeuroAdmin@2026"
try:
    result = pwd_context.verify(pw, stored_hash)
    print(f"verify('{pw}') = {result}")
except Exception as e:
    print(f"verify ERROR: {e}")

# Also show what a fresh hash of this password looks like
new_hash = pwd_context.hash(pw)
print(f"\nFresh hash: {new_hash[:50]}")
print(f"Fresh verify: {pwd_context.verify(pw, new_hash)}")

# Force update with fresh hash
print(f"\nForce-updating hash in Firestore...")
doc.reference.update({"password_hash": new_hash})
print("Done. Re-reading to confirm...")
doc2 = users_ref.document(doc.id).get()
saved = doc2.to_dict().get("password_hash", "")
print(f"Saved hash (first 50): {saved[:50]}")
print(f"Verify after save: {pwd_context.verify(pw, saved)}")
