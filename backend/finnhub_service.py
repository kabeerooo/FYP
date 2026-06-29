# finnhub_service.py
"""
Finnhub API Service - Fast real-time stock data
Free tier: 60 API calls/minute (much faster than yfinance!)
Fallback to yfinance if Finnhub fails or rate limited
✅ PERFORMANCE FIX: Made async for parallel batch requests
"""

import finnhub
import httpx
import os
from dotenv import load_dotenv
import yfinance as yf
from datetime import datetime

load_dotenv()

# Initialize Finnhub client
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")
finnhub_client = finnhub.Client(api_key=FINNHUB_API_KEY) if FINNHUB_API_KEY else None

# Shared async HTTP client — created once, closed on application shutdown.
_async_http_client: httpx.AsyncClient | None = None

async def get_async_http_client() -> httpx.AsyncClient:
    """Return the shared async HTTP client, creating it on first call."""
    global _async_http_client
    if _async_http_client is None or _async_http_client.is_closed:
        _async_http_client = httpx.AsyncClient(timeout=10.0)
    return _async_http_client

async def close_async_http_client() -> None:
    """Close the shared async HTTP client. Call this on application shutdown."""
    global _async_http_client
    if _async_http_client and not _async_http_client.is_closed:
        await _async_http_client.aclose()
        _async_http_client = None

async def get_stock_quote_async(symbol: str):
    """
    ✅ ASYNC version of get_stock_quote for parallel batch requests
    
    Get real-time stock quote from Finnhub API
    Response time: <100ms (vs 2-5s for yfinance)
    
    Returns: {
        "symbol": str,
        "current_price": float,
        "change": float,
        "change_percent": float,
        "high": float,
        "low": float,
        "open": float,
        "previous_close": float,
        "volume": int,
        "timestamp": int
    }
    """
    try:
        if not FINNHUB_API_KEY:
            raise Exception("Finnhub API key not configured")
        
        # ✅ ASYNC HTTP request to Finnhub (truly non-blocking)
        client = await get_async_http_client()
        url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={FINNHUB_API_KEY}"
        response = await client.get(url)
        
        if response.status_code != 200:
            raise Exception(f"Finnhub API error: {response.status_code}")
        
        quote = response.json()
        
        # Check if data is valid
        if quote.get('c', 0) == 0:
            raise Exception("Invalid quote data from Finnhub")
        
        # ✅ PERFORMANCE FIX: Don't fetch volume from yfinance - it's VERY slow
        # Volume will be fetched separately only when needed
        volume = 0
        
        return {
            "symbol": symbol.upper(),
            "current_price": quote['c'],  # Current price
            "change": quote['d'],  # Change
            "change_percent": quote['dp'],  # Percentage change
            "high": quote['h'],  # Day high
            "low": quote['l'],  # Day low
            "open": quote['o'],  # Day open
            "previous_close": quote['pc'],  # Previous close
            "volume": volume,  # Will be 0 for now (fast loading more important)
            "timestamp": quote['t']  # Unix timestamp
        }
    
    except Exception as e:
        # Fallback to yfinance using history() — avoids slow .info call
        print(f"⚠️ Finnhub error for {symbol}: {e}, falling back to yfinance")
        try:
            stock = yf.Ticker(symbol)
            hist = stock.history(period="2d")
            if hist.empty:
                raise Exception("No history data from yfinance")
            current_price = float(hist["Close"].iloc[-1])
            prev_close = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else current_price
            change = current_price - prev_close
            change_pct = (change / prev_close * 100) if prev_close else 0
            return {
                "symbol": symbol.upper(),
                "current_price": current_price,
                "change": change,
                "change_percent": change_pct,
                "high": float(hist["High"].iloc[-1]),
                "low": float(hist["Low"].iloc[-1]),
                "open": float(hist["Open"].iloc[-1]),
                "previous_close": prev_close,
                "volume": int(hist["Volume"].iloc[-1]) if "Volume" in hist else 0,
                "timestamp": int(datetime.now().timestamp())
            }
        except Exception as yf_error:
            print(f"❌ Both Finnhub and yfinance failed for {symbol}: {yf_error}")
            return None

def get_stock_quote(symbol: str):
    """
    SYNC version (for backward compatibility)
    Get real-time stock quote with HYBRID approach:
    - Finnhub for fast price data (<100ms)
    - yfinance for volume (Finnhub free tier doesn't include it)
    
    Returns: {
        "symbol": str,
        "current_price": float,
        "change": float,
        "change_percent": float,
        "high": float,
        "low": float,
        "open": float,
        "previous_close": float,
        "volume": int,
        "timestamp": int
    }
    """
    try:
        if not finnhub_client:
            raise Exception("Finnhub API key not configured")
        
        # Finnhub real-time quote (response time: <100ms)
        quote = finnhub_client.quote(symbol)
        
        # Check if data is valid
        if quote.get('c', 0) == 0:
            raise Exception("Invalid quote data from Finnhub")
        
        # ✅ PERFORMANCE FIX: Don't fetch volume from yfinance - it's VERY slow
        # Volume will be fetched separately only when needed
        volume = 0
        
        return {
            "symbol": symbol.upper(),
            "current_price": quote['c'],  # Current price
            "change": quote['d'],  # Change
            "change_percent": quote['dp'],  # Percentage change
            "high": quote['h'],  # Day high
            "low": quote['l'],  # Day low
            "open": quote['o'],  # Day open
            "previous_close": quote['pc'],  # Previous close
            "volume": volume,  # Will be 0 for now (fast loading more important)
            "timestamp": quote['t']  # Unix timestamp
        }
    
    except Exception as e:
        # Fallback to yfinance using history() — avoids slow .info call
        print(f"⚠️ Finnhub error for {symbol}: {e}, falling back to yfinance")
        try:
            stock = yf.Ticker(symbol)
            hist = stock.history(period="2d")
            if hist.empty:
                raise Exception("No history data from yfinance")
            current_price = float(hist["Close"].iloc[-1])
            prev_close = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else current_price
            change = current_price - prev_close
            change_pct = (change / prev_close * 100) if prev_close else 0
            return {
                "symbol": symbol.upper(),
                "current_price": current_price,
                "change": change,
                "change_percent": change_pct,
                "high": float(hist["High"].iloc[-1]),
                "low": float(hist["Low"].iloc[-1]),
                "open": float(hist["Open"].iloc[-1]),
                "previous_close": prev_close,
                "volume": int(hist["Volume"].iloc[-1]) if "Volume" in hist else 0,
                "timestamp": int(datetime.now().timestamp())
            }
        except Exception as yf_error:
            print(f"❌ Both Finnhub and yfinance failed for {symbol}: {yf_error}")
            return None


def get_company_profile(symbol: str):
    """
    Get company profile information
    Returns: {
        "name": str,
        "ticker": str,
        "exchange": str,
        "industry": str,
        "sector": str,
        "country": str,
        "logo": str,
        "market_cap": float
    }
    """
    # Use yfinance for market cap as Finnhub free tier doesn't always include it
    # This is a hybrid approach: Finnhub for fast quotes, yfinance for market cap
    try:
        stock = yf.Ticker(symbol)
        info = stock.info
        
        # Get market cap from yfinance (most reliable)
        market_cap = (
            info.get('marketCap') or 
            info.get('market_cap') or 
            info.get('MarketCap') or 
            0
        )
        
        # If still 0, calculate from shares outstanding
        if market_cap == 0:
            shares = info.get('sharesOutstanding') or info.get('shares_outstanding') or 0
            current_price = info.get('currentPrice') or info.get('regularMarketPrice') or 0
            if shares > 0 and current_price > 0:
                market_cap = int(shares * current_price)
        
        return {
            "name": info.get('longName', info.get('shortName', 'Unknown')),
            "ticker": symbol.upper(),
            "exchange": info.get('exchange', 'Unknown'),
            "industry": info.get('industry', 'Unknown'),
            "sector": info.get('sector', 'Unknown'),
            "country": info.get('country', 'Unknown'),
            "logo": info.get('logo_url', ''),
            "market_cap": market_cap
        }
    
    except Exception as e:
        print(f"⚠️ Error getting company profile for {symbol}: {e}")
        # Return minimal data to avoid breaking the app
        return {
            "name": symbol.upper(),
            "ticker": symbol.upper(),
            "exchange": "Unknown",
            "industry": "Unknown",
            "sector": "Unknown",
            "country": "Unknown",
            "logo": "",
            "market_cap": 0
        }


def get_stock_news(symbol: str, count: int = 10):
    """
    Get latest news for a stock
    Returns: List of news articles
    """
    try:
        if not finnhub_client:
            raise Exception("Finnhub API key not configured")
        
        # Finnhub company news (response time: <200ms)
        from_date = datetime.now().strftime('%Y-%m-%d')
        to_date = datetime.now().strftime('%Y-%m-%d')
        news = finnhub_client.company_news(symbol, _from=from_date, to=to_date)
        
        # Format news articles
        articles = []
        for article in news[:count]:
            articles.append({
                "title": article.get('headline', 'No title'),
                "summary": article.get('summary', 'No summary'),
                "url": article.get('url', ''),
                "source": article.get('source', 'Unknown'),
                "published_at": article.get('datetime', 0)
            })
        
        return articles
    
    except Exception as e:
        print(f"⚠️ Finnhub news error for {symbol}: {e}")
        return []


def get_multiple_quotes(symbols: list):
    """
    Get quotes for multiple symbols efficiently
    Returns: Dictionary with symbol as key and quote data as value
    """
    results = {}
    for symbol in symbols:
        quote = get_stock_quote(symbol)
        if quote:
            results[symbol.upper()] = quote
    return results


# Test function
if __name__ == "__main__":
    print("🚀 Testing Finnhub Service...")
    
    # Test single quote
    print("\n📊 Testing AAPL quote...")
    aapl_quote = get_stock_quote("AAPL")
    if aapl_quote:
        print(f"✅ AAPL: ${aapl_quote['current_price']:.2f} ({aapl_quote['change_percent']:+.2f}%)")
    
    # Test company profile
    print("\n🏆 Testing AAPL profile...")
    aapl_profile = get_company_profile("AAPL")
    if aapl_profile:
        print(f"✅ {aapl_profile['name']} - {aapl_profile['sector']}")
    
    # Test multiple quotes
    print("\n📈 Testing multiple quotes...")
    stocks = ["AAPL", "MSFT", "GOOGL", "TSLA"]
    quotes = get_multiple_quotes(stocks)
    for symbol, data in quotes.items():
        print(f"✅ {symbol}: ${data['current_price']:.2f} ({data['change_percent']:+.2f}%)")
    
    print("\n🏆 All tests complete!")
