"""
Historical Data Caching System
Caches stock prices, news, and technical indicators to reduce API calls and improve performance
✅ PERFORMANCE FIX: Added in-memory cache layer to avoid Firestore latency
"""

from datetime import datetime, timedelta
from typing import List, Dict, Optional
import firebase_admin
from firebase_admin import firestore
import yfinance as yf
from collections import defaultdict

class DataCacheManager:
    """Manages caching of stock data, news, and technical indicators"""
    
    def __init__(self):
        self.db = firestore.client()
        self.price_cache = self.db.collection('cached_prices')
        self.news_cache = self.db.collection('cached_news')
        self.indicators_cache = self.db.collection('cached_indicators')
        
        # ✅ IN-MEMORY CACHE (for ultra-fast access, avoids Firestore roundtrip)
        self._memory_cache = {}
        self._memory_cache_timestamps = {}
        
        # Cache expiration times (in minutes)
        self.PRICE_CACHE_TTL = 5      # 5 minutes for current prices
        self.NEWS_CACHE_TTL = 30      # 30 minutes for news
        self.INDICATOR_CACHE_TTL = 60 # 1 hour for technical indicators
        self.HISTORICAL_CACHE_TTL = 1440  # 24 hours for historical data
    
    # ==================== PRICE CACHING ====================
    
    def get_cached_price(self, stock_symbol: str) -> Optional[Dict]:
        """Get cached current price if available and not expired"""
        try:
            # ✅ CHECK IN-MEMORY CACHE FIRST (fastest - no network call)
            cache_key = f"{stock_symbol}_current"
            if cache_key in self._memory_cache:
                cached_time = self._memory_cache_timestamps.get(cache_key)
                if cached_time and datetime.now() - cached_time < timedelta(minutes=self.PRICE_CACHE_TTL):
                    return self._memory_cache[cache_key]
                else:
                    # Expired - remove from memory cache
                    del self._memory_cache[cache_key]
                    del self._memory_cache_timestamps[cache_key]
            
            # ✅ CHECK FIRESTORE CACHE (slower but persistent)
            doc_ref = self.price_cache.document(cache_key)
            doc = doc_ref.get()
            
            if doc.exists:
                data = doc.to_dict()
                cached_time = datetime.fromisoformat(data['cached_at'])
                
                # Check if cache is still valid
                if datetime.now() - cached_time < timedelta(minutes=self.PRICE_CACHE_TTL):
                    result = {
                        'price': data['price'],
                        'change': data.get('change', 0),
                        'change_percent': data.get('change_percent', 0),
                        'volume': data.get('volume', 0),
                        'market_cap': data.get('market_cap', 0),
                        'high': data.get('high', data['price']),
                        'low': data.get('low', data['price']),
                        'open': data.get('open', data['price']),
                        'cached': True
                    }
                    
                    # ✅ STORE IN MEMORY CACHE for next time
                    self._memory_cache[cache_key] = result
                    self._memory_cache_timestamps[cache_key] = cached_time
                    
                    return result
            
            return None
            
        except Exception as e:
            print(f"❌ Error getting cached price: {e}")
            return None
    
    def cache_current_price(self, stock_symbol: str, price_data: Dict):
        """Cache current stock price"""
        try:
            cache_key = f"{stock_symbol}_current"
            now = datetime.now()
            
            cache_entry = {
                'stock_symbol': stock_symbol,
                'price': price_data.get('price'),
                'change': price_data.get('change', 0),
                'change_percent': price_data.get('change_percent', 0),
                'volume': price_data.get('volume', 0),
                'market_cap': price_data.get('market_cap', 0),
                'high': price_data.get('high', price_data.get('price', 0)),
                'low': price_data.get('low', price_data.get('price', 0)),
                'open': price_data.get('open', price_data.get('price', 0)),
                'cached_at': now.isoformat(),
                'expires_at': (now + timedelta(minutes=self.PRICE_CACHE_TTL)).isoformat()
            }
            
            # ✅ STORE IN MEMORY CACHE FIRST (instant access)
            memory_data = {
                'price': price_data.get('price'),
                'change': price_data.get('change', 0),
                'change_percent': price_data.get('change_percent', 0),
                'volume': price_data.get('volume', 0),
                'market_cap': price_data.get('market_cap', 0),
                'high': price_data.get('high', price_data.get('price', 0)),
                'low': price_data.get('low', price_data.get('price', 0)),
                'open': price_data.get('open', price_data.get('price', 0)),
                'cached': True
            }
            self._memory_cache[cache_key] = memory_data
            self._memory_cache_timestamps[cache_key] = now
            
            # ✅ ALSO STORE IN FIRESTORE (persistent across restarts)
            doc_ref = self.price_cache.document(cache_key)
            doc_ref.set(cache_entry)
            
        except Exception as e:
            print(f"❌ Error caching price: {e}")
    
    def get_cached_historical(self, stock_symbol: str, period: str = '7d') -> Optional[List[Dict]]:
        """Get cached historical price data"""
        try:
            doc_ref = self.price_cache.document(f"{stock_symbol}_hist_{period}")
            doc = doc_ref.get()
            
            if doc.exists:
                data = doc.to_dict()
                cached_time = datetime.fromisoformat(data['cached_at'])
                
                # Check if cache is still valid
                if datetime.now() - cached_time < timedelta(minutes=self.HISTORICAL_CACHE_TTL):
                    return data.get('historical_data', [])
            
            return None
            
        except Exception as e:
            print(f"❌ Error getting cached historical: {e}")
            return None
    
    def cache_historical_data(self, stock_symbol: str, period: str, historical_data: List[Dict]):
        """Cache historical price data"""
        try:
            cache_entry = {
                'stock_symbol': stock_symbol,
                'period': period,
                'historical_data': historical_data,
                'cached_at': datetime.now().isoformat(),
                'expires_at': (datetime.now() + timedelta(minutes=self.HISTORICAL_CACHE_TTL)).isoformat()
            }
            
            doc_ref = self.price_cache.document(f"{stock_symbol}_hist_{period}")
            doc_ref.set(cache_entry)
            
        except Exception as e:
            print(f"❌ Error caching historical data: {e}")
    
    # ==================== NEWS CACHING ====================
    
    def get_cached_news(self, stock_symbol: str) -> Optional[List[Dict]]:
        """Get cached news articles"""
        try:
            doc_ref = self.news_cache.document(stock_symbol)
            doc = doc_ref.get()
            
            if doc.exists:
                data = doc.to_dict()
                cached_time = datetime.fromisoformat(data['cached_at'])
                
                # Check if cache is still valid
                if datetime.now() - cached_time < timedelta(minutes=self.NEWS_CACHE_TTL):
                    return data.get('articles', [])
            
            return None
            
        except Exception as e:
            print(f"❌ Error getting cached news: {e}")
            return None
    
    def cache_news(self, stock_symbol: str, articles: List[Dict]):
        """Cache news articles"""
        try:
            cache_entry = {
                'stock_symbol': stock_symbol,
                'articles': articles[:10],  # Store only top 10 articles
                'cached_at': datetime.now().isoformat(),
                'expires_at': (datetime.now() + timedelta(minutes=self.NEWS_CACHE_TTL)).isoformat(),
                'article_count': len(articles)
            }
            
            doc_ref = self.news_cache.document(stock_symbol)
            doc_ref.set(cache_entry)
            
        except Exception as e:
            print(f"❌ Error caching news: {e}")
    
    # ==================== TECHNICAL INDICATORS CACHING ====================
    
    def get_cached_indicators(self, stock_symbol: str) -> Optional[Dict]:
        """Get cached technical indicators"""
        try:
            doc_ref = self.indicators_cache.document(stock_symbol)
            doc = doc_ref.get()
            
            if doc.exists:
                data = doc.to_dict()
                cached_time = datetime.fromisoformat(data['cached_at'])
                
                # Check if cache is still valid
                if datetime.now() - cached_time < timedelta(minutes=self.INDICATOR_CACHE_TTL):
                    return data.get('indicators', {})
            
            return None
            
        except Exception as e:
            print(f"❌ Error getting cached indicators: {e}")
            return None
    
    def cache_indicators(self, stock_symbol: str, indicators: Dict):
        """Cache technical indicators"""
        try:
            cache_entry = {
                'stock_symbol': stock_symbol,
                'indicators': indicators,
                'cached_at': datetime.now().isoformat(),
                'expires_at': (datetime.now() + timedelta(minutes=self.INDICATOR_CACHE_TTL)).isoformat()
            }
            
            doc_ref = self.indicators_cache.document(stock_symbol)
            doc_ref.set(cache_entry)
            
        except Exception as e:
            print(f"❌ Error caching indicators: {e}")
    
    def calculate_and_cache_indicators(self, stock_symbol: str) -> Dict:
        """Calculate technical indicators and cache them"""
        try:
            # Fetch historical data
            ticker = yf.Ticker(stock_symbol)
            hist = ticker.history(period='3mo')  # 3 months for indicators
            
            if hist.empty:
                return {}
            
            # Calculate basic indicators
            indicators = {}
            
            # Moving Averages
            indicators['sma_20'] = float(hist['Close'].rolling(window=20).mean().iloc[-1])
            indicators['sma_50'] = float(hist['Close'].rolling(window=50).mean().iloc[-1])
            
            # RSI (Relative Strength Index)
            delta = hist['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            indicators['rsi'] = float(100 - (100 / (1 + rs.iloc[-1])))
            
            # Volatility
            indicators['volatility'] = float(hist['Close'].pct_change().std() * 100)
            
            # Volume analysis
            indicators['avg_volume'] = int(hist['Volume'].mean())
            indicators['current_volume'] = int(hist['Volume'].iloc[-1])
            
            # Price range
            indicators['52w_high'] = float(hist['Close'].max())
            indicators['52w_low'] = float(hist['Close'].min())
            
            # Cache the indicators
            self.cache_indicators(stock_symbol, indicators)
            
            return indicators
            
        except Exception as e:
            print(f"❌ Error calculating indicators: {e}")
            return {}
    
    # ==================== CACHE MANAGEMENT ====================
    
    def clear_expired_cache(self):
        """Clear all expired cache entries"""
        try:
            now = datetime.now().isoformat()
            collections = [self.price_cache, self.news_cache, self.indicators_cache]
            
            total_deleted = 0
            
            for collection in collections:
                docs = collection.where('expires_at', '<', now).stream()
                
                for doc in docs:
                    doc.reference.delete()
                    total_deleted += 1
            
            return total_deleted
            
        except Exception as e:
            print(f"❌ Error clearing expired cache: {e}")
            return 0
    
    def get_cache_stats(self) -> Dict:
        """Get cache statistics"""
        try:
            stats = {
                'price_cache_count': len(list(self.price_cache.stream())),
                'news_cache_count': len(list(self.news_cache.stream())),
                'indicators_cache_count': len(list(self.indicators_cache.stream()))
            }
            
            # Calculate cache hit potential
            total_cached = sum(stats.values())
            stats['total_cached_entries'] = total_cached
            stats['estimated_api_calls_saved'] = total_cached * 10  # Rough estimate
            
            return stats
            
        except Exception as e:
            print(f"❌ Error getting cache stats: {e}")
            return {}
    
    def invalidate_stock_cache(self, stock_symbol: str):
        """Manually invalidate all cache for a specific stock"""
        try:
            # Delete current price cache
            self.price_cache.document(f"{stock_symbol}_current").delete()
            
            # Delete historical caches
            for period in ['1d', '5d', '7d', '1mo', '3mo', '1y']:
                try:
                    self.price_cache.document(f"{stock_symbol}_hist_{period}").delete()
                except:
                    pass
            
            # Delete news cache
            try:
                self.news_cache.document(stock_symbol).delete()
            except:
                pass
            
            # Delete indicators cache
            try:
                self.indicators_cache.document(stock_symbol).delete()
            except:
                pass
            
            return True
            
        except Exception as e:
            print(f"❌ Error invalidating cache: {e}")
            return False
    
    # ==================== BATCH CACHING ====================
    
    def batch_cache_stocks(self, stock_symbols: List[str]) -> Dict:
        """Cache data for multiple stocks at once"""
        try:
            results = {
                'success': [],
                'failed': []
            }
            
            for symbol in stock_symbols:
                try:
                    # Fetch and cache current price
                    ticker = yf.Ticker(symbol)
                    info = ticker.info
                    
                    price_data = {
                        'price': info.get('currentPrice', info.get('regularMarketPrice', 0)),
                        'change': info.get('regularMarketChange', 0),
                        'change_percent': info.get('regularMarketChangePercent', 0),
                        'volume': info.get('volume', 0)
                    }
                    
                    self.cache_current_price(symbol, price_data)
                    
                    # Calculate and cache indicators
                    self.calculate_and_cache_indicators(symbol)
                    
                    results['success'].append(symbol)
                    
                except Exception as e:
                    print(f"Failed to cache {symbol}: {e}")
                    results['failed'].append(symbol)
            
            return results
            
        except Exception as e:
            print(f"❌ Error batch caching: {e}")
            return {'success': [], 'failed': stock_symbols}
