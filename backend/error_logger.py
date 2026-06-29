"""
Error Logging and Monitoring System
Comprehensive error tracking, categorization, and alert system
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional
from enum import Enum
from auth_routes import db
import traceback
import sys

class ErrorSeverity(Enum):
    """Error severity levels"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class ErrorCategory(Enum):
    """Error categories"""
    AUTHENTICATION = "authentication"
    DATABASE = "database"
    API = "api"
    PREDICTION = "prediction"
    CHAT = "chat"
    SYSTEM = "system"
    NETWORK = "network"
    VALIDATION = "validation"

class ErrorLogger:
    """Comprehensive error logging system"""
    
    def __init__(self):
        self.error_thresholds = {
            ErrorSeverity.CRITICAL: 1,  # Alert immediately
            ErrorSeverity.HIGH: 5,      # Alert after 5 occurrences
            ErrorSeverity.MEDIUM: 20,   # Alert after 20 occurrences
            ErrorSeverity.LOW: 100      # Alert after 100 occurrences
        }
    
    def log_error(
        self,
        error: Exception,
        category: ErrorCategory,
        severity: ErrorSeverity,
        user_id: Optional[str] = None,
        context: Dict = None
    ) -> str:
        """Log an error with full context"""
        try:
            error_id = f"ERR_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{id(error)}"
            
            # Extract traceback
            tb_lines = traceback.format_exception(type(error), error, error.__traceback__)
            traceback_str = ''.join(tb_lines)
            
            error_data = {
                'error_id': error_id,
                'timestamp': datetime.now().isoformat(),
                'error_type': type(error).__name__,
                'error_message': str(error),
                'traceback': traceback_str,
                'category': category.value,
                'severity': severity.value,
                'user_id': user_id,
                'context': context or {},
                'resolved': False,
                'resolution_notes': None,
                'occurrences': 1
            }
            
            # Store in Firestore
            error_ref = db.collection('error_logs').document(error_id)
            error_ref.set(error_data)
            
            # Check if alert needed
            self._check_alert_threshold(category, severity)
            
            print(f"❌ Error logged: {error_id} - {category.value} - {severity.value}")
            
            return error_id
            
        except Exception as e:
            print(f"Failed to log error: {e}")
            return None
    
    def log_simple_error(
        self,
        message: str,
        category: str = "system",
        severity: str = "medium",
        user_id: Optional[str] = None,
        details: Dict = None
    ):
        """Log error without exception object"""
        try:
            error_id = f"ERR_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            error_data = {
                'error_id': error_id,
                'timestamp': datetime.now().isoformat(),
                'error_message': message,
                'category': category,
                'severity': severity,
                'user_id': user_id,
                'details': details or {},
                'resolved': False
            }
            
            db.collection('error_logs').document(error_id).set(error_data)
            
            return error_id
        except Exception as e:
            print(f"Failed to log simple error: {e}")
            return None
    
    def get_error_dashboard_data(self, hours: int = 24) -> Dict:
        """Get comprehensive error analytics"""
        try:
            cutoff = datetime.now() - timedelta(hours=hours)
            
            errors_ref = db.collection('error_logs')
            query = errors_ref.where('timestamp', '>=', cutoff.isoformat())
            errors = query.stream()
            
            # Analytics
            total_errors = 0
            errors_by_category = {}
            errors_by_severity = {}
            errors_by_hour = [0] * 24
            recent_errors = []
            unresolved_count = 0
            
            for error_doc in errors:
                error = error_doc.to_dict()
                total_errors += 1
                
                # Category breakdown
                category = error.get('category', 'unknown')
                errors_by_category[category] = errors_by_category.get(category, 0) + 1
                
                # Severity breakdown
                severity = error.get('severity', 'unknown')
                errors_by_severity[severity] = errors_by_severity.get(severity, 0) + 1
                
                # Hourly distribution
                try:
                    timestamp = datetime.fromisoformat(error.get('timestamp'))
                    hour_index = (24 - (datetime.now().hour - timestamp.hour)) % 24
                    if 0 <= hour_index < 24:
                        errors_by_hour[hour_index] += 1
                except:
                    pass
                
                # Track unresolved
                if not error.get('resolved', False):
                    unresolved_count += 1
                
                # Recent errors (last 10)
                if len(recent_errors) < 10:
                    recent_errors.append({
                        'error_id': error.get('error_id'),
                        'timestamp': error.get('timestamp'),
                        'category': category,
                        'severity': severity,
                        'message': error.get('error_message', '')[:100],
                        'user_id': error.get('user_id'),
                        'resolved': error.get('resolved', False)
                    })
            
            # Sort recent errors by timestamp
            recent_errors.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
            
            return {
                'period_hours': hours,
                'total_errors': total_errors,
                'unresolved_errors': unresolved_count,
                'resolution_rate': round((total_errors - unresolved_count) / total_errors * 100, 1) if total_errors > 0 else 100,
                'errors_by_category': errors_by_category,
                'errors_by_severity': errors_by_severity,
                'hourly_distribution': errors_by_hour,
                'recent_errors': recent_errors,
                'critical_count': errors_by_severity.get('critical', 0),
                'high_count': errors_by_severity.get('high', 0)
            }
            
        except Exception as e:
            print(f"Error getting dashboard data: {e}")
            return {'error': str(e)}
    
    def get_error_details(self, error_id: str) -> Optional[Dict]:
        """Get full details of a specific error"""
        try:
            error_ref = db.collection('error_logs').document(error_id)
            error_doc = error_ref.get()
            
            if error_doc.exists:
                return error_doc.to_dict()
            return None
            
        except Exception as e:
            print(f"Error retrieving error details: {e}")
            return None
    
    def mark_error_resolved(self, error_id: str, resolution_notes: str, resolved_by: str):
        """Mark an error as resolved"""
        try:
            error_ref = db.collection('error_logs').document(error_id)
            error_ref.update({
                'resolved': True,
                'resolution_notes': resolution_notes,
                'resolved_by': resolved_by,
                'resolved_at': datetime.now().isoformat()
            })
            return True
        except Exception as e:
            print(f"Error marking error as resolved: {e}")
            return False
    
    def get_error_trends(self, days: int = 7) -> Dict:
        """Get error trends over time"""
        try:
            cutoff = datetime.now() - timedelta(days=days)
            
            errors_ref = db.collection('error_logs')
            query = errors_ref.where('timestamp', '>=', cutoff.isoformat())
            errors = query.stream()
            
            # Daily breakdown
            daily_errors = {}
            for error_doc in errors:
                error = error_doc.to_dict()
                try:
                    date = datetime.fromisoformat(error.get('timestamp')).strftime('%Y-%m-%d')
                    daily_errors[date] = daily_errors.get(date, 0) + 1
                except:
                    pass
            
            # Fill in missing dates with 0
            all_dates = []
            for i in range(days):
                date = (datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d')
                all_dates.append(date)
                if date not in daily_errors:
                    daily_errors[date] = 0
            
            all_dates.reverse()
            
            return {
                'dates': all_dates,
                'counts': [daily_errors.get(date, 0) for date in all_dates]
            }
            
        except Exception as e:
            print(f"Error getting error trends: {e}")
            return {'dates': [], 'counts': []}
    
    def _check_alert_threshold(self, category: ErrorCategory, severity: ErrorSeverity):
        """Check if error threshold reached for alerts"""
        # This would integrate with notification system
        # For now, just log critical/high severity errors
        if severity in [ErrorSeverity.CRITICAL, ErrorSeverity.HIGH]:
            print(f"🚨 ALERT: {severity.value.upper()} error in {category.value}")


# Global error logger instance
error_logger = ErrorLogger()


# Decorator for automatic error logging
def log_errors(category: ErrorCategory, severity: ErrorSeverity = ErrorSeverity.MEDIUM):
    """Decorator to automatically log errors in functions"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                error_logger.log_error(e, category, severity, context={
                    'function': func.__name__,
                    'args': str(args)[:100],
                    'kwargs': str(kwargs)[:100]
                })
                raise
        return wrapper
    return decorator
