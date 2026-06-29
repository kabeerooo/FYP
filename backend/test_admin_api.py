"""
Quick test of admin login API endpoint
"""
import requests
import json

print("\n" + "="*70)
print("🧪 TESTING ADMIN LOGIN API")
print("="*70 + "\n")

# Test data
url = "http://127.0.0.1:8000/api/admin/login"
admin_email = "admin@neurosight.ai"
admin_password = "NeuroAdmin@2026!"

print(f"📍 Endpoint: {url}")
print(f"📧 Email: {admin_email}")
print(f"🔑 Password: {'*' * len(admin_password)}")
print()

try:
    # Make the API request
    print("🔄 Sending POST request...")
    response = requests.post(
        url,
        json={
            "email": admin_email,
            "password": admin_password
        },
        headers={"Content-Type": "application/json"},
        timeout=5
    )
    
    print(f"📥 Response Status: {response.status_code}")
    print()
    
    # Parse response
    try:
        data = response.json()
        print("📄 Response Body:")
        print(json.dumps(data, indent=2))
    except:
        print("📄 Response Body (raw):")
        print(response.text)
    
    print()
    
    # Evaluate result
    if response.status_code == 200:
        print("✅ SUCCESS! Admin login is working correctly.")
        print()
        print("You can now log in with:")
        print(f"   Email: {admin_email}")
        print(f"   Password: {admin_password}")
        print()
    elif response.status_code == 401:
        print("❌ AUTHENTICATION FAILED!")
        print("   The credentials are incorrect.")
        print()
    elif response.status_code == 403:
        print("❌ ACCESS DENIED!")
        print("   The user exists but doesn't have admin role.")
        print()
    else:
        print(f"⚠️  Unexpected status code: {response.status_code}")
        print()
        
except requests.exceptions.ConnectionError:
    print("❌ CONNECTION ERROR!")
    print("   The backend server is not running on port 8000.")
    print()
    print("   Start the server with:")
    print("   cd d:\\Neuro\\backend")
    print("   python main.py")
    print()
except requests.exceptions.Timeout:
    print("❌ TIMEOUT ERROR!")
    print("   The server took too long to respond.")
    print()
except Exception as e:
    print(f"❌ ERROR: {type(e).__name__}")
    print(f"   {str(e)}")
    print()

print("="*70 + "\n")
