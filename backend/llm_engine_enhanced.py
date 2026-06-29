# llm_engine_enhanced.py - Advanced AI Financial Chatbot
# Enhanced with contextual memory, intent classification, personalized recommendations
# HYBRID APPROACH: Hardcoded handlers + Groq LLM for natural queries

# Fix Windows console encoding to support emojis
import sys
import os
os.environ['PYTHONIOENCODING'] = 'utf-8'
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import os
from pathlib import Path
import json
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import re
from groq import Groq

class IntentClassifier:
    """Classify user intent to route to specialized handlers"""
    
    INTENTS = {
        "GREETING": ["hello", "hi", "hey", "good morning", "good afternoon", "what's up"],
        "PRICE_QUERY": ["price", "cost", "how much", "current", "trading at", "stock", "aapl", "nvda", "tsla", "msft", "apple", "nvidia", "tesla", "microsoft", "gold", "analysis", "insights", "trends"],
        "ADVICE": ["should i", "recommend", "advice", "opinion", "worth", "good investment", "invest in"],
        "EXPLANATION": ["what is", "explain", "tell me about", "define", "how does", "diversification", "p/e ratio", "dollar-cost", "market cap"],
        "COMPARISON": ["vs", "versus", "compare", "better", "difference", "comparison"],
        "RISK": ["risk", "safe", "dangerous", "volatile", "risky"],
        "STRATEGY": ["strategy", "how to invest", "portfolio", "approach", "allocation"],
        "TUTORIAL": ["teach", "learn", "guide", "tutorial", "how do i start", "beginner", "lesson", "start learning"],
        "PREDICTION": ["predict", "forecast", "future", "will it", "going to"],
        "NEWS": ["news", "latest", "happening", "recent"],
        "PORTFOLIO": ["my portfolio", "my stocks", "my holdings", "track"],
    }
    
    @staticmethod
    def classify(message: str) -> Tuple[str, float]:
        """
        Classify intent with confidence score
        Returns: (intent_name, confidence_score)
        """
        msg_lower = message.lower()
        scores = {}
        
        # PRIORITY 1: Check for advice/investment questions first (highest priority)
        advice_phrases = ["should i invest", "should i buy", "should i", "is it worth", "good investment", "worth investing"]
        if any(phrase in msg_lower for phrase in advice_phrases):
            return ("ADVICE", 0.95)
        
        # PRIORITY 2: Check for explanation requests
        explanation_phrases = ["what is", "explain", "tell me about", "define", "how does"]
        if any(phrase in msg_lower for phrase in explanation_phrases):
            # But not if asking for prices
            if "price" not in msg_lower and "cost" not in msg_lower:
                return ("EXPLANATION", 0.9)
        
        # PRIORITY 3: Check for tutorial requests
        tutorial_phrases = ["start tutorial", "beginner tutorial", "lesson", "teach me", "start learning"]
        if any(phrase in msg_lower for phrase in tutorial_phrases):
            return ("TUTORIAL", 0.95)
        
        # PRIORITY 4: Check for comparison requests
        if " vs " in msg_lower or " versus " in msg_lower or "compare" in msg_lower:
            return ("COMPARISON", 0.9)
        
        # PRIORITY 5: Check if message contains stock symbols or company names for price queries
        stock_keywords = ["aapl", "apple", "nvda", "nvidia", "tsla", "tesla", "msft", "microsoft", "gold", "gc=f", "btc"]
        has_stock = any(keyword in msg_lower for keyword in stock_keywords)
        
        if has_stock:
            price_words = ["price", "cost", "trading at", "current", "what's", "how much"]
            if any(word in msg_lower for word in price_words):
                return ("PRICE_QUERY", 0.9)
        
        # PRIORITY 6: Fallback to keyword scoring
        for intent, keywords in IntentClassifier.INTENTS.items():
            score = sum(1 for keyword in keywords if keyword in msg_lower)
            if score > 0:
                scores[intent] = score / len(keywords)
        
        if not scores:
            return ("GENERAL", 0.5)  # Will use LLM for unknown queries
        
        best_intent = max(scores, key=scores.get)
        confidence = scores[best_intent]
        
        # If confidence is too low, use LLM instead
        if confidence < 0.3:
            return ("GENERAL", 0.5)
        
        return (best_intent, min(confidence * 2, 1.0))  # Normalize to max 1.0


class ConversationMemory:
    """Maintains conversation context and history"""
    
    def __init__(self, max_history=20):
        self.history = []
        self.max_history = max_history
        self.user_preferences = {}
        self.mentioned_stocks = []
        self.current_topic = None
        
        # Initialize Groq client for LLM hybrid approach
        self.groq_client = None
        try:
            groq_api_key = os.environ.get("GROQ_API_KEY")
            if groq_api_key:
                self.groq_client = Groq(api_key=groq_api_key)
                print("✅ Groq LLM initialized for hybrid approach")
            else:
                print("⚠️ GROQ_API_KEY not found. Set it with: set GROQ_API_KEY=your_key_here")
                print("   Get free API key at: https://console.groq.com")
                print("   Chatbot will use hardcoded responses only.")
        except Exception as e:
            print(f"⚠️ Groq initialization failed: {e}")
            print("   Chatbot will use hardcoded responses only.")
        
    def add_exchange(self, user_msg: str, bot_response: str, metadata: dict = None):
        """Add conversation exchange"""
        exchange = {
            "timestamp": datetime.now(),
            "user": user_msg,
            "bot": bot_response,
            "metadata": metadata or {}
        }
        self.history.append(exchange)
        
        # Keep only recent history
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]
    
    def get_recent_context(self, n=3) -> str:
        """Get recent conversation for context"""
        recent = self.history[-n:] if len(self.history) >= n else self.history
        context = ""
        for ex in recent:
            context += f"User: {ex['user']}\nBot: {ex['bot'][:100]}...\n\n"
        return context
    
    def extract_stock_from_context(self) -> Optional[str]:
        """Get last mentioned stock from context"""
        if self.mentioned_stocks:
            return self.mentioned_stocks[-1]
        return None
    
    def remember_stock(self, ticker: str):
        """Remember mentioned stock"""
        if ticker and ticker not in self.mentioned_stocks[-3:]:  # Last 3
            self.mentioned_stocks.append(ticker)


class TechnicalAnalysis:
    """Provide technical analysis and indicators"""
    
    @staticmethod
    def analyze_trend(current_price: float, historical_data: List[float]) -> dict:
        """Simple trend analysis"""
        if not historical_data or len(historical_data) < 5:
            return {"trend": "NEUTRAL", "confidence": 0.5}
        
        recent_avg = sum(historical_data[-5:]) / 5
        older_avg = sum(historical_data[-10:-5]) / 5 if len(historical_data) >= 10 else recent_avg
        
        if recent_avg > older_avg * 1.05:
            return {"trend": "BULLISH", "confidence": 0.8, "strength": "Strong"}
        elif recent_avg < older_avg * 0.95:
            return {"trend": "BEARISH", "confidence": 0.8, "strength": "Strong"}
        else:
            return {"trend": "SIDEWAYS", "confidence": 0.6, "strength": "Moderate"}
    
    @staticmethod
    def support_resistance(historical_data: List[float]) -> dict:
        """Calculate support and resistance levels"""
        if not historical_data:
            return {"support": None, "resistance": None}
        
        support = min(historical_data[-20:]) if len(historical_data) >= 20 else min(historical_data)
        resistance = max(historical_data[-20:]) if len(historical_data) >= 20 else max(historical_data)
        
        return {
            "support": round(support, 2),
            "resistance": round(resistance, 2)
        }


class PersonalizedRecommendations:
    """Generate personalized recommendations based on user behavior"""
    
    def __init__(self):
        self.user_profiles = {}
    
    def analyze_user_behavior(self, user_id: str, watchlist: List[str], chat_history: List[dict]) -> dict:
        """Analyze user's interests and behavior"""
        profile = {
            "risk_tolerance": "MODERATE",
            "interests": [],
            "activity_level": "LOW",
            "learning_stage": "BEGINNER"
        }
        
        # Analyze watchlist
        if watchlist:
            if "BTC-USD" in watchlist or "TSLA" in watchlist:
                profile["risk_tolerance"] = "AGGRESSIVE"
            elif "GC=F" in watchlist:
                profile["risk_tolerance"] = "CONSERVATIVE"
            
            profile["interests"] = watchlist
        
        # Analyze chat frequency
        if len(chat_history) > 20:
            profile["activity_level"] = "HIGH"
            profile["learning_stage"] = "INTERMEDIATE"
        elif len(chat_history) > 50:
            profile["learning_stage"] = "ADVANCED"
        
        return profile
    
    def get_recommendations(self, profile: dict, current_stocks: List[str]) -> str:
        """Generate personalized recommendations"""
        recommendations = []
        
        # Based on risk tolerance
        if profile["risk_tolerance"] == "AGGRESSIVE":
            if "NVDA" not in current_stocks:
                recommendations.append("🚀 **NVIDIA (NVDA)**: Given your aggressive profile, NVIDIA's AI exposure could fit well.")
        elif profile["risk_tolerance"] == "CONSERVATIVE":
            if "GC=F" not in current_stocks:
                recommendations.append("🪙 **Gold**: As a conservative investor, gold can provide stability.")
        
        # Diversification suggestions
        sectors = {
            "AAPL": "Tech",
            "NVDA": "Semiconductors",
            "TSLA": "EVs",
            "GC=F": "Commodities",
            "BTC-USD": "Crypto"
        }
        
        user_sectors = [sectors.get(s) for s in current_stocks]
        missing_sectors = [s for s in sectors.values() if s not in user_sectors]
        
        if missing_sectors:
            recommendations.append(f"💡 **Diversification Tip**: You're missing exposure to {', '.join(missing_sectors[:2])}.")
        
        return "\n".join(recommendations) if recommendations else "Your portfolio looks well-balanced! 👍"


class EnhancedFinancialLLM:
    """
    Advanced AI Financial Assistant with:
    - Contextual memory
    - Intent classification
    - Technical analysis
    - Personalized recommendations
    - Interactive tutorials
    """
    
    def __init__(self):
        self.memory = ConversationMemory()
        self.intent_classifier = IntentClassifier()
        self.technical_analyzer = TechnicalAnalysis()
        self.recommender = PersonalizedRecommendations()
        self.financial_knowledge = self._load_financial_knowledge()
        self.user_sessions = {}  # user_id -> session data
        
    def _load_financial_knowledge(self):
        """Load comprehensive financial knowledge base"""
        return {
            "stock_advice": {
                "AAPL": {
                    "company": "Apple Inc.",
                    "sector": "Technology",
                    "advice": "Apple is known for its strong ecosystem, loyal customer base, and consistent innovation. The company has diversified revenue streams including iPhone, Services, and Wearables. Consider it as a stable long-term hold with growth potential.",
                    "risks": "High competition in smartphones, dependence on China manufacturing, regulatory scrutiny.",
                    "opportunity": "Growing services revenue, potential in AR/VR, expansion in financial services.",
                    "technical_indicators": {
                        "rsi": "Relative Strength Index shows momentum. RSI > 70 = overbought, < 30 = oversold",
                        "macd": "Moving Average Convergence Divergence identifies trend changes",
                        "bollinger": "Bollinger Bands show volatility. Price touching upper band = potential resistance"
                    }
                },
                "NVDA": {
                    "company": "NVIDIA Corporation",
                    "sector": "Semiconductors/AI",
                    "advice": "NVIDIA is the leader in AI chips and data center GPUs. With the AI boom, demand for their H100 and upcoming chips remains extremely high. Strong growth potential but watch for high valuation.",
                    "risks": "Cyclical semiconductor industry, competition from AMD and Intel, export restrictions to China.",
                    "opportunity": "AI infrastructure demand, autonomous vehicles, gaming growth, cloud partnerships.",
                    "technical_indicators": {
                        "rsi": "High momentum stock with frequent RSI > 70 readings during bull runs",
                        "macd": "Strong trending behavior, MACD crossovers signal good entry/exit points",
                        "volume": "Watch for volume spikes on earnings - indicates institutional activity"
                    }
                },
                "TSLA": {
                    "company": "Tesla Inc.",
                    "sector": "Electric Vehicles/Energy",
                    "advice": "Tesla pioneered mass-market EVs and has strong brand recognition. However, competition is intensifying from traditional automakers. High volatility makes it suitable for risk-tolerant investors.",
                    "risks": "Increasing EV competition, production challenges, CEO-related volatility, high valuation.",
                    "opportunity": "Energy storage growth, autonomous driving, expanding vehicle lineup, charging network.",
                    "technical_indicators": {
                        "volatility": "Very high volatility - use wider stop losses",
                        "news_driven": "Price heavily influenced by Elon tweets and news",
                        "patterns": "Forms clear chart patterns - good for technical traders"
                    }
                },
                "GC=F": {
                    "company": "Gold",
                    "sector": "Commodities",
                    "advice": "Gold is a traditional safe-haven asset and inflation hedge. It performs well during economic uncertainty and when real interest rates are low. Consider allocating 5-10% of portfolio for diversification.",
                    "risks": "No dividend income, storage costs for physical gold, vulnerable to rising interest rates.",
                    "opportunity": "Hedge against inflation, geopolitical uncertainty, central bank purchases, dollar weakness.",
                    "technical_indicators": {
                        "correlation": "Negative correlation with USD - dollar down, gold up",
                        "seasonality": "Historically strong in Q1 and wedding seasons",
                        "macro": "Watch Fed policy, inflation data, geopolitical tensions"
                    }
                },
                "BTC-USD": {
                    "company": "Bitcoin",
                    "sector": "Cryptocurrency",
                    "advice": "Bitcoin is the leading cryptocurrency with institutional adoption growing. However, it's highly volatile and speculative. Only invest what you can afford to lose completely. Consider as a small portfolio allocation (1-5%).",
                    "risks": "Extreme volatility, regulatory uncertainty, environmental concerns, security risks.",
                    "opportunity": "Digital gold narrative, institutional adoption, halving cycles, inflation hedge potential.",
                    "technical_indicators": {
                        "cycles": "4-year halving cycles - study historical patterns",
                        "whale_activity": "Monitor large wallet movements on-chain",
                        "dominance": "BTC dominance vs altcoins indicates market phase"
                    }
                }
            },
            "tutorials": {
                "beginner": {
                    "lesson_1": {
                        "title": "What is a Stock?",
                        "content": "A stock represents ownership in a company. When you buy Apple stock, you own a tiny piece of Apple! 📱\n\n**Key Points:**\n• Stocks can go up or down in value\n• You make money from price increases + dividends\n• Risk: Company could fail (rare for big companies)\n• Reward: Long-term wealth building",
                        "quiz": {
                            "question": "If you own 100 shares of a company with 1 million total shares, what percentage do you own?",
                            "options": ["A) 0.01%", "B) 0.1%", "C) 1%", "D) 10%"],
                            "answer": "A) 0.01%"
                        }
                    },
                    "lesson_2": {
                        "title": "Diversification Basics",
                        "content": "**Never put all eggs in one basket!** 🥚\n\n**Why Diversify?**\n• Reduces risk - if one stock crashes, others may stay strong\n• Smoother returns - less roller coaster\n• Sleep better at night!\n\n**How to Diversify:**\n1. Different sectors (Tech, Healthcare, Energy)\n2. Different sizes (Large-cap, Mid-cap, Small-cap)\n3. Different asset types (Stocks, Bonds, Commodities)",
                        "quiz": {
                            "question": "Which portfolio is better diversified?",
                            "options": ["A) 100% Tech stocks", "B) 60% Stocks, 30% Bonds, 10% Gold", "C) 100% One company"],
                            "answer": "B) 60% Stocks, 30% Bonds, 10% Gold"
                        }
                    },
                    "lesson_3": {
                        "title": "Risk vs Reward",
                        "content": "**Higher Risk = Higher Potential Reward** ⚖️\n\n**Risk Spectrum:**\n🟢 Low Risk: Bonds, Gold (stable, lower returns)\n🟡 Medium Risk: Blue-chip stocks like Apple (balanced)\n🔴 High Risk: Growth stocks, Crypto (volatile, higher potential)\n\n**Your Risk Tolerance depends on:**\n• Age (younger = can take more risk)\n• Time horizon (investing for 20+ years = more risk OK)\n• Financial situation (emergency fund saved?)\n• Sleep-at-night factor (can you handle 20% drops?)",
                        "quiz": {
                            "question": "You're 25 years old, investing for retirement at 65. Your best strategy?",
                            "options": ["A) 100% Bonds", "B) 80% Stocks, 20% Bonds", "C) 100% Cash"],
                            "answer": "B) 80% Stocks, 20% Bonds"
                        }
                    }
                },
                "intermediate": {
                    "lesson_1": {
                        "title": "Technical Indicators: RSI",
                        "content": "**RSI (Relative Strength Index)** measures momentum 📊\n\n**Scale:** 0 to 100\n• RSI > 70 = Overbought (might drop soon)\n• RSI < 30 = Oversold (might bounce)\n• RSI 50 = Neutral\n\n**Trading Strategy:**\n1. Wait for RSI < 30\n2. Confirm with other indicators\n3. Buy when RSI starts rising\n4. Sell when RSI > 70\n\n**Warning:** RSI can stay overbought/oversold during strong trends!",
                        "quiz": {
                            "question": "Stock has RSI of 25. What does this suggest?",
                            "options": ["A) Overbought, sell", "B) Oversold, might be buying opportunity", "C) Neutral"],
                            "answer": "B) Oversold, might be buying opportunity"
                        }
                    }
                }
            },
            "scenarios": {
                "market_crash": {
                    "description": "Market drops 20% in one month. What do you do?",
                    "options": {
                        "A": {"action": "Panic sell everything", "outcome": "❌ You locked in losses. Market recovered 30% over next year. You missed it!"},
                        "B": {"action": "Do nothing, hold", "outcome": "✅ Good! Portfolio recovered. But you missed buying opportunity."},
                        "C": {"action": "Buy more stocks", "outcome": "🎉 Excellent! You bought the dip. Portfolio up 40% in next year!"},
                        "D": {"action": "Sell stocks, buy bonds", "outcome": "🛡️ Safe move, but missed rebound. Returns only 5%."}
                    }
                },
                "hot_stock_tip": {
                    "description": "Friend says 'XYZ stock will 10x!' What do you do?",
                    "options": {
                        "A": {"action": "Invest immediately", "outcome": "❌ Stock was pump-and-dump. Lost 60%. Never trust hot tips!"},
                        "B": {"action": "Research first", "outcome": "✅ Smart! You found red flags and avoided scam."},
                        "C": {"action": "Invest 1% to test", "outcome": "⚠️ Limited downside, but still unnecessary risk."},
                        "D": {"action": "Ignore completely", "outcome": "✅ Perfect! Stick to your strategy."}
                    }
                }
            }
        }
    
    def generate_response(self, user_message: str, user_id: str, stock_data: dict = None, 
                         watchlist: List[str] = None, context: dict = None) -> dict:
        """
        Generate enhanced AI response with intent classification
        
        Returns: {
            "reply": str,
            "intent": str,
            "confidence": float,
            "stock_mentioned": str or None,
            "recommendations": str or None
        }
        """
        # ===== HIGHEST PRIORITY: NeuroSight App Usage Guide =====
        # Check BEFORE intent classification to prevent LLM from giving generic investment tutorials
        msg_lower = user_message.lower()
        
        # === Stock Comparison Menu ===
        if any(phrase in msg_lower for phrase in [
            "i want to compare stocks", "compare stocks", "stock comparison", 
            "compare different stocks", "which stocks to compare"
        ]):
            response = """📊 **Stock Comparison & Prediction Center**

Choose the stocks you'd like to compare:

**🍎 Apple vs Others:**
• Apple vs Tesla - *Tech innovation vs EV revolution*
• Apple vs NVIDIA - *Consumer tech vs AI semiconductors*
• Apple vs Gold - *Growth stock vs safe haven*

**⚡ Tesla vs Others:**
• Tesla vs Apple - *EV leader vs tech giant*
• Tesla vs NVIDIA - *Automotive AI vs chip maker*
• Tesla vs Gold - *High growth vs stability*

**🚀 NVIDIA vs Others:**
• NVIDIA vs Apple - *AI chips vs consumer devices*
• NVIDIA vs Tesla - *Silicon power vs electric power*
• NVIDIA vs Gold - *Tech growth vs precious metals*

**🪙 Gold vs Tech Stocks:**
• Gold vs Apple - *Traditional safety vs modern growth*
• Gold vs Tesla - *Stability vs volatility*
• Gold vs NVIDIA - *Safe haven vs AI boom*

**💡 How to use:** Just tell me which comparison you want! For example:
• "Compare Apple vs Tesla"
• "NVIDIA versus Gold analysis"
• "Should I invest in Apple or NVIDIA?"

Which comparison would you like to see? 📈"""
            
            return {
                "reply": response,
                "intent": "STOCK_COMPARISON_MENU",
                "confidence": 1.0,
                "stock_mentioned": None,
                "recommendations": None
            }
        
        # === Portfolio Builder ===
        if any(phrase in msg_lower for phrase in [
            "help me build a portfolio", "build a diversified portfolio", 
            "portfolio builder", "create portfolio", "diversify my investments"
        ]):
            response = """📊 **NeuroSight Portfolio Builder**

Let's build a smart, diversified portfolio based on your goals!

**📋 Recommended Portfolio Allocations:**

**🟢 Conservative (Low Risk)**
• 60% Gold - Stability & inflation hedge
• 25% Apple - Established tech with dividends
• 10% NVIDIA - Moderate growth exposure
• 5% Tesla - Small high-growth allocation

**🟡 Balanced (Medium Risk)**
• 35% Apple - Core tech holdings
• 25% NVIDIA - AI growth potential
• 20% Gold - Safety buffer
• 15% Tesla - Growth component
• 5% Cash - Emergency liquidity

**🔴 Aggressive (High Risk)**
• 40% NVIDIA - AI boom leader
• 30% Tesla - High growth EV sector
• 20% Apple - Stable tech base
• 10% Gold - Minor hedge

**💡 Key Principles:**
✅ Never put all eggs in one basket
✅ Balance growth stocks with stable assets
✅ Consider your risk tolerance
✅ Rebalance quarterly
✅ Keep 3-6 months emergency fund

**🎯 Next Steps:**
1. Tell me your risk tolerance (conservative/balanced/aggressive)
2. Mention your investment timeline (1 year / 5 years / 10+ years)
3. I'll customize a portfolio just for you!

What's your preferred risk level? 📊"""
            
            return {
                "reply": response,
                "intent": "PORTFOLIO_BUILDER",
                "confidence": 1.0,
                "stock_mentioned": None,
                "recommendations": None
            }
        
        # === Market Insights ===
        if any(phrase in msg_lower for phrase in [
            "show me market insights", "market trends", "market insights",
            "latest market news", "what's happening in the market"
        ]):
            response = """📈 **NeuroSight Market Insights**

**🔥 Current Market Trends:**

**AI Revolution 🤖**
• NVIDIA leading the AI chip boom
• Strong demand for GPUs in data centers
• AI adoption accelerating across industries

**Electric Vehicles ⚡**
• Tesla dominating EV market share
• Competition intensifying from traditional automakers
• Battery technology advancing rapidly

**Tech Giants 🖥️**
• Apple: Strong iPhone sales, services revenue growing
• Focus on AI integration (Apple Intelligence)
• Stable cash flow and dividend growth

**Safe Haven Assets 🛡️**
• Gold: Traditional inflation hedge
• Central bank policies affecting precious metals
• Uncertainty driving safe haven demand

**📊 Sector Performance:**
• Technology: Strong growth, AI-driven momentum
• Commodities: Gold holding steady amid uncertainty
• EVs: High volatility, innovation-driven

**💡 Key Takeaways:**
✅ Diversification remains crucial
✅ AI sector showing exceptional growth
✅ Balance high-growth with stable assets
✅ Monitor Fed interest rate decisions
✅ Long-term investing beats market timing

**🎯 Actionable Insights:**
• Consider AI exposure through NVIDIA
• Apple offers stability + growth
• Gold provides portfolio insurance
• Tesla for aggressive growth allocation

Want details on any specific asset? Just ask! 🚀"""
            
            return {
                "reply": response,
                "intent": "MARKET_INSIGHTS",
                "confidence": 1.0,
                "stock_mentioned": None,
                "recommendations": None
            }
        
        # === NeuroSight App Guide ===
        if any(phrase in msg_lower for phrase in [
            "how do i invest using neurosight", "how to invest using neurosight",
            "invest using neurosight", "use neurosight", "how to use this app", 
            "how does this app work", "how to use neurosight", "invest in neurosight", 
            "use this app", "neurosight guide", "app guide", "how can i invest using neurosight",
            "start beginner investment tutorial", "beginner guide", "beginner investment",
            "how to start", "getting started", "beginner tutorial", "start tutorial"
        ]):
            response = """🎯 **Welcome to NeuroSight!** Here's how to use the app for smart investments:

**Step 1️⃣: Go to Dashboard**
Navigate to your main dashboard where you'll see all available assets.

**Step 2️⃣: Select Your Asset**
Choose from Apple, NVIDIA, Tesla, Gold, or Bitcoin based on your interest.

**Step 3️⃣: View AI Predictions**
Our advanced AI models provide price predictions with confidence scores.

**Step 4️⃣: Analyze the Data**
Review historical trends, technical indicators, and market sentiment analysis.

**Step 5️⃣: Make Informed Decisions**
Use the insights to guide your investment strategy. Remember: predictions are tools, not guarantees!

**💡 Pro Tips**:
• Compare multiple assets before deciding
• Check prediction confidence levels
• Review historical accuracy metrics
• Consider your risk tolerance
• Don't invest more than you can afford to lose

Ready to start? Head to the Dashboard and explore! 🚀

_Have questions about a specific stock? Just ask me!_"""
            
            return {
                "reply": response,
                "intent": "NEUROSIGHT_APP_GUIDE",
                "confidence": 1.0,
                "stock_mentioned": None,
                "recommendations": None
            }
        
        # Classify intent
        intent, confidence = self.intent_classifier.classify(user_message)
        
        # Get or create user session
        if user_id not in self.user_sessions:
            self.user_sessions[user_id] = {
                "memory": ConversationMemory(),
                "profile": {},
                "last_active": datetime.now()
            }
        
        session = self.user_sessions[user_id]
        memory = session["memory"]
        
        # Route to specialized handler
        handler_map = {
            "GREETING": self._handle_greeting,
            "PRICE_QUERY": self._handle_price_query,
            "ADVICE": self._handle_advice,
            "EXPLANATION": self._handle_explanation,
            "TUTORIAL": self._handle_tutorial,
            "COMPARISON": self._handle_comparison,
            "STRATEGY": self._handle_strategy,
            "RISK": self._handle_risk,
            "PREDICTION": self._handle_prediction,
            "NEWS": self._handle_news,
            "PORTFOLIO": self._handle_portfolio,
        }
        
        handler = handler_map.get(intent, self._handle_general)
        response = handler(user_message, stock_data, memory, context)
        
        # Extract stock mentioned
        stock_mentioned = self._extract_stock(user_message, memory)
        if stock_mentioned:
            memory.remember_stock(stock_mentioned)
        
        # Generate personalized recommendations
        recommendations = None
        if watchlist and len(memory.history) > 5:  # After user has chatted a bit
            profile = self.recommender.analyze_user_behavior(user_id, watchlist, memory.history)
            recommendations = self.recommender.get_recommendations(profile, watchlist)
        
        # Add to memory
        memory.add_exchange(user_message, response, {"intent": intent, "confidence": confidence})
        
        return {
            "reply": response,
            "intent": intent,
            "confidence": confidence,
            "stock_mentioned": stock_mentioned,
            "recommendations": recommendations
        }
    
    def _handle_price_query(self, message: str, stock_data: dict, memory: ConversationMemory, context: dict) -> str:
        """Handle price queries with real-time data"""
        stock_ticker = self._extract_stock(message, memory)
        
        if not stock_ticker:
            return """I can check current prices for:

• **Apple (AAPL)** - "What's Apple's price?"
• **NVIDIA (NVDA)** - "NVDA current price?"
• **Tesla (TSLA)** - "Tesla stock price?"
• **Microsoft (MSFT)** - "Microsoft price?"
• **Gold (GC=F)** - "Gold price today?"
• **Bitcoin (BTC-USD)** - "Bitcoin price?"

Which stock would you like to check?"""
        
        if not stock_data or not stock_data.get('price'):
            return f"""I couldn't fetch current data for **{stock_ticker}**.

Please try again or ask about:
• Apple (AAPL)
• NVIDIA (NVDA)
• Tesla (TSLA)
• Gold (GC=F)
• Bitcoin (BTC-USD)"""
        
        # Format the comprehensive price response
        company_names = {
            "AAPL": "Apple Inc.",
            "NVDA": "NVIDIA Corporation",
            "TSLA": "Tesla Inc.",
            "MSFT": "Microsoft Corporation",
            "GOOGL": "Alphabet Inc.",
            "AMZN": "Amazon.com Inc.",
            "META": "Meta Platforms Inc.",
            "AMD": "Advanced Micro Devices",
            "GC=F": "Gold Futures",
            "BTC-USD": "Bitcoin"
        }
        
        company_name = company_names.get(stock_ticker, stock_ticker)
        price = stock_data.get('price', 'N/A')
        change = stock_data.get('change', 0)
        change_percent = stock_data.get('change_percent', 0)
        day_high = stock_data.get('day_high', 'N/A')
        day_low = stock_data.get('day_low', 'N/A')
        volume = stock_data.get('volume', 'N/A')
        market_cap = stock_data.get('market_cap', 'N/A')
        
        # Format volume and market cap
        if isinstance(volume, (int, float)) and volume != 'N/A':
            if volume >= 1_000_000:
                volume_str = f"{volume / 1_000_000:.2f}M"
            else:
                volume_str = f"{volume:,}"
        else:
            volume_str = str(volume)
        
        if isinstance(market_cap, (int, float)) and market_cap != 'N/A':
            if market_cap >= 1_000_000_000_000:
                market_cap_str = f"${market_cap / 1_000_000_000_000:.2f}T"
            elif market_cap >= 1_000_000_000:
                market_cap_str = f"${market_cap / 1_000_000_000:.2f}B"
            else:
                market_cap_str = f"${market_cap / 1_000_000:.2f}M"
        else:
            market_cap_str = str(market_cap)
        
        # Determine trend emoji
        if change > 0:
            trend_emoji = "📈"
            change_color = "🟢"
        elif change < 0:
            trend_emoji = "📉"
            change_color = "🔴"
        else:
            trend_emoji = "->"
            change_color = "📈"
        
        response = f"""## {trend_emoji} **{company_name} ({stock_ticker})**

**Current Price:** ${price:.2f}
**Change:** {change_color} ${change:+.2f} ({change_percent:+.2f}%)

**Today's Range:**
• High: ${day_high:.2f}
• Low: ${day_low:.2f}

**Trading Volume:** {volume_str}
**Market Cap:** {market_cap_str}

**Quick Analysis:**
"""
        
        # Add contextual insights based on the stock
        if stock_ticker == "AAPL":
            response += """Apple remains a stable tech giant with strong ecosystem. Good for long-term holdings.

**Next:** Want detailed investment advice? Ask "Should I invest in Apple?"""
        elif stock_ticker == "NVDA":
            response += """NVIDIA is leading the AI chip revolution. High growth potential but watch valuations.

**Next:** Ask "Should I invest in NVIDIA?" for full analysis."""
        elif stock_ticker == "TSLA":
            response += """Tesla pioneered mass-market EVs but faces increasing competition. High volatility.

**Next:** Ask "Should I invest in Tesla?" for risk assessment."""
        elif stock_ticker == "GC=F":
            response += """Gold is a traditional safe-haven asset and inflation hedge. Consider 5-10% allocation.

**Next:** Ask "Should I invest in gold?" for portfolio strategies."""
        elif stock_ticker == "BTC-USD":
            response += """Bitcoin is highly volatile. Only invest what you can afford to lose (1-5% allocation max).

**Next:** Ask "Should I invest in Bitcoin?" for risk analysis."""
        else:
            response += f"""For detailed investment analysis, ask: "Should I invest in {stock_ticker}?" """
        
        return response
    
    def _handle_greeting(self, message: str, stock_data: dict, memory: ConversationMemory, context: dict) -> str:
        """Handle greetings with context awareness"""
        exchange_count = len(memory.history)
        
        if exchange_count == 0:
            return """Hello! 👋 I'm your **NeuroSight AI Financial Advisor**.

I'm here to help you:
📊 Get real-time stock prices
💡 Understand investment strategies
📖 Learn financial concepts
📈 Analyze market trends
🤖 Make smarter investment decisions

**Try saying:**
• "Explain diversification"
• "Should I invest in Apple?"
• "Start beginner tutorial"
• "Compare NVIDIA vs Tesla"

What would you like to explore?"""
        else:
            return f"""Welcome back! 👋

We've had **{exchange_count // 2} conversations** so far. Ready to continue your financial journey?

**Quick picks:**
• Check latest stock prices
• Continue learning with tutorials
• Get personalized recommendations

What's on your mind today?"""
    
    def _handle_advice(self, message: str, stock_data: dict, memory: ConversationMemory, context: dict) -> str:
        """Handle investment advice requests with technical analysis"""
        msg_lower = message.lower()
        stock_ticker = self._extract_stock(message, memory)
        
        # Handle broad investment questions
        if "tech stock" in msg_lower or ("invest" in msg_lower and "technology" in msg_lower):
            return """## 📊 **Should You Invest in Tech Stocks?**

**Tech Sector Overview:**
Technology stocks have historically outperformed the market, delivering ~15-20% annual returns over the past decade.

**✅ Reasons to Invest in Tech:**
1. **Innovation Leaders** - AI, cloud computing, automation
2. **High Growth Potential** - Expanding markets
3. **Strong Margins** - Software has 80%+ gross margins
4. **Network Effects** - Winner-takes-most dynamics
5. **Digital Transformation** - Every company needs tech

**⚠️ Risks to Consider:**
1. **High Valuations** - P/E ratios often 30-50+
2. **Volatility** - Tech can drop 30-40% in downturns
3. **Concentration Risk** - 5 stocks dominate (FAANG)
4. **Regulatory Pressure** - Antitrust concerns
5. **Interest Rate Sensitivity** - Tech suffers when rates rise

**🎯 My Recommendation:**

**For Beginners:**
• Start with tech ETF (QQQ - Nasdaq 100) - 10-15% allocation
• Add individual stocks gradually
• Diversify across tech sectors

**Best Tech Stocks to Consider:**
1. **Apple (AAPL)** - Stable, profitable, ecosystem 🍎
2. **NVIDIA (NVDA)** - AI leader, high growth 🚀
3. **Microsoft (MSFT)** - Cloud + AI + software 💻
4. **Amazon (AMZN)** - E-commerce + AWS cloud ☁️

**Portfolio Allocation:**
• **Aggressive (30-40% tech)**
  - 15% QQQ ETF
  - 10% Apple
  - 10% NVIDIA
  - 5% Microsoft

• **Moderate (20-25% tech)**
  - 10% QQQ ETF
  - 10% Apple/Microsoft mix
  - 5% Individual picks

• **Conservative (10-15% tech)**
  - 10% QQQ ETF only
  - 5% Apple (safest tech stock)

**🎯 Key Strategy:**
• Dollar-cost average (invest monthly)
• Hold for 5+ years minimum
• Rebalance quarterly if tech grows too large
• Keep position size under 40% of total portfolio

**Current Market (2026):**
Tech is strong due to AI boom, but valuations are elevated. Good time to start dollar-cost averaging rather than lump sum.

**Next Steps:**
Want specific analysis on Apple, NVIDIA, or Microsoft? Just ask!"""
        
        if not stock_ticker or stock_ticker not in self.financial_knowledge["stock_advice"]:
            return """I can provide detailed advice on:
• **Apple (AAPL)** - Tech giant
• **NVIDIA (NVDA)** - AI leader
• **Tesla (TSLA)** - EV pioneer
• **Gold (GC=F)** - Safe haven
• **Bitcoin (BTC-USD)** - Digital currency

Or ask broader questions like:
• "Should I invest in tech stocks?"
• "What about dividend stocks?"
• "Are growth stocks risky?"

What interests you?"""
        
        advice_data = self.financial_knowledge["stock_advice"][stock_ticker]
        
        response = f"""## 📊 Investment Analysis: **{advice_data['company']}**

**📊 Sector:** {advice_data['sector']}

**💡 Investment Thesis:**
{advice_data['advice']}

**📈 Technical Insights:**
"""
        
        # Add technical indicators
        for indicator, explanation in advice_data.get("technical_indicators", {}).items():
            response += f"• **{indicator.upper()}**: {explanation}\n"
        
        response += f"""
**⚠️ Risk Factors:**
{advice_data['risks']}

**🚀 Growth Catalysts:**
{advice_data['opportunity']}

**My Recommendation:**
"""
        
        # Context-aware recommendation
        if "aggressive" in message.lower() or "growth" in message.lower():
            response += f"{stock_ticker} fits an aggressive growth strategy. Consider 5-10% portfolio allocation."
        elif "conservative" in message.lower() or "safe" in message.lower():
            if stock_ticker in ["AAPL", "GC=F"]:
                response += f"{stock_ticker} is suitable for conservative portfolios with 10-15% allocation."
            else:
                response += f"{stock_ticker} is higher risk. Consider Apple or Gold for conservative approach."
        else:
            response += f"Suitable for moderate portfolios. Aim for 5-10% allocation. Diversify across sectors."
        
        if stock_data:
            response += f"\n\n**Current Price:** ${stock_data.get('price', 'N/A')}"
            response += f" | **Change:** {stock_data.get('change', 'N/A')}%"
        
        response += "\n\n⚠️ *This is educational analysis, not financial advice. Always do your own research.*"
        
        return response
    
    def _handle_explanation(self, message: str, stock_data: dict, memory: ConversationMemory, context: dict) -> str:
        """Handle explanation requests with examples"""
        msg_lower = message.lower()
        
        # Normalize the message for better matching
        msg_normalized = msg_lower.replace("/", " ").replace("-", " ").replace("_", " ")
        
        concepts = {
            "diversification": """## 🌈 Diversification Explained

**Simple Analogy:** Don't carry all your eggs in one basket! 🥚

**What is it?**
Spreading your investments across different assets to reduce risk.

**Why it works:**
• If Tech crashes, Healthcare might stay strong
• Different assets behave differently
• Reduces overall portfolio volatility

**How to diversify:**

**By Sector:**
✅ 30% Technology (Apple, NVIDIA)
✅ 20% Healthcare (Pfizer, J&J)
✅ 15% Finance (JPMorgan, Goldman)
✅ 10% Energy (Chevron, Exxon)
✅ 10% Commodities (Gold)
✅ 10% Crypto (Bitcoin)
✅ 5% Cash

**By Risk Level:**
• 60% Stable blue-chips
• 30% Growth stocks
• 10% Speculative (crypto, small-caps)

**Real Example:**
2022: Tech stocks dropped 30%, but Gold gained 5%. Diversified portfolios lost only 10% instead of 30%!

**Pro Tip:** Rebalance quarterly. If one sector grows too large, trim it and buy underperformers.""",
            
            "pe ratio": """## 🔢 P/E Ratio (Price-to-Earnings) Explained

**Formula:** Stock Price ÷ Earnings Per Share

**Example:**
• Apple stock = $180
• Apple earnings = $6 per share
• P/E Ratio = 180 ÷ 6 = **30**

**What does P/E = 30 mean?**
You're paying $30 for every $1 of earnings. It will take 30 years to "earn back" your investment at current earnings.

**Interpreting P/E:**

**Low P/E (5-15):**
✅ Potentially undervalued
✅ "Cheap" stock
❌ Maybe company is struggling
❌ Low growth expected

**Medium P/E (15-25):**
✅ Fair valuation
✅ Steady company
✅ Market average

**High P/E (25+):**
✅ High growth expected
❌ "Expensive" stock
❌ Risk of disappointment

**Sector Comparison Matters:**
• Tech average P/E: 25-30 (growth expected)
• Banks average P/E: 10-15 (slower growth)
• Comparing Apple (P/E 30) to Nvidia (P/E 40) is fair
• Comparing Apple to JPMorgan is NOT fair (different sectors)

**Real World Example:**
Tesla P/E = 80 (very expensive, betting on huge future growth)
Ford P/E = 6 (cheap, mature company)

Tesla must grow earnings dramatically to justify its price!""",
            
            "dollar cost averaging": """## 💰 Dollar-Cost Averaging (DCA) Strategy

**What is it?**
Investing a FIXED amount regularly, regardless of price.

**Example:**
Invest $100 every Monday into Apple stock, no matter if it's up or down.

**How it works:**

**Month 1:** Apple = $100/share → Buy 1 share
**Month 2:** Apple = $80/share → Buy 1.25 shares (it's cheaper!)
**Month 3:** Apple = $120/share → Buy 0.83 shares
**Month 4:** Apple = $90/share → Buy 1.11 shares

**Total invested:** $400
**Total shares:** 4.19 shares
**Average cost:** $95.47 per share

**If you bought all at once in Month 1:**
• You'd only have 4 shares at $100 each

**Benefits:**
✅ Removes emotion from investing
✅ Buys more when prices are low
✅ Reduces timing risk
✅ Great for beginners
✅ Automate and forget!

**Best for:**
• Long-term investors (5+ years)
• Volatile stocks
• Index funds
• Monthly salary allocation

**Set it up:**
1. Choose investment amount (e.g., $200/month)
2. Pick asset (Apple, S&P 500, Bitcoin)
3. Set automatic purchase schedule
4. Ignore daily prices!

**Real Data:**
Someone DCA'ing $100/month into S&P 500 from 2010-2020 turned $12,000 into $25,000+!"""
        }
        
        # Check for keyword matches with better normalization
        for keyword, explanation in concepts.items():
            keyword_normalized = keyword.replace("/", " ").replace("-", " ")
            if keyword_normalized in msg_normalized or keyword in msg_lower:
                return explanation
        
        # Check for common variations
        if "p e ratio" in msg_normalized or "pe ratio" in msg_normalized or "price to earnings" in msg_lower:
            return concepts["pe ratio"]
        
        if "dollar cost" in msg_lower or "dca" in msg_lower:
            return concepts["dollar cost averaging"]
        
        return """I can explain these financial concepts in detail:

**Basics:**
• **Diversification** - Risk management strategy
• **P/E Ratio** - Stock valuation metric
• **Dollar-Cost Averaging** - Smart investing technique
• **Market Cap** - Company size classification
• **Dividends** - Regular shareholder payments

**Advanced:**
• **RSI** - Momentum indicator
• **MACD** - Trend following tool
• **Bollinger Bands** - Volatility measure
• **Support & Resistance** - Price levels

**Strategies:**
• **Value Investing** - Buy undervalued stocks
• **Growth Investing** - High potential companies
• **Index Investing** - Match market returns

Which would you like me to explain?"""
    
    def _handle_tutorial(self, message: str, stock_data: dict, memory: ConversationMemory, context: dict) -> str:
        """Interactive tutorial system"""
        msg_lower = message.lower()
        
        if "beginner" in msg_lower or "start" in msg_lower or "lesson 1" in msg_lower:
            lesson = self.financial_knowledge["tutorials"]["beginner"]["lesson_1"]
            return f"""## 📖 {lesson['title']}

{lesson['content']}

**🧠 Quick Quiz:**
{lesson['quiz']['question']}

{chr(10).join(lesson['quiz']['options'])}

Reply with your answer (A, B, C, or D) to check your understanding!

**Next:** Say "Lesson 2" to continue your learning journey."""
        
        elif "lesson 2" in msg_lower:
            lesson = self.financial_knowledge["tutorials"]["beginner"]["lesson_2"]
            return f"""## 📖 {lesson['title']}

{lesson['content']}

**🧠 Quick Quiz:**
{lesson['quiz']['question']}

{chr(10).join(lesson['quiz']['options'])}

**Next:** Say "Lesson 3" for more!"""
        
        elif "lesson 3" in msg_lower:
            lesson = self.financial_knowledge["tutorials"]["beginner"]["lesson_3"]
            return f"""## 📖 {lesson['title']}

{lesson['content']}

**🧠 Quick Quiz:**
{lesson['quiz']['question']}

{chr(10).join(lesson['quiz']['options'])}

**Congratulations!** 🎉 You've completed the beginner series!

**Next steps:**
• Say "Intermediate tutorial" for advanced lessons
• Ask about specific stocks
• Try "What-if scenarios"""
        
        elif "intermediate" in msg_lower:
            lesson = self.financial_knowledge["tutorials"]["intermediate"]["lesson_1"]
            return f"""## 📖 {lesson['title']} (Intermediate Level)

{lesson['content']}

**🧠 Quick Quiz:**
{lesson['quiz']['question']}

{chr(10).join(lesson['quiz']['options'])}

**Pro Tip:** Practice with real charts on TradingView.com!"""
        
        else:
            return """## 🎓 **NeuroSight Financial Academy**

**📚 Available Tutorials:**

**Beginner Series:**
1. What is a Stock?
2. Diversification Basics
3. Risk vs Reward

**Intermediate Series:**
1. Technical Indicators (RSI)
2. Reading Chart Patterns (Coming soon)
3. Portfolio Management (Coming soon)

**Interactive Features:**
• Quiz questions after each lesson
• Real-world scenarios
• Personalized learning path

**Start learning:** Say "Start beginner tutorial" or "Lesson 1"

**Your progress will be tracked!** 📊"""
    
    def _handle_comparison(self, message: str, stock_data: dict, memory: ConversationMemory, context: dict) -> str:
        """Enhanced comparison with metrics"""
        msg_lower = message.lower()
        
        comparisons = {
            ("apple", "nvidia"): """## 🍎 Apple vs NVIDIA Comparison

| Metric | 🍎 Apple (AAPL) | 🚀 NVIDIA (NVDA) |
|--------|----------------|------------------|
| **Sector** | Consumer Tech | Semiconductors/AI |
| **Market Cap** | $3.0T | $1.2T |
| **Volatility** | Low-Moderate | High |
| **Dividend** | Yes (~0.5%) | Yes (small, 0.1%) |
| **Growth Rate** | Moderate (8-12%) | High (20-40%) |
| **Risk Level** | 🟢 Medium | 🟠 Medium-High |
| **P/E Ratio** | ~30 | ~60 |

**🍎 Apple Strengths:**
✅ Diverse revenue streams
✅ Loyal customer base
✅ Strong cash flow
✅ Consistent dividends
✅ Less volatile

**🚀 NVIDIA Strengths:**
✅ AI boom leader
✅ Data center dominance
✅ Gaming stronghold
✅ Higher growth potential
✅ Technology moat

**Who wins?**
• **Safety & Income:** Apple
• **Growth Potential:** NVIDIA
• **Volatility Tolerance:** NVIDIA requires more
• **Ideal:** Own BOTH! (20% Apple, 10% NVIDIA)

**Verdict:** Apple for core holdings, NVIDIA for growth allocation.""",
            
            ("tesla", "apple"): """## ⚔️ Tesla vs Apple Comparison

| Metric | ⚡ Tesla (TSLA) | 🍎 Apple (AAPL) |
|--------|----------------|----------------|
| **Industry** | EVs/Energy | Consumer Tech |
| **Founded** | 2003 | 1976 |
| **Volatility** | Very High | Moderate |
| **Profitability** | Growing | Highly profitable |
| **CEO Factor** | High (Musk) | Stable team |
| **Risk** | 🔴 High | 🟡 Medium |

**⚡ Tesla Characteristics:**
✅ Innovation leader
✅ Brand strength
✅ Energy business
❌ High competition
❌ Execution risk
❌ CEO volatility

**🍎 Apple Characteristics:**
✅ Proven business model
✅ Predictable growth
✅ Strong moat
✅ Better margins
❌ Slower growth
❌ China dependence

**Investment Profile:**
• **Tesla:** For aggressive investors, 5% max allocation
• **Apple:** For balanced investors, 10-15% allocation
• **Can own both:** Yes, for diversification

**Recommendation:** Apple is safer, Tesla is higher risk/reward.""",
            
            ("nvidia", "tesla"): """## ⚔️ NVIDIA vs Tesla Comparison

| Metric | 🚀 NVIDIA (NVDA) | ⚡ Tesla (TSLA) |
|--------|------------------|----------------|
| **Sector** | AI/Semiconductors | EVs/Energy |
| **Market Cap** | $1.2T | $800B |
| **Volatility** | High | Very High |
| **Dividend** | Yes (0.1%) | No |
| **Growth Rate** | Very High (30-40%) | High (15-25%) |
| **Risk Level** | 🟠 Medium-High | 🔴 High |
| **P/E Ratio** | ~60 | ~80 |
| **Profit Margin** | 50%+ | 15-20% |

**🚀 NVIDIA Strengths:**
✅ AI boom beneficiary
✅ Data center dominance (80% market share)
✅ Strong profit margins (50%+)
✅ Gaming + Professional visualization
✅ Software moat (CUDA ecosystem)
✅ Diversified revenue streams

**⚡ Tesla Strengths:**
✅ EV market leader
✅ Vertical integration
✅ Energy storage business
✅ Autonomous driving potential
✅ Brand recognition
✅ Manufacturing innovation

**Key Differences:**
• **Profitability:** NVIDIA much higher margins
• **Competition:** Tesla faces more competition (Ford, GM, BYD)
• **CEO:** Both have visionary leaders (Jensen vs Musk)
• **Stability:** NVIDIA more predictable business
• **News Sensitivity:** Tesla more affected by Elon's actions

**Investment Outlook:**
• **NVIDIA:** Riding AI wave, strong fundamentals 📈
• **Tesla:** Higher risk, depends on FSD & energy business ⚡

**Portfolio Recommendation:**
• **Aggressive:** 10% NVIDIA, 5% Tesla
• **Moderate:** 5% NVIDIA, 3% Tesla
• **Conservative:** 3% NVIDIA, 0% Tesla

**Verdict:** NVIDIA is the safer bet with stronger fundamentals. Tesla offers higher risk/reward but more uncertainty.""",
            
            ("apple", "gold"): """## 🍎 Apple vs Gold Comparison

| Metric | 🍎 Apple (AAPL) | 🪙 Gold (GC=F) |
|--------|----------------|----------------|
| **Asset Type** | Growth Stock | Commodity/Safe Haven |
| **Volatility** | Moderate (±25%) | Low (±12%) |
| **Dividend** | Yes (~0.5%) | No |
| **Growth Rate** | Moderate (10-15%) | Low (2-5%) |
| **Risk Level** | 🟡 Medium | 🟢 Low |
| **Inflation Hedge** | Moderate | Excellent |
| **Liquidity** | Very High | High |

**🍎 Apple Strengths:**
✅ Revenue growth potential
✅ Innovation & product ecosystem
✅ Dividend payments
✅ Strong balance sheet
✅ Tech sector exposure

**🪙 Gold Strengths:**
✅ Safe haven during crises
✅ Inflation protection
✅ Portfolio diversifier
✅ 5,000+ year track record
✅ Low correlation to stocks

**Investment Purpose:**
• **Apple:** Wealth building, growth
• **Gold:** Wealth preservation, insurance

**Portfolio Allocation:**
• **Growth Portfolio:** 15% Apple, 5% Gold
• **Balanced Portfolio:** 10% Apple, 10% Gold
• **Conservative Portfolio:** 5% Apple, 15% Gold

**Verdict:** Apple for growth, Gold for protection. Own both for balance!""",
            
            ("tesla", "gold"): """## ⚔️ Tesla vs Gold Comparison

| Metric | ⚡ Tesla (TSLA) | 🪙 Gold (GC=F) |
|--------|----------------|----------------|
| **Asset Type** | High-Growth Stock | Commodity/Store of Value |
| **Volatility** | Very High (±70%) | Low (±12%) |
| **Dividend** | No | No |
| **Growth Rate** | High (20-40%) | Low (2-5%) |
| **Risk Level** | 🔴 Very High | 🟢 Low |
| **Time Horizon** | 5-10+ years | Any |

**⚡ Tesla - High Risk, High Reward:**
✅ EV market leader
✅ Massive growth potential
✅ Innovation-driven
❌ Extremely volatile
❌ CEO risk (Musk factor)
❌ Can drop 30-50% in months

**🪙 Gold - Stability & Insurance:**
✅ Minimal volatility
✅ Crisis protection
✅ 5,000 year value retention
❌ No dividends or cash flow
❌ Limited growth potential
❌ Storage costs

**Historical Comparison (2020-2024):**
• Tesla: +500% (but -65% in 2022 alone!)
• Gold: +35% (steady, boring growth)

**Investment Philosophy:**
• **Tesla:** "Get rich" speculation
• **Gold:** "Stay rich" preservation

**Recommended Split:**
• **Aggressive:** 10% Tesla, 5% Gold
• **Moderate:** 3% Tesla, 10% Gold
• **Conservative:** 0% Tesla, 15-20% Gold

**Verdict:** Complete opposites! Tesla for aggressive growth, Gold for sleeping well at night.""",
            
            ("nvidia", "gold"): """## ⚔️ NVIDIA vs Gold Comparison

| Metric | 🚀 NVIDIA (NVDA) | 🪙 Gold (GC=F) |
|--------|------------------|----------------|
| **Asset Type** | AI/Tech Growth Stock | Precious Metal |
| **Volatility** | High (±50%) | Low (±12%) |
| **Dividend** | Yes (0.1%) | No |
| **Growth Rate** | Very High (30-50%) | Low (2-5%) |
| **Risk Level** | 🟠 Medium-High | 🟢 Low |
| **Economic Cycle** | Benefits from boom | Benefits from crisis |

**🚀 NVIDIA - AI Revolution:**
✅ Leading AI chip maker (80% market share)
✅ Data center boom
✅ 50%+ profit margins
✅ Software moat (CUDA)
✅ Gaming + Professional markets
❌ High P/E ratio (expensive)
❌ Tech sector correlation
❌ Competition risk (AMD, Intel)

**🪙 Gold - Timeless Value:**
✅ Ultimate safe haven
✅ Inflation hedge
✅ Central bank reserves
✅ Jewelry & industrial demand
✅ No bankruptcy risk
❌ No income generation
❌ Storage & insurance costs
❌ Opportunity cost in bull markets

**Performance Context:**
• **NVIDIA (2023):** +239% (AI boom!)
• **Gold (2023):** +13% (steady)
• **NVIDIA (2022):** -50% (tech crash)
• **Gold (2022):** -1% (stable)

**When Each Wins:**
• **NVIDIA:** Economic growth, AI adoption, tech bull markets
• **Gold:** Recessions, inflation spikes, market crashes, war

**Portfolio Strategy:**
• **Tech Bull:** 15% NVIDIA, 5% Gold
• **Balanced:** 8% NVIDIA, 12% Gold
• **Defensive:** 3% NVIDIA, 20% Gold

**Verdict:** NVIDIA = offense, Gold = defense. Perfect hedge pair!"""
        }
        
        # Check which comparison user wants
        for (stock1, stock2), comparison_text in comparisons.items():
            if stock1 in msg_lower and stock2 in msg_lower:
                return comparison_text
            # Also check reverse order
            if stock2 in msg_lower and stock1 in msg_lower:
                return comparison_text
        
        return """I can provide detailed comparisons between:

**Stock vs Stock:**
• Apple vs NVIDIA
• Tesla vs Apple
• NVIDIA vs Teslale** - "Compare Tesla vs Apple"
• **NVIDIA vs Tesla** - "Compare NVIDIA vs Tesla"

**Just ask:** "Compare [stock1] vs [stock2]"

Which comparison would you like to see?"""
    
    def _handle_strategy(self, message: str, stock_data: dict, memory: ConversationMemory, context: dict) -> str:
        """Investment strategy guidance"""
        return """## 🎯 **Investment Strategies for Different Goals**

### 1️⃣ **The Index Fund Strategy** (Passive)
**Best for:** Beginners, busy people
**Allocation:**
• 70% S&P 500 Index Fund
• 20% International Index
• 10% Bonds

**Effort:** Very low (rebalance yearly)
**Expected Return:** ~8-10%/year
**Risk:** Medium

---

### 2️⃣ **The Dividend Growth Strategy**
**Best for:** Income seekers, retirees
**Allocation:**
• 60% Dividend aristocrats (Apple, J&J, Coca-Cola)
• 30% Bonds
• 10% Growth stocks

**Effort:** Low (review quarterly)
**Expected Return:** ~6-8%/year + dividends
**Risk:** Low-Medium

---

### 3️⃣ **The Growth Investor Strategy**
**Best for:** Young, risk-tolerant
**Allocation:**
• 50% Growth stocks (NVIDIA, Tesla, tech)
• 25% Established tech (Apple, Microsoft)
• 15% Emerging markets
• 10% Crypto (Bitcoin)

**Effort:** Medium (monitor monthly)
**Expected Return:** ~12-15%/year (volatile)
**Risk:** High

---

### 4️⃣ **The All-Weather Portfolio**
**Best for:** Conservative, retirees
**Allocation:**
• 30% Stocks
• 40% Bonds
• 15% Gold
• 15% Commodities

**Effort:** Low (rebalance semi-annually)
**Expected Return:** ~5-7%/year
**Risk:** Low

---

### 5️⃣ **The 3-Fund Portfolio** (Simple & Effective)
**Best for:** Most investors!
**Allocation:**
• 60% Total US Stock Market
• 30% Total International Stock
• 10% Total Bond Market

**Effort:** Very low
**Expected Return:** ~7-9%/year
**Risk:** Medium

---

**📊 My Recommendation:**
1. Start with Index Funds (Strategy #1 or #5)
2. Add dividend stocks as you learn
3. Allocate 5-10% to individual stocks only after research
4. Keep 3-6 months expenses in cash

**Age-Based Rules:**
• **Under 30:** 80-90% stocks, 10-20% bonds
• **30-50:** 70% stocks, 30% bonds/stable
• **50-65:** 50-60% stocks, 40-50% bonds
• **Over 65:** 30-40% stocks, 60-70% bonds/cash

Which strategy fits your situation?"""
    
    def _handle_risk(self, message: str, stock_data: dict, memory: ConversationMemory, context: dict) -> str:
        """Risk assessment and management"""
        return """## ⚠️ **Understanding & Managing Investment Risk**

### **Risk Spectrum (Our Assets)**

**🟢 Lowest Risk → 🔴 Highest Risk**

1. **Gold (GC=F)** 🟢
   • Volatility: ±10-15%/year
   • Worst year: -28% (2013)
   • Best use: Portfolio stabilizer

2. **Apple (AAPL)** 🟡
   • Volatility: ±20-30%/year
   • Worst year: -32% (2022)
   • Best use: Core holding

3. **NVIDIA (NVDA)** 🟠
   • Volatility: ±40-60%/year
   • Worst year: -50% (2022)
   • Best use: Growth allocation

4. **Tesla (TSLA)** 🔴
   • Volatility: ±60-80%/year
   • Worst year: -65% (2022)
   • Best use: Speculative 5% max

5. **Bitcoin (BTC-USD)** 🔴🔴
   • Volatility: ±80-150%/year
   • Worst year: -73% (2022)
   • Best use: 1-5% speculative

---

### **Risk Management Rules**

**1. Position Sizing**
• Never more than 5-10% in one stock
• High-risk assets: Max 5%
• Total speculative: Max 15%

**2. Stop Losses**
• Set mental stops at -15% for stocks
• Sell if fundamentals change
• Don't average down on falling knives

**3. Diversification**
• Minimum 8-10 different stocks
• Multiple sectors
• Include defensive assets (gold, bonds)

**4. Emergency Fund First!**
• 3-6 months expenses in cash
• Never invest money you need soon
• Invest only "patience capital"

**5. Emotional Control**
• Market drops are NORMAL
• Down 20%? It's called a bear market
• Don't panic sell at bottoms
• Have a written investment plan

---

### **Risk Tolerance Quiz**

**Can you handle a 30% portfolio drop?**
• **Yes, I'd buy more:** Aggressive (70-80% stocks)
• **Yes, I'd hold:** Moderate (50-60% stocks)
• **No, I'd panic:** Conservative (30-40% stocks)

**Time horizon:**
• **20+ years:** Can take high risk
• **10-20 years:** Moderate risk
• **5-10 years:** Lower risk
• **<5 years:** Very low risk, mostly cash/bonds

---

### **Real Example: 2022 Bear Market**

**What happened:**
• S&P 500: -18%
• NASDAQ (Tech): -33%
• Tesla: -65%
• Bitcoin: -73%
• Gold: +1%

**Who survived:**
✅ Diversified investors (-15%)
✅ Index fund holders (recovered 2023)
✅ Dollar-cost averagers (bought the dip)

❌ Panic sellers (locked in losses)
❌ Over-leveraged traders (wiped out)
❌ All-in on one stock (devastating)

**Lesson:** Diversification works. Patience pays.

What's your risk tolerance?"""
    
    def _handle_prediction(self, message: str, stock_data: dict, memory: ConversationMemory, context: dict) -> str:
        """Handle prediction requests with trend analysis"""
        stock_ticker = self._extract_stock(message, memory)
        
        if not stock_ticker:
            return """I can analyze trends for:
• Apple (AAPL)
• NVIDIA (NVDA)
• Tesla (TSLA)
• Gold (GC=F)
• Bitcoin (BTC-USD)

**Note:** No one can predict the future with certainty! I can show historical patterns and current trends.

Which asset would you like me to analyze?"""
        
        response = f"""## 📈 **Trend Analysis: {stock_ticker}**

**⚠️ Important Disclaimer:**
Nobody can predict stock prices with certainty - not even AI! Past performance ≠ future results.

**What I can tell you:**

**Historical Pattern (Last 90 days):**
"""
        
        # Simulate trend analysis (in production, use real data)
        if stock_ticker == "NVDA":
            response += """• **Trend:** Strong uptrend ↗️
• **Momentum:** Bullish (high volume on up days)
• **Support:** $400 level holding strong
• **Resistance:** $500 psychological barrier

**Factors to Watch:**
✅ AI chip demand remains high
✅ Data center revenue growing
⚠️ Valuation getting stretched (P/E 60+)
⚠️ Competition from AMD increasing"""
        
        elif stock_ticker == "AAPL":
            response += """• **Trend:** Sideways consolidation ->
• **Momentum:** Neutral (mixed signals)
• **Support:** $165-170 range
• **Resistance:** $185-190 range

**Factors to Watch:**
✅ Services revenue growing steadily
✅ New product launches (Vision Pro)
⚠️ iPhone sales slowing in China
⚠️ Regulatory pressures"""
        
        elif stock_ticker == "TSLA":
            response += """• **Trend:** High volatility, recent uptrend ↗️
• **Momentum:** Mixed (news-driven)
• **Support:** $200 level
• **Resistance:** $300 level

**Factors to Watch:**
✅ Cybertruck production ramping
✅ Energy storage division growing
⚠️ EV competition intensifying
⚠️ Musk-related headline risk"""
        
        elif stock_ticker == "BTC-USD":
            response += """• **Trend:** Bull market phase 📈
• **Momentum:** Strong (broke key resistance)
• **Support:** $40,000 level
• **Resistance:** $50,000-60,000 range

**Factors to Watch:**
✅ Bitcoin ETF approvals
✅ 2024 Halving cycle coming
⚠️ Regulatory uncertainty
⚠️ Extreme volatility"""
        
        elif stock_ticker == "GC=F":
            response += """• **Trend:** Gradual uptrend ↗️
• **Momentum:** Steady (safe-haven flows)
• **Support:** $1,900/oz
• **Resistance:** $2,100/oz

**Factors to Watch:**
✅ Fed pausing rate hikes
✅ Geopolitical tensions
⚠️ Strong dollar pressure
⚠️ Rising real yields"""
        
        response += """

**📊 Probability Assessment:**
(Based on historical patterns, not guarantees)

**Next 30 days:**
• Higher: 55% chance
• Flat: 30% chance
• Lower: 15% chance

**Next 90 days:**
• Up 10%+: 40% chance
• Flat ±5%: 35% chance
• Down 10%+: 25% chance

**💡 Investment Wisdom:**
Instead of trying to predict:
1. **Dollar-cost average** (invest regularly)
2. **Focus on fundamentals** (earnings, growth)
3. **Think long-term** (5+ years)
4. **Diversify** (don't bet on one stock)

**Remember:** Markets are unpredictable short-term but trend up long-term (historically ~10%/year).

Would you like specific entry/exit strategies for this asset?"""
        
        return response
    
    def _handle_news(self, message: str, stock_data: dict, memory: ConversationMemory, context: dict) -> str:
        """Handle news and market updates requests"""
        stock_ticker = self._extract_stock(message, memory)
        
        return """## 📰 **Market News & Updates**

I don't have real-time news integration yet, but I can help you understand:

**📊 Where to Find Reliable News:**
• **Bloomberg** - Professional market news
• **CNBC** - Real-time market coverage
• **Reuters** - Global financial news
• **Yahoo Finance** - Stock-specific news
• **Seeking Alpha** - Investment analysis

**🎯 What to Focus On:**
1. **Earnings Reports** - Quarterly results
2. **Fed Announcements** - Interest rate decisions
3. **Economic Data** - GDP, inflation, jobs
4. **Company Announcements** - Mergers, products
5. **Analyst Ratings** - Upgrades/downgrades

**Pro Tip:** Don't overreact to daily news! Focus on long-term fundamentals.

**Want analysis instead?** Ask:
• "Should I invest in [stock]?"
• "Analyze [stock] trend"
• "Compare [stock1] vs [stock2]"""
    
    def _handle_portfolio(self, message: str, stock_data: dict, memory: ConversationMemory, context: dict) -> str:
        """Handle portfolio tracking and management"""
        return """## 📊 **Portfolio Management**

**Track Your Investments:**
I don't have portfolio tracking integrated yet, but here's how to manage yours:

**📱 Recommended Portfolio Apps:**
• **Yahoo Finance** - Free, comprehensive
• **Personal Capital** - Holistic view
• **Robinhood** - Simple tracking
• **Fidelity/Charles Schwab** - Full-featured

**🎯 Portfolio Building Tips:**

**Beginner Portfolio (Conservative):**
• 50% Large-cap stocks (AAPL, MSFT)
• 30% Bonds/Fixed income
• 10% Gold (safe haven)
• 10% Cash

**Intermediate Portfolio (Balanced):**
• 60% Stocks (diversified sectors)
• 20% Growth stocks (NVDA, TSLA)
• 10% Bonds
• 5% Gold
• 5% Crypto

**Advanced Portfolio (Aggressive):**
• 70% Tech stocks
• 15% Growth stocks
• 10% Crypto
• 5% Commodities

**Key Principles:**
✅ Diversify across sectors
✅ Rebalance quarterly
✅ Dollar-cost average
✅ Keep emergency fund separate

**Want personalized advice?** Tell me:
• Your age and goals
• Risk tolerance
• Investment timeline
• Current holdings

Ask: "Help me build a portfolio for [your situation]"""
    
    def _handle_general(self, message: str, stock_data: dict, memory: ConversationMemory, context: dict) -> str:
        """
        HYBRID APPROACH: Use Groq LLM for natural conversation when available,
        fallback to hardcoded menu if API key not set or LLM fails.
        
        Combines:
        - Real-time stock data from yfinance
        - Custom knowledge base (your investment advice)
        - LLM natural language understanding
        """
        # Try LLM first if available
        if memory.groq_client:
            try:
                return self._handle_general_with_llm(message, stock_data, memory, context)
            except Exception as e:
                print(f"⚠️ LLM failed ({e}), using fallback response")
                # Continue to fallback below
        
        # FALLBACK: Hardcoded menu response (works without API key)
        msg_lower = message.lower()
        
        # Try to detect what user might be asking about
        if "how" in msg_lower or "what" in msg_lower:
            return """I can help you understand:

**💡 Financial Concepts:**
• Diversification - Risk management
• P/E Ratio - Valuation metric  
• Dollar-Cost Averaging - Smart buying strategy
• Market Cap - Company size
• Dividends - Regular payments

Just ask: "Explain [concept]"

**📊 Specific Stocks:**
• Apple (AAPL) - Tech ecosystem
• NVIDIA (NVDA) - AI chips
• Tesla (TSLA) - Electric vehicles
• Gold (GC=F) - Safe haven
• Bitcoin (BTC-USD) - Cryptocurrency

Just ask: "Should I invest in [stock]?"

**📖 Learning:**
• Beginner tutorials (say "Start tutorial")
• Investment strategies (say "Show strategies")
• Risk management (say "Explain risk")

What would you like to know?"""
        
        elif "price" in msg_lower or "current" in msg_lower:
            return """I can check current prices for:

• **Apple (AAPL)** - "What's Apple's price?"
• **NVIDIA (NVDA)** - "NVDA current price?"
• **Tesla (TSLA)** - "Tesla stock price?"
• **Gold (GC=F)** - "Gold price today?"
• **Bitcoin (BTC-USD)** - "Bitcoin price?"

Which would you like to check?"""
        
        return """I'm your AI Financial Advisor! I can help with:

**💡 Investment Questions:**
• "Should I invest in [stock/sector]?"
• "Is [stock] a good buy?"
• "Compare [stock1] vs [stock2]"

**📚 Learn Finance:**
• "Explain diversification"
• "What is P/E ratio?"
• "Start beginner tutorial"

**📈 Market Analysis:**
• "What's [stock] price?"
• "Analyze [stock] trend"
• "Show me investment strategies"

**🎯 Portfolio Help:**
• "Help me build a portfolio"
• "What's my risk tolerance?"
• "Should I buy or sell?"

**Example questions:**
• "Should I invest in tech stocks?"
• "What is the current price of Apple?"
• "Explain dollar-cost averaging"
• "Compare NVIDIA vs Tesla"

What would you like to explore?"""
    
    def _handle_general_with_llm(self, message: str, stock_data: dict, memory: ConversationMemory, context: dict) -> str:
        """
        Use Groq LLM to handle natural/unexpected queries with context injection.
        
        This method:
        1. Extracts real-time stock data (if relevant)
        2. Pulls custom knowledge from hardcoded advice
        3. Sends everything to LLM with proper context
        4. Returns natural conversational response
        """
        
        # Build context for LLM
        context_parts = []
        
        # Add stock data if available
        stock_ticker = self._extract_stock(message, memory)
        if stock_ticker and stock_data and stock_data.get('price'):
            price = stock_data.get('price', 'N/A')
            change_percent = stock_data.get('change_percent', 0)
            company_name = stock_data.get('name', stock_ticker)
            
            context_parts.append(f"""
CURRENT MARKET DATA:
{company_name} ({stock_ticker}):
- Price: ${price:.2f}
- Change: {change_percent:+.2f}%
- Day High: ${stock_data.get('day_high', 'N/A'):.2f}
- Day Low: ${stock_data.get('day_low', 'N/A'):.2f}
- Volume: {stock_data.get('volume', 'N/A'):,}
""")
        
        # Add knowledge base for specific stocks
        if stock_ticker:
            stock_advice = self._get_stock_advice_summary(stock_ticker)
            if stock_advice:
                context_parts.append(f"\nINVESTMENT ANALYSIS:\n{stock_advice}")
        
        # Add conversation history
        recent_context = memory.get_recent_context(n=2)
        if recent_context:
            context_parts.append(f"\nRECENT CONVERSATION:\n{recent_context}")
        
        # Build system prompt
        system_prompt = """You are NeuroSight AI, an expert financial advisor chatbot. 

Your role:
- Answer financial questions in a friendly, conversational tone
- Use the provided market data and analysis when available
- Be honest about limitations (no predictions, not financial advice)
- Keep responses concise but informative (3-5 sentences typically)
- Use emojis sparingly for visual interest
- Never make up stock prices - only use provided data

When user asks casually (like "yo", "how's", "what u think"):
- Respond naturally but professionally
- Still include actual data and analysis
- Maintain helpful advisor personality

Remember: You're a helpful AI assistant, not a formal financial advisor."""
        
        # Build user prompt with context
        user_prompt = message
        if context_parts:
            user_prompt = "\n".join(context_parts) + f"\n\nUSER QUESTION: {message}"
        
        # Call Groq API
        response = memory.groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",  # Current supported model (Jan 2026)
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.7,  # Balanced creativity
            max_tokens=500,   # Concise responses
            top_p=0.9
        )
        
        llm_response = response.choices[0].message.content.strip()
        
        # Add disclaimer for investment advice
        if any(word in message.lower() for word in ["should i", "recommend", "advice", "buy", "sell"]):
            llm_response += "\n\n💡 *This is educational information, not financial advice. Always do your own research and consider consulting a financial advisor.*"
        
        return llm_response
    
    def _get_stock_advice_summary(self, stock_ticker: str) -> Optional[str]:
        """Extract relevant advice from knowledge base for LLM context"""
        advice_map = {
            "AAPL": "Apple Inc. - Mature tech giant with strong ecosystem (iPhone, Mac, Services). Stable dividend payer. Lower growth but reliable. Good for conservative portfolios.",
            "NVDA": "NVIDIA - AI chip leader benefiting from AI boom. High growth potential but volatile. 80% data center market share. Strong margins (50%+). Good for aggressive growth investors.",
            "TSLA": "Tesla - EV market leader with energy storage business. Very volatile. Led by Elon Musk. Autonomous driving potential. High risk/high reward. For speculative portfolios only.",
            "GC=F": "Gold - Traditional safe-haven asset. Hedge against inflation and market volatility. No yield but capital preservation. Good for risk-averse portfolios (5-10% allocation).",
            "BTC-USD": "Bitcoin - Highly volatile cryptocurrency. Speculative asset with no intrinsic value. High risk but potential for high returns. Only invest what you can afford to lose."
        }
        return advice_map.get(stock_ticker)
    
    def _extract_stock(self, message: str, memory: ConversationMemory) -> Optional[str]:
        """Extract stock ticker from message or context"""
        msg_lower = message.lower()
        
        stock_map = {
            "apple": "AAPL", "aapl": "AAPL",
            "nvidia": "NVDA", "nvda": "NVDA",
            "tesla": "TSLA", "tsla": "TSLA",
            "gold": "GC=F",
            "bitcoin": "BTC-USD", "btc": "BTC-USD", "crypto": "BTC-USD"
        }
        
        for keyword, ticker in stock_map.items():
            if keyword in msg_lower:
                return ticker
        
        # Check conversation context
        if any(word in msg_lower for word in ["it", "this", "that"]):
            return memory.extract_stock_from_context()
        
        return None


# Global enhanced LLM instance
enhanced_llm_engine = EnhancedFinancialLLM()
