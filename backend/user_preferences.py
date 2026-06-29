"""
User Personalization System - Watchlist & Preferences
Manages user stock watchlists, preferences, and custom alerts
"""

from datetime import datetime
from typing import List, Dict, Optional
import firebase_admin
from firebase_admin import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

class UserPreferencesManager:
    """Manages user preferences, watchlists, and alerts"""
    
    def __init__(self):
        self.db = firestore.client()
        self.preferences_collection = self.db.collection('user_preferences')
        self.watchlist_collection = self.db.collection('user_watchlists')
        self.alerts_collection = self.db.collection('price_alerts')
    
    # ==================== PREFERENCES ====================
    
    def get_user_preferences(self, user_id: str) -> Dict:
        """Get user preferences or create default ones"""
        try:
            pref_ref = self.preferences_collection.document(user_id)
            pref = pref_ref.get()
            
            if pref.exists:
                return pref.to_dict()
            else:
                # Create default preferences
                default_prefs = {
                    'user_id': user_id,
                    'favorite_stocks': [],
                    'notification_enabled': True,
                    'email_alerts': False,
                    'analysis_depth': 'moderate',  # basic, moderate, detailed
                    'chart_preference': 'line',    # line, candlestick, area
                    'dark_mode': True,
                    'created_at': datetime.now().isoformat(),
                    'updated_at': datetime.now().isoformat()
                }
                pref_ref.set(default_prefs)
                return default_prefs
                
        except Exception as e:
            print(f"❌ Error getting preferences: {e}")
            return {}
    
    def update_user_preferences(self, user_id: str, updates: Dict) -> bool:
        """Update user preferences"""
        try:
            updates['updated_at'] = datetime.now().isoformat()
            
            pref_ref = self.preferences_collection.document(user_id)
            pref_ref.set(updates, merge=True)
            
            return True
            
        except Exception as e:
            print(f"❌ Error updating preferences: {e}")
            return False
    
    def add_favorite_stock(self, user_id: str, stock_symbol: str) -> bool:
        """Add stock to user's favorites"""
        try:
            pref = self.get_user_preferences(user_id)
            favorites = pref.get('favorite_stocks', [])
            
            if stock_symbol not in favorites:
                favorites.append(stock_symbol)
                return self.update_user_preferences(user_id, {'favorite_stocks': favorites})
            
            return True
            
        except Exception as e:
            print(f"❌ Error adding favorite: {e}")
            return False
    
    def remove_favorite_stock(self, user_id: str, stock_symbol: str) -> bool:
        """Remove stock from user's favorites"""
        try:
            pref = self.get_user_preferences(user_id)
            favorites = pref.get('favorite_stocks', [])
            
            if stock_symbol in favorites:
                favorites.remove(stock_symbol)
                return self.update_user_preferences(user_id, {'favorite_stocks': favorites})
            
            return True
            
        except Exception as e:
            print(f"❌ Error removing favorite: {e}")
            return False
    
    # ==================== WATCHLIST ====================
    
    def get_user_watchlist(self, user_id: str) -> List[Dict]:
        """Get user's stock watchlist"""
        try:
            watchlist_docs = self.watchlist_collection.where(filter=FieldFilter('user_id', '==', user_id)).stream()
            
            watchlist = []
            for doc in watchlist_docs:
                data = doc.to_dict()
                data['watchlist_id'] = doc.id
                watchlist.append(data)
            
            # Sort by created_at descending
            watchlist.sort(key=lambda x: x.get('created_at', ''), reverse=True)
            return watchlist
            
        except Exception as e:
            print(f"❌ Error getting watchlist: {e}")
            return []
    
    def add_to_watchlist(self, user_id: str, stock_symbol: str, notes: str = "") -> Optional[str]:
        """Add stock to watchlist"""
        try:
            # Check if already in watchlist
            existing = self.watchlist_collection.where(filter=FieldFilter('user_id', '==', user_id))\
                                                  .where(filter=FieldFilter('stock_symbol', '==', stock_symbol))\
                                                  .limit(1).get()
            
            if len(list(existing)) > 0:
                return "already_exists"
            
            watchlist_item = {
                'user_id': user_id,
                'stock_symbol': stock_symbol,
                'notes': notes,
                'created_at': datetime.now().isoformat(),
                'last_viewed': datetime.now().isoformat()
            }
            
            doc_ref = self.watchlist_collection.add(watchlist_item)
            return doc_ref[1].id
            
        except Exception as e:
            print(f"❌ Error adding to watchlist: {e}")
            return None
    
    def remove_from_watchlist(self, watchlist_id: str) -> bool:
        """Remove stock from watchlist"""
        try:
            self.watchlist_collection.document(watchlist_id).delete()
            return True
            
        except Exception as e:
            print(f"❌ Error removing from watchlist: {e}")
            return False
    
    def update_watchlist_notes(self, watchlist_id: str, notes: str) -> bool:
        """Update notes for a watchlist item"""
        try:
            self.watchlist_collection.document(watchlist_id).update({
                'notes': notes,
                'updated_at': datetime.now().isoformat()
            })
            return True
            
        except Exception as e:
            print(f"❌ Error updating notes: {e}")
            return False
    
    # ==================== PRICE ALERTS ====================
    
    def create_price_alert(self, user_id: str, stock_symbol: str, 
                          alert_type: str, target_price: float) -> Optional[str]:
        """
        Create price alert
        alert_type: 'above' or 'below'
        """
        try:
            alert = {
                'user_id': user_id,
                'stock_symbol': stock_symbol,
                'alert_type': alert_type,  # 'above' or 'below'
                'target_price': target_price,
                'status': 'active',  # active, triggered, disabled
                'created_at': datetime.now().isoformat(),
                'triggered_at': None
            }
            
            doc_ref = self.alerts_collection.add(alert)
            return doc_ref[1].id
            
        except Exception as e:
            print(f"❌ Error creating alert: {e}")
            return None
    
    def get_user_alerts(self, user_id: str, status: str = 'active') -> List[Dict]:
        """Get user's price alerts"""
        try:
            query = self.alerts_collection.where(filter=FieldFilter('user_id', '==', user_id))
            
            if status:
                query = query.where(filter=FieldFilter('status', '==', status))
            
            alert_docs = query.stream()
            
            alerts = []
            for doc in alert_docs:
                data = doc.to_dict()
                data['alert_id'] = doc.id
                alerts.append(data)
            
            return alerts
            
        except Exception as e:
            print(f"❌ Error getting alerts: {e}")
            return []
    
    def check_and_trigger_alerts(self, stock_symbol: str, current_price: float) -> List[Dict]:
        """Check if any alerts should be triggered for a stock"""
        try:
            # Get all active alerts for this stock
            alerts = self.alerts_collection.where(filter=FieldFilter('stock_symbol', '==', stock_symbol))\
                                           .where(filter=FieldFilter('status', '==', 'active')).stream()
            
            triggered_alerts = []
            
            for alert_doc in alerts:
                alert = alert_doc.to_dict()
                alert_id = alert_doc.id
                
                should_trigger = False
                
                if alert['alert_type'] == 'above' and current_price >= alert['target_price']:
                    should_trigger = True
                elif alert['alert_type'] == 'below' and current_price <= alert['target_price']:
                    should_trigger = True
                
                if should_trigger:
                    # Update alert status
                    self.alerts_collection.document(alert_id).update({
                        'status': 'triggered',
                        'triggered_at': datetime.now().isoformat(),
                        'triggered_price': current_price
                    })
                    
                    alert['alert_id'] = alert_id
                    triggered_alerts.append(alert)
            
            return triggered_alerts
            
        except Exception as e:
            print(f"❌ Error checking alerts: {e}")
            return []
    
    def delete_alert(self, alert_id: str) -> bool:
        """Delete a price alert"""
        try:
            self.alerts_collection.document(alert_id).delete()
            return True
            
        except Exception as e:
            print(f"❌ Error deleting alert: {e}")
            return False
    
    # ==================== ANALYTICS ====================
    
    def get_user_stats(self, user_id: str) -> Dict:
        """Get user engagement statistics"""
        try:
            watchlist_count = len(self.get_user_watchlist(user_id))
            alert_count = len(self.get_user_alerts(user_id, status='active'))
            prefs = self.get_user_preferences(user_id)
            favorite_count = len(prefs.get('favorite_stocks', []))
            
            return {
                'watchlist_count': watchlist_count,
                'active_alerts': alert_count,
                'favorite_stocks': favorite_count,
                'preferences_set': bool(prefs)
            }
            
        except Exception as e:
            print(f"❌ Error getting stats: {e}")
            return {}
