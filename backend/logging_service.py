# logging_service.py - Comprehensive system logging service

from datetime import datetime
from firebase_admin import firestore
import auth_routes

db = auth_routes.db

class LogType:
    """Log type constants"""
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    SECURITY = "security"

class LogCategory:
    """Log category constants"""
    AUTH = "authentication"
    USER = "user_management"
    ADMIN = "admin_action"
    SYSTEM = "system"
    CHAT = "chat_interaction"
    PREDICTION = "prediction"
    ERROR = "error"

def log_event(
    category: str,
    message: str,
    log_type: str = LogType.INFO,
    user_id: str = None,
    details: dict = None
):
    """
    Log an event to Firestore system_logs collection
    
    Args:
        category: Event category (auth, user, admin, system, chat, prediction, error)
        message: Human-readable log message
        log_type: Type of log (info, success, warning, error, security)
        user_id: Optional user ID associated with the event
        details: Optional additional details as dict
    """
    try:
        log_data = {
            "category": category,
            "message": message,
            "type": log_type,
            "timestamp": datetime.utcnow().isoformat(),
            "user_id": user_id,
            "details": details or {}
        }
        
        db.collection('system_logs').add(log_data)
        
    except Exception as e:
        # If logging fails, print to console but don't crash the app
        print(f"Failed to log event: {e}")

# Convenience functions for common log types

def log_login(user_id: str, email: str, success: bool = True):
    """Log user login attempt"""
    if success:
        log_event(
            LogCategory.AUTH,
            f"User logged in: {email}",
            LogType.SUCCESS,
            user_id=user_id,
            details={"email": email, "action": "login"}
        )
    else:
        log_event(
            LogCategory.AUTH,
            f"Failed login attempt: {email}",
            LogType.WARNING,
            details={"email": email, "action": "login_failed"}
        )

def log_logout(user_id: str, email: str):
    """Log user logout"""
    log_event(
        LogCategory.AUTH,
        f"User logged out: {email}",
        LogType.INFO,
        user_id=user_id,
        details={"email": email, "action": "logout"}
    )

def log_registration(user_id: str, email: str, name: str):
    """Log new user registration"""
    log_event(
        LogCategory.USER,
        f"New user registered: {name} ({email})",
        LogType.SUCCESS,
        user_id=user_id,
        details={"email": email, "name": name, "action": "registration"}
    )

def log_admin_action(admin_id: str, action: str, details: dict = None):
    """Log admin action"""
    log_event(
        LogCategory.ADMIN,
        f"Admin action: {action}",
        LogType.INFO,
        user_id=admin_id,
        details={"action": action, **(details or {})}
    )

def log_chat_interaction(user_id: str, query: str, response_type: str = "general"):
    """Log chat interaction"""
    log_event(
        LogCategory.CHAT,
        f"Chat interaction by user {user_id}",
        LogType.INFO,
        user_id=user_id,
        details={"query_preview": query[:50], "response_type": response_type}
    )

def log_prediction_request(user_id: str, asset: str):
    """Log asset prediction request"""
    log_event(
        LogCategory.PREDICTION,
        f"Prediction requested for {asset}",
        LogType.INFO,
        user_id=user_id,
        details={"asset": asset, "action": "prediction_request"}
    )

def log_system_event(message: str, event_type: str = LogType.INFO, details: dict = None):
    """Log system event"""
    log_event(
        LogCategory.SYSTEM,
        message,
        event_type,
        details=details
    )

def log_error(message: str, error_details: str = None, user_id: str = None):
    """Log error event"""
    log_event(
        LogCategory.ERROR,
        message,
        LogType.ERROR,
        user_id=user_id,
        details={"error": error_details} if error_details else None
    )
