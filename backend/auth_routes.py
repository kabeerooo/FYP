# auth_routes.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from datetime import datetime
from passlib.context import CryptContext
import firebase_admin
from firebase_admin import credentials, firestore
import os
import re  # ✅ ADDED FOR EMAIL VALIDATION
import threading

# Initialize Firebase (only once)
if not firebase_admin._apps:
    import json
    _fb_json = os.getenv("FIREBASE_SERVICE_ACCOUNT")
    if _fb_json:
        # Production: credentials supplied as JSON env var
        cred = credentials.Certificate(json.loads(_fb_json))
    else:
        # Local dev: read from file
        cred_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "firebase-service-account.json"))
        cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)

db = firestore.client()
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

# Import logging service
try:
    from logging_service import log_registration, log_login, log_error
except ImportError:
    # Fallback if logging service not available
    def log_registration(*args, **kwargs): pass
    def log_login(*args, **kwargs): pass
    def log_error(*args, **kwargs): pass

# Import email service
try:
    from email_service import (
        generate_verification_code,
        send_verification_email,
        send_welcome_email,
        store_verification_code,
        verify_code,
        send_password_reset_email,
        store_password_reset_code,
        verify_password_reset_code
    )
    EMAIL_SERVICE_AVAILABLE = True
except ImportError:
    print("⚠️ Email service not available")
    EMAIL_SERVICE_AVAILABLE = False

class RegisterRequest(BaseModel):
    name: str = Field(..., min_length=1)
    email: str = Field(..., min_length=5)
    password: str = Field(..., min_length=8)

class LoginRequest(BaseModel):
    email: str = Field(..., min_length=5)
    password: str = Field(..., min_length=1)

class VerifyEmailRequest(BaseModel):
    email: str = Field(..., min_length=5)
    code: str = Field(..., min_length=6, max_length=6)

class ResendCodeRequest(BaseModel):
    email: str = Field(..., min_length=5)

class ForgotPasswordRequest(BaseModel):
    email: str = Field(..., min_length=5)

class ResetPasswordRequest(BaseModel):
    email: str = Field(..., min_length=5)
    code: str = Field(..., min_length=6, max_length=6)
    new_password: str = Field(..., min_length=8)

router = APIRouter()

# ✅ STRICT EMAIL VALIDATION PATTERN
EMAIL_REGEX = r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$"

def validate_strong_password(password: str) -> tuple[bool, str]:
    """Validate password meets security requirements"""
    if len(password) < 8:
        return False, "Password must be at least 8 characters"
    if not re.search(r"[A-Z]", password):
        return False, "Password must contain at least one uppercase letter"
    if not re.search(r"[a-z]", password):
        return False, "Password must contain at least one lowercase letter"
    if not re.search(r"\d", password):
        return False, "Password must contain at least one number"
    if not re.search(r"[^A-Za-z0-9]", password):
        return False, "Password must contain at least one special character"
    return True, ""

@router.post("/register")
def register_user(data: RegisterRequest):
    clean_name = data.name.strip()
    clean_email = data.email.strip().lower()
    
    if not clean_name or len(clean_name) < 2:
        raise HTTPException(400, "Name must be at least 2 characters")

    # ✅ VALIDATE EMAIL FORMAT
    if not re.fullmatch(EMAIL_REGEX, clean_email):
        raise HTTPException(400, "Invalid email address format")
    
    # ✅ VALIDATE STRONG PASSWORD
    is_valid, error_msg = validate_strong_password(data.password)
    if not is_valid:
        raise HTTPException(400, error_msg)

    users_ref = db.collection("users")
    existing = users_ref.where(filter=firestore.FieldFilter("email", "==", clean_email)).limit(1).get()
    
    if len(existing) > 0:
        user_data = existing[0].to_dict()
        if user_data.get("is_verified", False):
            raise HTTPException(400, "Email already registered")
        # User exists but not verified - delete old verification code
        else:
            print(f"⚠️ User {clean_email} exists but not verified. Deleting old user and code...")
            user_id = existing[0].id
            # Delete old user
            existing[0].reference.delete()
            # Delete old verification code (legacy user_id doc + current email doc)
            try:
                db.collection("verification_codes").document(user_id).delete()
                db.collection("verification_codes").document(clean_email).delete()
                print(f"🗑️ Deleted old verification codes for {user_id}/{clean_email}")
            except Exception as e:
                print(f"⚠️ No old verification code to delete: {e}")

    doc_ref = users_ref.document()
    doc_ref.set({
        "name": clean_name,
        "email": clean_email,
        "password_hash": pwd_context.hash(data.password),
        "role": "user",
        "created_at": datetime.utcnow(),
        # Auto-verify immediately when email service is unavailable (local dev)
        "is_verified": not EMAIL_SERVICE_AVAILABLE,
    })

    # Generate and send verification code
    if EMAIL_SERVICE_AVAILABLE:
        code = generate_verification_code()
        print(f"🎯 Using code {code} for both storage and email")
        store_verification_code(doc_ref.id, clean_email, code)
        threading.Thread(
            target=send_verification_email,
            args=(clean_email, clean_name, code),
            daemon=True
        ).start()

    # Log registration
    log_registration(doc_ref.id, clean_email, clean_name)

    msg = (
        "Registration successful! Please check your email to verify your account."
        if EMAIL_SERVICE_AVAILABLE
        else "Registration successful! You can now log in."
    )
    return {
        "message": msg,
        "email": clean_email,
        "user_id": doc_ref.id,
        "requires_verification": EMAIL_SERVICE_AVAILABLE,
    }

@router.post("/login")
def login_user(data: LoginRequest):
    clean_email = data.email.strip().lower()
    
    users_ref = db.collection("users")
    query = users_ref.where(filter=firestore.FieldFilter("email", "==", clean_email)).limit(1)
    existing = query.get()
    
    if len(existing) == 0:
        raise HTTPException(401, "Invalid email or password")
    
    user_doc = existing[0]
    user = user_doc.to_dict()
    
    if not user.get("is_verified", False):
        raise HTTPException(403, "Please verify your email before logging in")

    if not pwd_context.verify(data.password, user["password_hash"]):
        log_login(None, clean_email, success=False)
        raise HTTPException(401, "Invalid email or password")
    
    # Log successful login
    log_login(user_doc.id, clean_email, success=True)

    return {
        "success": True,
        "user_id": user_doc.id,
        "email": user["email"],
        "name": user["name"],
        "role": user.get("role", "user")
    }

@router.post("/admin/login")
def admin_login(data: LoginRequest):
    clean_email = data.email.strip().lower()
    
    users_ref = db.collection("users")
    query = users_ref.where(filter=firestore.FieldFilter("email", "==", clean_email)).limit(1)
    existing = query.get()
    
    if len(existing) == 0:
        raise HTTPException(401, "Invalid admin credentials")
    
    user_doc = existing[0]
    user = user_doc.to_dict()
    
    # Check if user is admin
    if user.get("role") != "admin":
        raise HTTPException(403, "Access denied. Admin privileges required.")
    
    if not pwd_context.verify(data.password, user["password_hash"]):
        log_login(None, clean_email, success=False)
        raise HTTPException(401, "Invalid admin credentials")
    
    # Log admin login
    log_login(user_doc.id, clean_email, success=True)

    return {
        "success": True,
        "user_id": user_doc.id,
        "email": user["email"],
        "name": user["name"],
        "role": "admin"
    }

@router.post("/verify-email")
def verify_email(data: VerifyEmailRequest):
    """Verify email with 6-digit code"""
    clean_email = data.email.strip().lower()
    code = data.code.strip()
    
    if not EMAIL_SERVICE_AVAILABLE:
        raise HTTPException(500, "Email verification service unavailable")
    
    result = verify_code(clean_email, code)
    
    if not result["success"]:
        raise HTTPException(400, result["message"])
    
    try:
        users_ref = db.collection("users")
        query = users_ref.where(filter=firestore.FieldFilter("email", "==", clean_email)).limit(1)
        docs = query.get()
        
        if not docs:
            raise HTTPException(404, "User not found")
        
        user_doc = docs[0]
        user_data = user_doc.to_dict()
        
        user_doc.reference.update({
            "is_verified": True,
            "verified_at": datetime.utcnow()
        })
        
        send_welcome_email(clean_email, user_data["name"])
        
        return {
            "success": True,
            "message": "Email verified successfully! You can now login.",
            "user_id": user_doc.id,
            "email": clean_email,
            "name": user_data["name"]
        }
        
    except Exception as e:
        raise HTTPException(500, "Verification failed. Please try again.")

@router.post("/resend-verification")
def resend_verification(data: ResendCodeRequest):
    """Resend verification code"""
    clean_email = data.email.strip().lower()
    
    if not EMAIL_SERVICE_AVAILABLE:
        raise HTTPException(500, "Email service unavailable")
    
    try:
        users_ref = db.collection("users")
        query = users_ref.where(filter=firestore.FieldFilter("email", "==", clean_email)).limit(1)
        docs = query.get()
        
        if not docs:
            raise HTTPException(404, "User not found")
        
        user_doc = docs[0]
        user_data = user_doc.to_dict()
        
        if user_data.get("is_verified", False):
            raise HTTPException(400, "Email already verified. You can login now.")
        
        code = generate_verification_code()
        store_verification_code(user_doc.id, clean_email, code)
        # ✅ PERF FIX: fire email in background
        threading.Thread(
            target=send_verification_email,
            args=(clean_email, user_data["name"], code),
            daemon=True
        ).start()
        
        return {
            "success": True,
            "message": "New verification code sent to your email"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(500, "Failed to resend code. Please try again.")

@router.post("/forgot-password")
def forgot_password(data: ForgotPasswordRequest):
    """Send password reset code"""
    clean_email = data.email.strip().lower()
    
    if not EMAIL_SERVICE_AVAILABLE:
        raise HTTPException(500, "Email service unavailable")
    
    try:
        users_ref = db.collection("users")
        query = users_ref.where(filter=firestore.FieldFilter("email", "==", clean_email)).limit(1)
        docs = query.get()
        
        if not docs:
            # Don't reveal if user exists for security
            return {
                "success": True,
                "message": "If that email is registered, you'll receive a password reset code shortly."
            }
        
        user_doc = docs[0]
        user_data = user_doc.to_dict()
        
        # Generate and send reset code
        reset_code = generate_verification_code()
        store_password_reset_code(clean_email, reset_code)
        send_password_reset_email(clean_email, user_data["name"], reset_code)
        
        return {
            "success": True,
            "message": "Password reset code sent to your email"
        }
        
    except Exception as e:
        print(f"❌ Forgot password error: {str(e)}")
        # Generic message for security
        return {
            "success": True,
            "message": "If that email is registered, you'll receive a password reset code shortly."
        }

@router.post("/reset-password")
def reset_password(data: ResetPasswordRequest):
    """Reset password with code"""
    clean_email = data.email.strip().lower()
    
    if not EMAIL_SERVICE_AVAILABLE:
        raise HTTPException(500, "Email service unavailable")
    
    # Validate strong password
    is_valid, error_msg = validate_strong_password(data.new_password)
    if not is_valid:
        raise HTTPException(400, error_msg)
    
    try:
        # Verify reset code
        result = verify_password_reset_code(clean_email, data.code)
        if not result["success"]:
            raise HTTPException(400, result["message"])
        
        # Update password
        users_ref = db.collection("users")
        query = users_ref.where(filter=firestore.FieldFilter("email", "==", clean_email)).limit(1)
        docs = query.get()
        
        if not docs:
            raise HTTPException(404, "User not found")
        
        user_doc = docs[0]
        user_doc.reference.update({
            "password_hash": pwd_context.hash(data.new_password),
            "password_updated_at": datetime.utcnow()
        })
        
        # Mark reset code as used
        db.collection("password_resets").document(clean_email).update({"used": True})
        
        print(f"✅ Password reset successful for {clean_email}")
        
        return {
            "success": True,
            "message": "Password reset successful! You can now login with your new password."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Reset password error: {str(e)}")
        raise HTTPException(500, "Password reset failed. Please try again.")