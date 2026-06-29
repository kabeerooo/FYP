"""
Advanced Analytics Engine
Tracks stock interest, user engagement, trending queries, and chatbot performance
"""

from datetime import datetime, timedelta
from typing import List, Dict, Optional
from collections import Counter, defaultdict
import firebase_admin
from firebase_admin import firestore

from firebase_admin import firestore as _firestore

class AnalyticsEngine:
    """Advanced analytics for user behavior and system performance"""
    
    def __init__(self):
        self.db = firestore.client()
        self.analytics_collection = self.db.collection('analytics_events')
        self.stock_interest_collection = self.db.collection('stock_interest')
        self.query_patterns_collection = self.db.collection('query_patterns')
        self.performance_metrics = self.db.collection('performance_metrics')
    
    # ==================== EVENT TRACKING ====================
    
    def track_event(self, event_type: str, user_id: str, metadata: Dict = None):
        """
        Track analytics event
        event_types: stock_query, stock_view, feature_use, export, search, reaction
        """
        try:
            event = {
                'event_type': event_type,
                'user_id': user_id,
                'timestamp': datetime.now().isoformat(),
                'metadata': metadata or {}
            }
            
            self.analytics_collection.add(event)
            
        except Exception as e:
            print(f"❌ Error tracking event: {e}")
    
    # ==================== STOCK INTEREST ANALYTICS ====================
    
    def track_stock_interest(self, stock_symbol: str, user_id: str, query_type: str):
        """Track user interest in specific stocks.
        Uses Firestore atomic operations to avoid lost-update races under concurrent requests.
        """
        try:
            today = datetime.now().date().isoformat()
            doc_id = f"{stock_symbol}_{today}"
            doc_ref = self.stock_interest_collection.document(doc_id)

            doc_ref.set(
                {
                    "stock_symbol": stock_symbol,
                    "date": today,
                    "query_count": _firestore.Increment(1),
                    "unique_users": _firestore.ArrayUnion([user_id]),
                    f"query_types.{query_type}": _firestore.Increment(1),
                },
                merge=True,
            )
        except Exception as e:
            print(f"❌ Error tracking stock interest: {e}")
    
    def get_trending_stocks(self, days: int = 7, limit: int = 10) -> List[Dict]:
        """Get most queried stocks in last N days"""
        try:
            start_date = (datetime.now() - timedelta(days=days)).date().isoformat()
            
            docs = self.stock_interest_collection.where('date', '>=', start_date).stream()
            
            stock_totals = defaultdict(lambda: {'count': 0, 'users': set()})
            
            for doc in docs:
                data = doc.to_dict()
                symbol = data['stock_symbol']
                stock_totals[symbol]['count'] += data.get('query_count', 0)
                stock_totals[symbol]['users'].update(data.get('unique_users', []))
            
            # Convert to list and sort
            trending = []
            for symbol, stats in stock_totals.items():
                trending.append({
                    'stock_symbol': symbol,
                    'query_count': stats['count'],
                    'unique_users': len(stats['users']),
                    'popularity_score': stats['count'] * 0.6 + len(stats['users']) * 0.4
                })
            
            trending.sort(key=lambda x: x['popularity_score'], reverse=True)
            return trending[:limit]
            
        except Exception as e:
            print(f"❌ Error getting trending stocks: {e}")
            return []
    
    def get_stock_interest_breakdown(self, stock_symbol: str, days: int = 30) -> Dict:
        """Get detailed breakdown of interest in a specific stock"""
        try:
            start_date = (datetime.now() - timedelta(days=days)).date().isoformat()
            
            docs = self.stock_interest_collection.where('stock_symbol', '==', stock_symbol)\
                                                  .where('date', '>=', start_date).stream()
            
            daily_data = []
            total_queries = 0
            unique_users = set()
            query_type_totals = Counter()
            
            for doc in docs:
                data = doc.to_dict()
                daily_data.append({
                    'date': data['date'],
                    'queries': data.get('query_count', 0)
                })
                total_queries += data.get('query_count', 0)
                unique_users.update(data.get('unique_users', []))
                
                for qtype, count in data.get('query_types', {}).items():
                    query_type_totals[qtype] += count
            
            return {
                'stock_symbol': stock_symbol,
                'period_days': days,
                'total_queries': total_queries,
                'unique_users': len(unique_users),
                'daily_breakdown': sorted(daily_data, key=lambda x: x['date']),
                'query_types': dict(query_type_totals),
                'avg_queries_per_day': total_queries / days if days > 0 else 0
            }
            
        except Exception as e:
            print(f"❌ Error getting stock interest breakdown: {e}")
            return {}
    
    # ==================== QUERY PATTERN ANALYTICS ====================
    
    def track_query_pattern(self, user_id: str, query: str, intent: str, 
                           stock_mentioned: Optional[str] = None):
        """Track query patterns for analysis"""
        try:
            pattern = {
                'user_id': user_id,
                'query': query,
                'intent': intent,
                'stock_mentioned': stock_mentioned,
                'timestamp': datetime.now().isoformat(),
                'query_length': len(query.split()),
                'hour': datetime.now().hour
            }
            
            self.query_patterns_collection.add(pattern)
            
        except Exception as e:
            print(f"❌ Error tracking query pattern: {e}")
    
    def get_popular_queries(self, limit: int = 20) -> List[Dict]:
        """Get most common user queries"""
        try:
            # Get recent queries (last 30 days)
            start_date = (datetime.now() - timedelta(days=30)).isoformat()
            
            docs = self.query_patterns_collection.where('timestamp', '>=', start_date).stream()
            
            query_counter = Counter()
            
            for doc in docs:
                data = doc.to_dict()
                query_lower = data['query'].lower().strip()
                query_counter[query_lower] += 1
            
            popular = [
                {'query': query, 'count': count}
                for query, count in query_counter.most_common(limit)
            ]
            
            return popular
            
        except Exception as e:
            print(f"❌ Error getting popular queries: {e}")
            return []
    
    def get_intent_distribution(self, days: int = 7) -> Dict:
        """Get distribution of query intents"""
        try:
            start_date = (datetime.now() - timedelta(days=days)).isoformat()
            
            docs = self.query_patterns_collection.where('timestamp', '>=', start_date).stream()
            
            intent_counter = Counter()
            
            for doc in docs:
                data = doc.to_dict()
                intent_counter[data.get('intent', 'UNKNOWN')] += 1
            
            total = sum(intent_counter.values())
            
            distribution = {
                intent: {
                    'count': count,
                    'percentage': (count / total * 100) if total > 0 else 0
                }
                for intent, count in intent_counter.items()
            }
            
            return distribution
            
        except Exception as e:
            print(f"❌ Error getting intent distribution: {e}")
            return {}
    
    # ==================== USER ENGAGEMENT METRICS ====================
    
    def get_user_engagement_summary(self, days: int = 7) -> Dict:
        """Get overall user engagement metrics"""
        try:
            start_date = (datetime.now() - timedelta(days=days)).isoformat()
            
            events = self.analytics_collection.where('timestamp', '>=', start_date).stream()
            
            total_events = 0
            unique_users = set()
            event_types = Counter()
            hourly_activity = Counter()
            
            for event in events:
                data = event.to_dict()
                total_events += 1
                unique_users.add(data['user_id'])
                event_types[data['event_type']] += 1
                
                # Extract hour from timestamp
                timestamp = datetime.fromisoformat(data['timestamp'])
                hourly_activity[timestamp.hour] += 1
            
            return {
                'period_days': days,
                'total_events': total_events,
                'active_users': len(unique_users),
                'avg_events_per_user': total_events / len(unique_users) if unique_users else 0,
                'event_breakdown': dict(event_types),
                'peak_hours': dict(hourly_activity.most_common(5))
            }
            
        except Exception as e:
            print(f"❌ Error getting engagement summary: {e}")
            return {}
    
    # ==================== PERFORMANCE METRICS ====================
    
    def track_response_time(self, endpoint: str, response_time_ms: float, 
                           success: bool, error_msg: Optional[str] = None):
        """Track API response times"""
        try:
            metric = {
                'endpoint': endpoint,
                'response_time_ms': response_time_ms,
                'success': success,
                'error_msg': error_msg,
                'timestamp': datetime.now().isoformat()
            }
            
            self.performance_metrics.add(metric)
            
        except Exception as e:
            print(f"❌ Error tracking performance: {e}")
    
    def get_performance_stats(self, hours: int = 24) -> Dict:
        """Get performance statistics"""
        try:
            start_time = (datetime.now() - timedelta(hours=hours)).isoformat()
            
            docs = self.performance_metrics.where('timestamp', '>=', start_time).stream()
            
            endpoint_stats = defaultdict(lambda: {
                'count': 0,
                'total_time': 0,
                'success_count': 0,
                'error_count': 0
            })
            
            for doc in docs:
                data = doc.to_dict()
                endpoint = data['endpoint']
                stats = endpoint_stats[endpoint]
                
                stats['count'] += 1
                stats['total_time'] += data['response_time_ms']
                
                if data['success']:
                    stats['success_count'] += 1
                else:
                    stats['error_count'] += 1
            
            # Calculate averages and success rates
            result = {}
            for endpoint, stats in endpoint_stats.items():
                result[endpoint] = {
                    'total_requests': stats['count'],
                    'avg_response_time_ms': stats['total_time'] / stats['count'] if stats['count'] > 0 else 0,
                    'success_rate': (stats['success_count'] / stats['count'] * 100) if stats['count'] > 0 else 0,
                    'error_count': stats['error_count']
                }
            
            return result
            
        except Exception as e:
            print(f"❌ Error getting performance stats: {e}")
            return {}
    
    # ==================== FEATURE USAGE ANALYTICS ====================
    
    def get_feature_usage(self, days: int = 30) -> Dict:
        """Get feature usage statistics"""
        try:
            start_date = (datetime.now() - timedelta(days=days)).isoformat()
            
            events = self.analytics_collection.where('event_type', '==', 'feature_use')\
                                               .where('timestamp', '>=', start_date).stream()
            
            feature_counter = Counter()
            
            for event in events:
                data = event.to_dict()
                feature = data.get('metadata', {}).get('feature', 'unknown')
                feature_counter[feature] += 1
            
            total = sum(feature_counter.values())
            
            usage = {
                feature: {
                    'count': count,
                    'percentage': (count / total * 100) if total > 0 else 0
                }
                for feature, count in feature_counter.most_common()
            }
            
            return {
                'period_days': days,
                'total_feature_uses': total,
                'feature_breakdown': usage
            }
            
        except Exception as e:
            print(f"❌ Error getting feature usage: {e}")
            return {}
