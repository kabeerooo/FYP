# profile_routes.py

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from datetime import datetime
from passlib.context import CryptContext
import firebase_admin
from firebase_admin import firestore
import re

# Get Firestore client
db = firestore.client()
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

# Import logging service
try:
    from logging_service import log_error
except ImportError:
    def log_error(*args, **kwargs): pass

# Email validation pattern
EMAIL_REGEX = r"^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$"

router = APIRouter()

# Profile update request models
class UpdateProfileRequest(BaseModel):
    user_id: str
    name: str
    email: str
    phone: str | None = None
    bio: str | None = None
    experience: str | None = None

class ChangePasswordRequest(BaseModel):
    user_id: str
    email: str
    current_password: str
    new_password: str

@router.post("/user/update-profile")
def update_user_profile(data: UpdateProfileRequest):
    """Update user profile information"""
    try:
        users_ref = db.collection("users")
        user_doc = users_ref.document(data.user_id).get()
        
        if not user_doc.exists:
            raise HTTPException(404, "User not found")
        
        user_data = user_doc.to_dict()
        
        # Verify email matches or check if new email already exists
        if user_data.get("email").lower() != data.email.lower():
            # Email is being changed, check if new email already exists
            from firebase_admin import firestore
            existing = users_ref.where(filter=firestore.FieldFilter("email", "==", data.email.lower())).limit(1).get()
            if len(existing) > 0 and existing[0].id != data.user_id:
                raise HTTPException(400, "Email already in use by another account")
        
        # Validate email format
        if not re.fullmatch(EMAIL_REGEX, data.email.lower()):
            raise HTTPException(400, "Invalid email address format")
        
        # Prepare update data
        update_data = {
            "name": data.name.strip(),
            "email": data.email.strip().lower(),
            "updated_at": datetime.utcnow()
        }
        
        # Add optional fields if provided
        if data.phone:
            update_data["phone"] = data.phone.strip()
        
        if data.bio:
            update_data["bio"] = data.bio.strip()
        
        if data.experience:
            update_data["experience"] = data.experience
        
        # Update user document
        users_ref.document(data.user_id).update(update_data)
        
        print(f"✅ Profile updated for user {data.user_id}")
        
        return {
            "success": True,
            "message": "Profile updated successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Profile update error: {str(e)}")
        log_error("profile_update", str(e), data.user_id)
        raise HTTPException(500, f"Failed to update profile: {str(e)}")

@router.post("/user/change-password")
def change_user_password(data: ChangePasswordRequest):
    """Change user password"""
    try:
        users_ref = db.collection("users")
        user_doc = users_ref.document(data.user_id).get()
        
        if not user_doc.exists:
            raise HTTPException(404, "User not found")
        
        user_data = user_doc.to_dict()
        
        # Verify email matches
        if user_data.get("email").lower() != data.email.lower():
            raise HTTPException(403, "Email verification failed")
        
        # Verify current password
        if not pwd_context.verify(data.current_password, user_data["password_hash"]):
            raise HTTPException(401, "Current password is incorrect")
        
        # Validate new password strength
        if len(data.new_password) < 8:
            raise HTTPException(400, "New password must be at least 8 characters")
        
        if not re.search(r'[A-Z]', data.new_password):
            raise HTTPException(400, "New password must contain at least one uppercase letter")
        
        if not re.search(r'[a-z]', data.new_password):
            raise HTTPException(400, "New password must contain at least one lowercase letter")
        
        if not re.search(r'[0-9]', data.new_password):
            raise HTTPException(400, "New password must contain at least one number")
        
        # Hash new password and update
        new_password_hash = pwd_context.hash(data.new_password)
        
        users_ref.document(data.user_id).update({
            "password_hash": new_password_hash,
            "password_updated_at": datetime.utcnow()
        })
        
        print(f"✅ Password changed for user {data.user_id}")
        
        return {
            "success": True,
            "message": "Password changed successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Password change error: {str(e)}")
        log_error("password_change", str(e), data.user_id)
        raise HTTPException(500, f"Failed to change password: {str(e)}")
