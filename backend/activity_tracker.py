"""
User Activity Tracking and Heatmap Generation
Monitors user interactions and generates activity visualizations
"""

from datetime import datetime, timedelta
from typing import Dict, List
from collections import defaultdict
from auth_routes import db

class ActivityTracker:
    """Tracks user activities for heatmap generation"""
    
    def __init__(self):
        self.activity_types = {
            'LOGIN': 'User Login',
            'LOGOUT': 'User Logout',
            'CHAT': 'Chat Message',
            'PREDICTION': 'Asset Prediction Request',
            'WATCHLIST_ADD': 'Added to Watchlist',
            'WATCHLIST_REMOVE': 'Removed from Watchlist',
            'DASHBOARD_VIEW': 'Viewed Dashboard',
            'PROFILE_UPDATE': 'Updated Profile'
        }
    
    def log_activity(self, user_id: str, activity_type: str, details: Dict = None):
        """Log a user activity"""
        try:
            activity_data = {
                'user_id': user_id,
                'activity_type': activity_type,
                'activity_name': self.activity_types.get(activity_type, activity_type),
                'timestamp': datetime.now().isoformat(),
                'hour': datetime.now().hour,
                'day_of_week': datetime.now().strftime('%A'),
                'date': datetime.now().strftime('%Y-%m-%d'),
                'details': details or {}
            }
            
            # Store in Firestore
            db.collection('user_activities').add(activity_data)
            
            return True
        except Exception as e:
            print(f"Error logging activity: {e}")
            return False
    
    def get_user_heatmap_data(self, user_id: str, days: int = 30) -> Dict:
        """Generate heatmap data for a specific user"""
        try:
            # Calculate date range
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            # Query activities
            activities_ref = db.collection('user_activities')
            query = activities_ref.where('user_id', '==', user_id)\
                                  .where('timestamp', '>=', start_date.isoformat())
            
            activities = query.stream()
            
            # Process data for heatmap
            hourly_data = defaultdict(lambda: defaultdict(int))
            daily_totals = defaultdict(int)
            activity_breakdown = defaultdict(int)
            
            for activity_doc in activities:
                activity = activity_doc.to_dict()
                day = activity.get('day_of_week', 'Unknown')
                hour = activity.get('hour', 0)
                activity_type = activity.get('activity_type', 'UNKNOWN')
                
                hourly_data[day][hour] += 1
                daily_totals[day] += 1
                activity_breakdown[activity_type] += 1
            
            # Convert to list format for frontend
            heatmap_matrix = []
            days_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            
            for day in days_order:
                day_data = []
                for hour in range(24):
                    count = hourly_data[day][hour]
                    day_data.append({
                        'day': day,
                        'hour': hour,
                        'count': count,
                        'intensity': min(count / 10.0, 1.0)  # Normalize to 0-1
                    })
                heatmap_matrix.append(day_data)
            
            return {
                'user_id': user_id,
                'period_days': days,
                'heatmap_data': heatmap_matrix,
                'daily_totals': dict(daily_totals),
                'activity_breakdown': dict(activity_breakdown),
                'total_activities': sum(daily_totals.values()),
                'most_active_day': max(daily_totals.items(), key=lambda x: x[1])[0] if daily_totals else None,
                'peak_hour': self._find_peak_hour(hourly_data)
            }
            
        except Exception as e:
            print(f"Error generating heatmap data: {e}")
            return {'error': str(e)}
    
    def get_all_users_heatmap(self, days: int = 7) -> Dict:
        """Generate aggregate heatmap for all users"""
        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            activities_ref = db.collection('user_activities')
            query = activities_ref.where('timestamp', '>=', start_date.isoformat())
            activities = query.stream()
            
            hourly_data = defaultdict(lambda: defaultdict(int))
            user_count = set()
            
            for activity_doc in activities:
                activity = activity_doc.to_dict()
                day = activity.get('day_of_week', 'Unknown')
                hour = activity.get('hour', 0)
                user_id = activity.get('user_id')
                
                hourly_data[day][hour] += 1
                user_count.add(user_id)
            
            # Convert to matrix
            heatmap_matrix = []
            days_order = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
            
            max_count = max(
                max(hours.values()) if hours else 0
                for hours in hourly_data.values()
            ) if hourly_data else 1
            
            for day in days_order:
                day_data = []
                for hour in range(24):
                    count = hourly_data[day][hour]
                    day_data.append({
                        'day': day,
                        'hour': hour,
                        'count': count,
                        'intensity': count / max_count if max_count > 0 else 0
                    })
                heatmap_matrix.append(day_data)
            
            return {
                'period_days': days,
                'heatmap_data': heatmap_matrix,
                'total_users': len(user_count),
                'total_activities': sum(sum(hours.values()) for hours in hourly_data.values()),
                'peak_time': self._find_peak_hour(hourly_data)
            }
            
        except Exception as e:
            print(f"Error generating aggregate heatmap: {e}")
            return {'error': str(e)}
    
    def _find_peak_hour(self, hourly_data: Dict) -> Dict:
        """Find the most active hour"""
        peak_count = 0
        peak_day = None
        peak_hour = None
        
        for day, hours in hourly_data.items():
            for hour, count in hours.items():
                if count > peak_count:
                    peak_count = count
                    peak_day = day
                    peak_hour = hour
        
        return {
            'day': peak_day,
            'hour': peak_hour,
            'count': peak_count,
            'time_string': f"{peak_day} at {peak_hour:02d}:00" if peak_day else "No activity"
        }
    
    def get_activity_timeline(self, user_id: str, hours: int = 24) -> List[Dict]:
        """Get recent activity timeline"""
        try:
            cutoff = datetime.now() - timedelta(hours=hours)
            
            activities_ref = db.collection('user_activities')
            query = activities_ref.where('user_id', '==', user_id)\
                                  .where('timestamp', '>=', cutoff.isoformat())\
                                  .order_by('timestamp', direction='DESCENDING')\
                                  .limit(100)
            
            activities = query.stream()
            
            timeline = []
            for activity_doc in activities:
                activity = activity_doc.to_dict()
                timeline.append({
                    'activity_name': activity.get('activity_name'),
                    'timestamp': activity.get('timestamp'),
                    'details': activity.get('details', {})
                })
            
            return timeline
            
        except Exception as e:
            print(f"Error getting activity timeline: {e}")
            return []


# Global activity tracker instance
activity_tracker = ActivityTracker()
