import firebase_admin
from firebase_admin import credentials, firestore
import os

# Initialize Firebase if not already done
if not firebase_admin._apps:
    cred_path = os.path.join(os.path.dirname(__file__), 'firebase-service-account.json')
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)

db = firestore.client()

print("🗑️ Clearing old price cache...")

# Delete all cached prices
cached_prices = db.collection('cached_prices').stream()
count = 0
for doc in cached_prices:
    doc.reference.delete()
    count += 1
    print(f"  Deleted: {doc.id}")

print(f"\n✅ Cleared {count} cached price entries")
print("Cache will be rebuilt with correct market_cap data on next API call")
