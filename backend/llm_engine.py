# llm_engine.py - Lightweight Local LLM for Financial Chatbot
# Optimized for low-end hardware (Core i5 4th gen, 6GB RAM, no GPU)

import os
from pathlib import Path
import json
from datetime import datetime

class LightweightFinancialLLM:
    """
    Rule-based + Template-based conversational AI for financial advice.
    Optimized for systems without GPU and limited RAM.
    """
    
    def __init__(self):
        self.conversation_history = []
        self.financial_knowledge = self._load_financial_knowledge()
        
    def _load_financial_knowledge(self):
        """Load financial advice templates and knowledge base"""
        return {
            "stock_advice": {
                "AAPL": {
                    "company": "Apple Inc.",
                    "sector": "Technology",
                    "advice": "Apple is known for its strong ecosystem, loyal customer base, and consistent innovation. The company has diversified revenue streams including iPhone, Services, and Wearables. Consider it as a stable long-term hold with growth potential.",
                    "risks": "High competition in smartphones, dependence on China manufacturing, regulatory scrutiny.",
                    "opportunity": "Growing services revenue, potential in AR/VR, expansion in financial services."
                },
                "NVDA": {
                    "company": "NVIDIA Corporation",
                    "sector": "Semiconductors/AI",
                    "advice": "NVIDIA is the leader in AI chips and data center GPUs. With the AI boom, demand for their H100 and upcoming chips remains extremely high. Strong growth potential but watch for high valuation.",
                    "risks": "Cyclical semiconductor industry, competition from AMD and Intel, export restrictions to China.",
                    "opportunity": "AI infrastructure demand, autonomous vehicles, gaming growth, cloud partnerships."
                },
                "TSLA": {
                    "company": "Tesla Inc.",
                    "sector": "Electric Vehicles/Energy",
                    "advice": "Tesla pioneered mass-market EVs and has strong brand recognition. However, competition is intensifying from traditional automakers. High volatility makes it suitable for risk-tolerant investors.",
                    "risks": "Increasing EV competition, production challenges, CEO-related volatility, high valuation.",
                    "opportunity": "Energy storage growth, autonomous driving, expanding vehicle lineup, charging network."
                },
                "GC=F": {
                    "company": "Gold",
                    "sector": "Commodities",
                    "advice": "Gold is a traditional safe-haven asset and inflation hedge. It performs well during economic uncertainty and when real interest rates are low. Consider allocating 5-10% of portfolio for diversification.",
                    "risks": "No dividend income, storage costs for physical gold, vulnerable to rising interest rates.",
                    "opportunity": "Hedge against inflation, geopolitical uncertainty, central bank purchases, dollar weakness."
                },
                "BTC-USD": {
                    "company": "Bitcoin",
                    "sector": "Cryptocurrency",
                    "advice": "Bitcoin is the leading cryptocurrency with institutional adoption growing. However, it's highly volatile and speculative. Only invest what you can afford to lose completely. Consider as a small portfolio allocation (1-5%).",
                    "risks": "Extreme volatility, regulatory uncertainty, environmental concerns, security risks.",
                    "opportunity": "Digital gold narrative, institutional adoption, halving cycles, inflation hedge potential."
                }
            },
            "investment_strategies": {
                "conservative": "Focus on blue-chip stocks, bonds, and dividend-paying companies. Prioritize capital preservation.",
                "moderate": "Balanced mix of growth and value stocks, some international exposure, 60/40 stocks/bonds ratio.",
                "aggressive": "Growth stocks, emerging markets, small-caps, cryptocurrencies. Higher risk tolerance required.",
                "diversification": "Don't put all eggs in one basket. Spread across sectors, geographies, and asset classes."
            },
            "market_concepts": {
                "bull_market": "A bull market means prices are rising or expected to rise. Good time for growth stocks.",
                "bear_market": "A bear market means prices are falling 20%+ from recent highs. Time for defensive stocks or cash.",
                "volatility": "Volatility measures price fluctuations. High volatility = high risk and potential reward.",
                "pe_ratio": "P/E ratio (Price-to-Earnings) shows if a stock is expensive. Lower is cheaper, but context matters.",
                "diversification": "Spreading investments across different assets to reduce risk.",
                "dividend": "Regular cash payments to shareholders from company profits.",
                "market_cap": "Total value of a company's shares. Large-cap = safer, small-cap = riskier but higher growth."
            }
        }
    
    def generate_response(self, user_message: str, stock_data: dict = None, context: dict = None) -> str:
        """
        Generate intelligent response based on user message and context
        
        Args:
            user_message: The user's input
            stock_data: Current stock price information if available
            context: Conversation context including last_stock
        
        Returns:
            str: AI-generated response
        """
        msg_lower = user_message.lower()
        context = context or {}
        
        # Store in conversation history
        self.conversation_history.append({
            "role": "user",
            "content": user_message,
            "timestamp": datetime.now()
        })
        
        response = ""
        
        # === NeuroSight App Usage Guide (HIGHEST PRIORITY - CHECK FIRST) ===
        if any(phrase in msg_lower for phrase in [
            "how do i invest using neurosight", "how to invest using neurosight",
            "invest using neurosight", "use neurosight", "how to use this app", 
            "how does this app work", "how to use neurosight", "invest in neurosight", 
            "use this app", "neurosight guide", "app guide", "how can i invest using neurosight",
            "start beginner investment tutorial", "beginner guide", "beginner investment",
            "how to start", "getting started", "beginner tutorial", "start tutorial"
        ]):
            response = """🎯 **Welcome to NeuroSight!** Here's how to use the app for smart investments:

**Step 1📌⃣: Go to Dashboard**
Navigate to your main dashboard where you'll see all available assets.

**Step 2📌⃣: Select Your Asset**
Choose from Apple, NVIDIA, Tesla, Gold, or Bitcoin based on your interest.

**Step 3📌⃣: View AI Predictions**
Our advanced AI models provide price predictions with confidence scores.

**Step 4📌⃣: Analyze the Data**
Review historical trends, technical indicators, and market sentiment analysis.

**Step 5📌⃣: Make Informed Decisions**
Use the insights to guide your investment strategy. Remember: predictions are tools, not guarantees!

**💡 Pro Tips**:
• Compare multiple assets before deciding
• Check prediction confidence levels
• Review historical accuracy metrics
• Consider your risk tolerance
• Don't invest more than you can afford to lose

Ready to start? Head to the Dashboard and explore! 🚀

_Have questions about a specific stock? Just ask me!_"""
        
        # === Conversational Greetings ===
        elif any(word in msg_lower for word in ["hello", "hi", "hey", "good morning", "good afternoon", "good evening"]):
            greetings = [
                "Hello! I'm your NeuroSight AI financial advisor. I can help you understand stocks, market trends, and investment strategies. What would you like to explore today?",
                "Hi there! Ready to dive into the world of finance? Ask me about Apple, NVIDIA, Tesla, Gold, or Bitcoin!",
                "Hey! I'm here to provide financial insights and real-time market data. What stock interests you?"
            ]
            response = greetings[hash(user_message) % len(greetings)]
        
        # === Goodbye ===
        elif any(word in msg_lower for word in ["bye", "goodbye", "see you", "exit", "quit"]):
            response = "Goodbye! Remember: invest wisely, diversify, and never invest more than you can afford to lose. Come back anytime for market insights! 📈"
        
        # === Thank you ===
        elif "thank" in msg_lower:
            response = "You're very welcome! 📌 Feel free to ask more questions anytime. Remember, continuous learning is key to successful investing!"
        
        # === Help / Capabilities ===
        elif any(word in msg_lower for word in ["help", "what can you do", "capabilities", "features"]):
            response = """I'm your AI-powered financial assistant! Here's what I can do:

📊 **Real-Time Stock Data**: Get live prices for Apple, NVIDIA, Tesla, Gold, and Bitcoin
💡 **Investment Advice**: Receive detailed analysis and recommendations
📈 **Market Insights**: Understand trends, risks, and opportunities
📌 **Financial Education**: Learn about P/E ratios, diversification, market caps, and more
💬 **Natural Conversations**: Ask me anything about finance in plain English!
🎯 **App Guidance**: Learn how to use NeuroSight for predictions

Try asking:
• "What's your advice on NVIDIA?"
• "Should I invest in Tesla?"
• "Explain diversification to me"
• "Is Apple a good long-term investment?"
• "How do I invest using NeuroSight?"

⚠️ Remember: This is educational content, not professional financial advice."""
        
        # === Stock-Specific Investment Advice ===
        # Check for both direct advice questions and general stock info with investment context
        is_asking_advice = self._is_asking_advice(msg_lower)
        is_asking_about_investment = "investment" in msg_lower or "investing" in msg_lower
        
        if is_asking_advice or is_asking_about_investment:
            stock_ticker = self._extract_stock_from_message(msg_lower, context)
            if stock_ticker and stock_ticker in self.financial_knowledge["stock_advice"]:
                advice_data = self.financial_knowledge["stock_advice"][stock_ticker]
                response = f"""Let me share insights about **{advice_data['company']}** ({stock_ticker}):

**📊 Sector**: {advice_data['sector']}

**💡 Investment Perspective**:
{advice_data['advice']}

**⚠️ Key Risks**:
{advice_data['risks']}

**🚀 Growth Opportunities**:
{advice_data['opportunity']}

**My Take**: Consider your risk tolerance, investment timeline, and portfolio diversification. {stock_ticker} can be part of a balanced strategy, but shouldn't be your only holding.

⚠️ _This is educational analysis, not financial advice. Always do your own research._"""
                
                if stock_data:
                    response += f"\n\n**Current Price**: ${stock_data.get('price', 'N/A')}"
            else:
                response = "I specialize in Apple (AAPL), NVIDIA (NVDA), Tesla (TSLA), Gold, and Bitcoin. Could you specify one of these assets?"
        
        # === Investment Strategy Questions ===
        elif any(word in msg_lower for word in ["strategy", "how should i invest", "investment approach", "portfolio"]):
            response = """Here are proven investment strategies:

**📌 Conservative Strategy** (Low Risk):
Focus on blue-chip stocks, bonds, and dividend-payers. Great for preserving capital with modest growth. Example: 50% bonds, 30% large-cap stocks, 20% cash.

**📌 Moderate Strategy** (Balanced):
60% stocks (mix of growth and value), 40% bonds. Balances growth and stability. Suitable for most long-term investors.

**🚀 Aggressive Strategy** (High Risk/Reward):
80-90% stocks (growth, small-cap, emerging markets), 5-10% crypto, minimal bonds. Higher volatility but potential for strong returns.

**📌 My Recommendations**:
1. **Diversify**: Never put all eggs in one basket
2. **Dollar-Cost Average**: Invest regularly, not all at once
3. **Long-Term Focus**: Markets reward patience (5+ years)
4. **Emergency Fund**: Keep 3-6 months expenses in cash
5. **Rebalance**: Review portfolio quarterly

Which risk level fits your situation?"""
        
        # === Market Concepts Education ===
        elif any(concept in msg_lower for concept in ["what is", "explain", "tell me about", "define"]):
            response = self._explain_financial_concept(msg_lower)
        
        # === Comparison Questions ===
        elif any(word in msg_lower for word in ["vs", "versus", "compare", "better", "difference between"]):
            response = self._handle_comparison(msg_lower)
        
        # === Risk Assessment ===
        elif any(word in msg_lower for word in ["risk", "safe", "dangerous", "volatile", "stability"]):
            response = """Let me break down risk levels for our supported assets:

**🟢 Lower Risk**: Gold - Traditional safe haven, relatively stable
**🟡 Moderate Risk**: Apple - Established tech giant, proven track record
**🟠 Higher Risk**: NVIDIA, Tesla - Growth stocks, more volatile
**🔴 Highest Risk**: Bitcoin - Extremely volatile, speculative

**Risk Management Tips**:
1. Never invest money you can't afford to lose
2. Diversify across different risk levels
3. Younger investors can take more risk (longer time to recover)
4. Volatility = opportunity for long-term investors
5. Use stop-loss orders to limit downside

What's your risk tolerance: Conservative, Moderate, or Aggressive?"""
        
        # === Timing Questions ===
        elif any(word in msg_lower for word in ["when", "timing", "buy now", "wait", "good time"]):
            response = """⏰ **Market Timing Wisdom**:

The truth is, **timing the market is nearly impossible** - even for professionals! Here's a better approach:

**✅ Do This**:
• **Dollar-Cost Averaging**: Invest fixed amounts regularly (weekly/monthly)
• **Buy the Dip**: Add to positions during market corrections
• **Long-Term View**: Best time to invest was yesterday, second best is today
• **Ignore Daily Noise**: Focus on fundamentals, not daily fluctuations

**❌ Avoid This**:
• Trying to "catch the bottom"
• Panic selling during downturns
• Waiting for the "perfect moment"
• Following herd mentality

**Time in the market > Timing the market**

Looking at a specific stock? I can provide current price and trend analysis!"""
        
        # === Follow-up context handling ===
        elif any(word in msg_lower for word in ["it", "this", "that", "more", "tell me more"]) and context.get("last_stock"):
            stock_ticker = context["last_stock"]
            if stock_ticker in self.financial_knowledge["stock_advice"]:
                advice_data = self.financial_knowledge["stock_advice"][stock_ticker]
                response = f"""More insights on **{advice_data['company']}**:

The company operates in the {advice_data['sector']} sector, which is {'growing rapidly' if stock_ticker in ['NVDA', 'TSLA', 'BTC-USD'] else 'well-established'}.

**Investment Thesis**:
{advice_data['advice']}

**What to Watch**:
• Quarterly earnings reports
• Industry trends and competition
• Macroeconomic factors (interest rates, inflation)
• Company-specific news and product launches

Want to know the current price? Just ask!"""
        
        # === Generic Fallback with Guidance ===
        else:
            response = """I'd love to help! I specialize in:

📌 **Stocks**: Apple, NVIDIA, Tesla
💰 **Commodities**: Gold
₿ **Crypto**: Bitcoin

**Try asking**:
• "What's Apple stock price?"
• "Should I invest in NVIDIA?"
• "Is Tesla risky?"
• "Explain diversification"
• "Compare Apple vs NVIDIA"
• "What's your investment strategy advice?"

I'm here to make finance simple and actionable! 📊"""
        
        # Store AI response in history
        self.conversation_history.append({
            "role": "assistant",
            "content": response,
            "timestamp": datetime.now()
        })
        
        return response
    
    def _is_asking_advice(self, msg: str) -> bool:
        """Check if user is asking for investment advice"""
        advice_keywords = [
            "should i invest",
            "can i invest",
            "how to invest",
            "how can i invest",
            "is it good",
            "good investment",
            "worth buying",
            "your opinion",
            "what do you think",
            "recommend",
            "advice on",
            "thoughts on",
            "good buy",
            "worth it",
            "invest in",
            "investing in"
        ]
        return any(keyword in msg for keyword in advice_keywords)
    
    def _extract_stock_from_message(self, msg: str, context: dict = None) -> str:
        """Extract stock ticker from user message"""
        # Use word boundaries to match exact words or parts of compound words
        stock_map = {
            "apple": "AAPL",
            "aapl": "AAPL",
            "nvidia": "NVDA",
            "nvda": "NVDA",
            "tesla": "TSLA",
            "tsla": "TSLA",
            "gold": "GC=F",
            "bitcoin": "BTC-USD",
            "btc": "BTC-USD",
            "crypto": "BTC-USD"
        }
        
        # Check for exact matches first (prioritize longer/more specific matches)
        # Sort by length descending to match "bitcoin" before "bit", etc.
        for keyword in sorted(stock_map.keys(), key=len, reverse=True):
            # Use word boundary check: stock name must be a separate word or at word boundary
            if keyword in msg:
                # Additional validation: make sure it's not part of another word
                # e.g., "in apple" should match "apple", not get confused by "in"
                idx = msg.find(keyword)
                # Check if it's at start, end, or surrounded by spaces/punctuation
                is_valid = (
                    idx == 0 or not msg[idx-1].isalnum()
                ) and (
                    idx + len(keyword) >= len(msg) or not msg[idx + len(keyword)].isalnum()
                )
                if is_valid:
                    return stock_map[keyword]
        
        # Check context for last mentioned stock
        if context and context.get("last_stock"):
            return context["last_stock"]
        
        return None
    
    def _explain_financial_concept(self, msg: str) -> str:
        """Explain financial concepts in simple terms"""
        concepts = self.financial_knowledge["market_concepts"]
        
        if any(word in msg for word in ["bull market", "bull"]):
            return f"📌 **Bull Market**: {concepts['bull_market']}\n\nExample: The 2010-2020 decade was largely a bull market. Investors who stayed invested saw great returns!"
        
        elif any(word in msg for word in ["bear market", "bear"]):
            return f"📌 **Bear Market**: {concepts['bear_market']}\n\nExample: 2022 was a bear market. Smart investors bought the dip and benefited when markets recovered!"
        
        elif "volatility" in msg or "volatile" in msg:
            return f"📊 **Volatility**: {concepts['volatility']}\n\nThink of it like waves: calm sea = low volatility, stormy sea = high volatility. Bitcoin is very volatile, Apple is less so."
        
        elif "p/e" in msg or "pe ratio" in msg or "price to earnings" in msg:
            return f"📌 **P/E Ratio**: {concepts['pe_ratio']}\n\nExample: If a stock costs $100 and earns $5/year, P/E = 20. Lower P/E might mean it's cheap, but compare within the same industry!"
        
        elif "diversif" in msg:
            return f"📌 **Diversification**: {concepts['diversification']}\n\nThink: Don't invest everything in one stock! Spread across tech, healthcare, commodities, etc. If one sector crashes, others might stay strong."
        
        elif "dividend" in msg:
            return f"💵 **Dividends**: {concepts['dividend']}\n\nExample: Apple pays ~$0.24 per share quarterly. If you own 100 shares, you get $24 every 3 months - passive income!"
        
        elif "market cap" in msg:
            return f"📌 **Market Capitalization**: {concepts['market_cap']}\n\nApple ($3T) = Mega-cap, very stable\nSmall companies ($500M) = Small-cap, riskier but higher growth potential"
        
        else:
            return """I can explain these financial concepts:
• **Bull Market** - Rising prices
• **Bear Market** - Falling prices
• **Volatility** - Price fluctuation intensity
• **P/E Ratio** - Stock valuation metric
• **Diversification** - Risk spreading strategy
• **Dividends** - Regular shareholder payments
• **Market Cap** - Company size/value

Which one interests you?"""
    
    def _handle_comparison(self, msg: str) -> str:
        """Handle comparison questions between stocks"""
        if ("apple" in msg or "aapl" in msg) and ("nvidia" in msg or "nvda" in msg):
            return """**Apple vs NVIDIA Comparison**:

**📌 Apple (AAPL)**:
✅ Established, mature company
✅ Diverse revenue streams
✅ Strong dividend history
✅ Lower volatility
❌ Slower growth rate

**🚀 NVIDIA (NVDA)**:
✅ Leading AI/chip maker
✅ Explosive growth potential
✅ Riding AI wave
❌ Higher volatility
❌ No dividend (recently added small one)
❌ More cyclical

**Verdict**: Apple = Stability, NVIDIA = Growth. Ideally, own both for diversification! Your choice depends on risk tolerance and time horizon."""
        
        elif ("tesla" in msg or "tsla" in msg) and ("apple" in msg or "aapl" in msg):
            return """**Tesla vs Apple Comparison**:

**⚡ Tesla (TSLA)**:
✅ Innovation leader in EVs
✅ High growth potential
❌ Very volatile
❌ CEO-dependent
❌ High competition

**📌 Apple (AAPL)**:
✅ Proven business model
✅ Strong ecosystem
✅ More predictable
❌ Slower growth

**Verdict**: Tesla is for aggressive investors who believe in EV future. Apple is for those wanting steady growth with less drama!"""
        
        elif "stock" in msg and "bond" in msg:
            return """**Stocks vs Bonds**:

**📈 Stocks** (Ownership):
✅ Higher returns (historically ~10%/year)
✅ Dividends + price appreciation
❌ More volatile
❌ Can lose value

**📌 Bonds** (Loans):
✅ Stable income
✅ Lower risk
❌ Lower returns (~3-5%/year)
❌ Lose value when rates rise

**Classic Mix**: 60% stocks / 40% bonds for balanced portfolio. Younger = more stocks, older = more bonds."""
        
        else:
            return "I can compare Apple vs NVIDIA, Tesla vs Apple, or explain Stocks vs Bonds. What comparison interests you?"
    
    def clear_history(self):
        """Clear conversation history"""
        self.conversation_history = []
    
    def get_conversation_summary(self) -> dict:
        """Get conversation statistics"""
        return {
            "total_exchanges": len(self.conversation_history) // 2,
            "user_messages": len([m for m in self.conversation_history if m["role"] == "user"]),
            "ai_responses": len([m for m in self.conversation_history if m["role"] == "assistant"])
        }

# Global LLM instance
llm_engine = LightweightFinancialLLM()
