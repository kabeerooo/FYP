"""
Test Admin Login - Debug Script
Checks admin user exists and tests password verification
"""
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import firebase_admin
from firebase_admin import credentials, firestore
from passlib.context import CryptContext

# Initialize Firebase
cred_path = os.path.join(os.path.dirname(__file__), "firebase-service-account.json")
if not firebase_admin._apps:
    firebase_admin.initialize_app(credentials.Certificate(cred_path))

db = firestore.client()
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

print("\n" + "="*70)
print("🔍 ADMIN LOGIN DIAGNOSTIC TEST")
print("="*70 + "\n")

# Search for admin users
print("1️⃣  Searching for admin users in Firebase...")
admins = db.collection("users").where("role", "==", "admin").get()

if not admins:
    print("❌ NO ADMIN USERS FOUND!\n")
    print("Creating admin user: admin@neurosight.ai")
    
    # Create admin user
    admin_password = "NeuroAdmin@2026!"
    admin_hash = pwd_context.hash(admin_password)
    
    db.collection("users").add({
        "email": "admin@neurosight.ai",
        "name": "Admin",
        "password_hash": admin_hash,
        "role": "admin",
        "is_verified": True,
        "created_at": firestore.SERVER_TIMESTAMP
    })
    
    print(f"✅ Admin user created with password: {admin_password}\n")
    sys.exit(0)

# Display all admin users
print(f"✅ Found {len(admins)} admin user(s):\n")
for doc in admins:
    user = doc.to_dict()
    print(f"   📧 Email: {user.get('email')}")
    print(f"   👤 Name: {user.get('name')}")
    print(f"   🆔 Doc ID: {doc.id}")
    print(f"   🔑 Hash prefix: {user.get('password_hash', '')[:60]}...")
    print()

# Test password verification for first admin
target_admin = admins[0]
admin_data = target_admin.to_dict()
admin_email = admin_data.get('email')
stored_hash = admin_data.get('password_hash', '')

print("2️⃣  Testing password verification...")
print(f"   Testing for: {admin_email}\n")

# Test common admin passwords
test_passwords = [
    "NeuroAdmin@2026!",
    "NeuroAdmin@2026",
    "admin123",
    "Admin@123"
]

for test_pw in test_passwords:
    try:
        result = pwd_context.verify(test_pw, stored_hash)
        status = "✅ MATCH" if result else "❌ NO MATCH"
        print(f"   {status}  Password: '{test_pw}'")
        
        if result:
            print(f"\n🎉 SUCCESS! Working password is: '{test_pw}'")
            print(f"\n   Use these credentials:")
            print(f"   Email: {admin_email}")
            print(f"   Password: {test_pw}\n")
            sys.exit(0)
            
    except Exception as e:
        print(f"   ❌ ERROR   Password: '{test_pw}' - {str(e)}")

# If we got here, none of the passwords worked
print("\n❌ NONE OF THE TEST PASSWORDS WORKED!\n")
print("3️⃣  Creating new admin with known password...")

new_password = "NeuroAdmin@2026!"
new_hash = pwd_context.hash(new_password)

target_admin.reference.update({
    "password_hash": new_hash
})

print(f"✅ Password reset successfully!")
print(f"\n   Use these credentials:")
print(f"   Email: {admin_email}")
print(f"   Password: {new_password}\n")

# Verify the update worked
print("4️⃣  Verifying update...")
updated_doc = db.collection("users").document(target_admin.id).get()
updated_hash = updated_doc.to_dict().get('password_hash', '')
verify_result = pwd_context.verify(new_password, updated_hash)

if verify_result:
    print(f"✅ VERIFICATION SUCCESSFUL! Admin login is now working.\n")
else:
    print(f"❌ VERIFICATION FAILED! Something went wrong.\n")

print("="*70 + "\n")
