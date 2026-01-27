"""
Signal Selection Agent
Uses Claude 3.5 Sonnet to analyze markets and generate trading signals
Now enhanced with technical indicators for quantitative signals
"""
from typing import Optional
from anthropic import Anthropic
import yaml
from src.utils.logger import get_logger
from src.utils.technical_indicators import technical_indicators
from src.orchestrator.state_models import MarketAnalysis, TradingSignal, TradingState
from config.settings import settings

logger = get_logger(__name__)


class SignalSelectionAgent:
    """AI-powered agent that generates trading signals using Claude 3.5 Sonnet"""

    def __init__(self):
        """Initialize Signal Selection Agent"""
        self.client = Anthropic(api_key=settings.anthropic_api_key)
        self.model = settings.llm_model

        # Load trading policy
        with open("config/trading_policy.yaml", "r") as f:
            self.policy = yaml.safe_load(f)

    def generate_signal(
        self,
        market_analysis: MarketAnalysis,
        state: TradingState
    ) -> TradingSignal:
        """
        Generate a trading signal for a market using Claude

        Args:
            market_analysis: Enriched market analysis with news and social data
            state: Current trading state for context

        Returns:
            Trading signal with recommendation
        """
        logger.info(f"Generating signal for {market_analysis.market.ticker}")

        # Build the prompt for Claude
        prompt = self._build_analysis_prompt(market_analysis, state)

        try:
            # Call Claude API
            response = self.client.messages.create(
                model=self.model,
                max_tokens=settings.llm_max_tokens,
                temperature=settings.llm_temperature,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )

            # Parse Claude's response
            analysis_text = response.content[0].text

            logger.info(f"Claude analysis:\n{analysis_text}")

            # Extract structured signal from response
            signal = self._parse_signal_from_response(
                analysis_text,
                market_analysis
            )

            logger.info(
                f"Signal generated: {signal.signal} "
                f"(Confidence: {signal.confidence}%, "
                f"Expected Return: {signal.expected_return:.1f}%)"
            )

            return signal

        except Exception as e:
            logger.error(f"Error generating signal: {e}")
            # Return NO_TRADE signal on error
            return TradingSignal(
                ticker=market_analysis.market.ticker,
                signal="NO_TRADE",
                confidence=0,
                expected_return=0,
                reasoning=f"Error in signal generation: {str(e)}",
                key_factors=[],
                risk_factors=["Analysis failed"],
                market_edge="None - error occurred"
            )

    def _build_analysis_prompt(
        self,
        market_analysis: MarketAnalysis,
        state: TradingState
    ) -> str:
        """Build comprehensive prompt for Claude"""

        market = market_analysis.market

        # Calculate key metrics
        yes_mid = (market.yes_bid + market.yes_ask) / 2
        no_mid = (market.no_bid + market.no_ask) / 2
        yes_spread = market.yes_ask - market.yes_bid
        implied_prob = yes_mid * 100

        # Calculate technical indicators
        # Note: historical_prices would come from market_analysis if available
        historical_prices = state.debug_info.get('historical_prices', {}).get(market.ticker, [])

        indicators = technical_indicators.calculate_all_indicators(
            market=market,
            historical_prices=historical_prices if historical_prices else None
        )

        interpretation = technical_indicators.interpret_indicators(indicators)

        # Summarize news
        news_summary = ""
        if market_analysis.news_articles:
            news_summary = "Recent News:\n"
            for i, article in enumerate(market_analysis.news_articles[:5], 1):
                news_summary += f"{i}. [{article.source}] {article.title}\n"
                if article.description:
                    news_summary += f"   {article.description[:200]}...\n"
        else:
            news_summary = "No recent news found.\n"

        # Summarize social sentiment
        social_summary = ""
        if market_analysis.social_posts:
            total_posts = len(market_analysis.social_posts)
            reddit_posts = [p for p in market_analysis.social_posts if p.platform == "reddit"]
            twitter_posts = [p for p in market_analysis.social_posts if p.platform == "twitter"]

            social_summary = f"Social Media Activity ({total_posts} posts):\n"
            social_summary += f"- Reddit: {len(reddit_posts)} discussions\n"
            social_summary += f"- Twitter: {len(twitter_posts)} tweets\n\n"

            # Show top posts
            social_summary += "Top discussions:\n"
            sorted_posts = sorted(
                market_analysis.social_posts,
                key=lambda x: x.score,
                reverse=True
            )
            for i, post in enumerate(sorted_posts[:3], 1):
                social_summary += f"{i}. [{post.platform}] {post.text[:150]}...\n"
        else:
            social_summary = "No social media activity found.\n"

        # Technical indicators summary
        technical_summary = f"""
TECHNICAL INDICATORS:
====================
Current Probability: {indicators.get('current_probability', 0):.1%}
Spread: {indicators.get('spread_pct', 0):.2f}% ({indicators.get('spread_quality', 'unknown')})

Momentum Signals:
- RSI: {indicators.get('rsi', 50):.1f} ({interpretation.get('rsi_signal', 'neutral')})
- Momentum: {indicators.get('momentum', 0):.3f} ({interpretation.get('momentum_signal', 'neutral')})
- MA Signal: {indicators.get('ma_signal', 'neutral')}
- Rate of Change: {indicators.get('rate_of_change', 0):.2f}%

Volatility Analysis:
- Volatility: {indicators.get('volatility', 0):.3f}
- Regime: {indicators.get('volatility_regime', 'unknown')}
- ATR: {indicators.get('atr', 0):.3f}
- Advice: {interpretation.get('volatility_advice', 'Use default risk parameters')}

Volume Profile:
- Volume Trend: {indicators.get('volume_trend', 'unknown')}
- Volume Signal: {indicators.get('volume_signal', 'unknown')}
- Volume Ratio: {indicators.get('volume_ratio', 1.0):.2f}x

Order Book Dynamics:
- Imbalance: {indicators.get('order_book_imbalance', 0):.3f}
- Signal: {indicators.get('imbalance_signal', 'balanced')}

Overall Technical Signal: {interpretation.get('overall_signal', 'neutral').upper()}
"""

        # Sentiment summary
        sentiment_summary = ""
        if market_analysis.news_sentiment is not None or market_analysis.social_sentiment is not None:
            sentiment_summary = f"""
SENTIMENT ANALYSIS:
==================
"""
            if market_analysis.news_sentiment is not None:
                news_score = market_analysis.news_sentiment
                news_label = "BULLISH" if news_score > 0.2 else "BEARISH" if news_score < -0.2 else "NEUTRAL"
                sentiment_summary += f"- News Sentiment: {news_score:+.2f} ({news_label})\n"

            if market_analysis.social_sentiment is not None:
                social_score = market_analysis.social_sentiment
                social_label = "BULLISH" if social_score > 0.2 else "BEARISH" if social_score < -0.2 else "NEUTRAL"
                sentiment_summary += f"- Social Sentiment: {social_score:+.2f} ({social_label})\n"

            if market_analysis.combined_sentiment is not None:
                combined_score = market_analysis.combined_sentiment
                combined_label = "BULLISH" if combined_score > 0.2 else "BEARISH" if combined_score < -0.2 else "NEUTRAL"
                sentiment_summary += f"- Combined Sentiment: {combined_score:+.2f} ({combined_label})\n"

        # Portfolio context
        portfolio_context = f"""
Current Portfolio Status:
- Balance: ${state.current_balance:.2f}
- Open Positions: {state.open_positions}
- Daily P&L: ${state.daily_pnl:.2f}
- Daily Trades: {state.daily_trades}
"""

        # Build the prompt
        prompt = f"""You are an expert predictive markets trader analyzing opportunities on Kalshi. Your goal is to identify high-probability trades with excellent risk/reward ratios.

MARKET DETAILS:
==============
Ticker: {market.ticker}
Question: {market.title}
Category: {market.category}

CURRENT PRICING:
- YES: Bid ${market.yes_bid:.2f} / Ask ${market.yes_ask:.2f} (Mid: ${yes_mid:.2f})
- NO: Bid ${market.no_bid:.2f} / Ask ${market.no_ask:.2f} (Mid: ${no_mid:.2f})
- Implied Probability: {implied_prob:.1f}%
- Spread: {yes_spread*100:.1f}%

LIQUIDITY:
- 24h Volume: ${market.volume_24h:,.0f}
- Open Interest: ${market.open_interest:,.0f}
- Market Closes: {market.close_date}

{technical_summary}

{sentiment_summary}

{news_summary}

{social_summary}

{portfolio_context}

TRADING POLICY CONSTRAINTS:
- Minimum confidence required: {self.policy['signal_selection']['min_confidence_score']}%
- Minimum expected return: {self.policy['signal_selection']['min_expected_return']}%
- Risk per trade: {settings.risk_per_trade_percent}%
- Maximum daily trades: {self.policy['risk_management']['max_daily_trades']}

ANALYSIS TASK:
=============
Based on all available information, provide a comprehensive trading analysis. Consider:

1. **Technical Signals**: What do the technical indicators tell us? RSI, momentum, volume trends?
2. **Sentiment Analysis**: What do quantitative sentiment scores reveal about market psychology?
3. **News Analysis**: What does recent news tell us? Are there clear trends or catalysts?
4. **Social Sentiment**: What is the public mood? Is there consensus or disagreement?
5. **Market Pricing**: Is the current implied probability accurate? Is there mispricing?
6. **Edge Identification**: Where is the edge? Why might the market be wrong?
7. **Risk Factors**: What could go wrong with this trade?
8. **Timing**: Is this the right time to enter? Should we wait for more information?

IMPORTANT: Pay special attention to technical indicators and sentiment scores - these are quantitative signals that complement your qualitative analysis.

REQUIRED OUTPUT FORMAT:
=====================
Provide your analysis in the following structure:

**RECOMMENDATION:** [LONG/SHORT/NO_TRADE]

**CONFIDENCE:** [0-100]%

**EXPECTED_RETURN:** [X]%

**REASONING:**
[Your detailed reasoning here - 2-3 paragraphs explaining your decision]

**KEY_FACTORS:**
- [Factor 1]
- [Factor 2]
- [Factor 3]

**RISK_FACTORS:**
- [Risk 1]
- [Risk 2]
- [Risk 3]

**MARKET_EDGE:**
[One clear sentence explaining why this trade has edge, or why it doesn't]

Be honest and conservative. If there isn't a clear edge, recommend NO_TRADE. We're looking for high-quality setups, not volume.
"""

        return prompt

    def _parse_signal_from_response(
        self,
        response: str,
        market_analysis: MarketAnalysis
    ) -> TradingSignal:
        """Parse Claude's response into a structured TradingSignal"""

        # Extract recommendation
        signal = "NO_TRADE"
        if "**RECOMMENDATION:**" in response:
            rec_line = response.split("**RECOMMENDATION:**")[1].split("\n")[0]
            rec_line = rec_line.strip().upper()
            if "LONG" in rec_line:
                signal = "LONG"
            elif "SHORT" in rec_line:
                signal = "SHORT"

        # Extract confidence
        confidence = 0.0
        if "**CONFIDENCE:**" in response:
            conf_line = response.split("**CONFIDENCE:**")[1].split("\n")[0]
            try:
                confidence = float(conf_line.strip().replace("%", ""))
            except:
                confidence = 0.0

        # Extract expected return
        expected_return = 0.0
        if "**EXPECTED_RETURN:**" in response:
            return_line = response.split("**EXPECTED_RETURN:**")[1].split("\n")[0]
            try:
                expected_return = float(return_line.strip().replace("%", ""))
            except:
                expected_return = 0.0

        # Extract reasoning
        reasoning = ""
        if "**REASONING:**" in response and "**KEY_FACTORS:**" in response:
            reasoning = response.split("**REASONING:**")[1].split("**KEY_FACTORS:**")[0].strip()

        # Extract key factors
        key_factors = []
        if "**KEY_FACTORS:**" in response and "**RISK_FACTORS:**" in response:
            factors_text = response.split("**KEY_FACTORS:**")[1].split("**RISK_FACTORS:**")[0]
            key_factors = [
                line.strip().lstrip("-").strip()
                for line in factors_text.split("\n")
                if line.strip().startswith("-")
            ]

        # Extract risk factors
        risk_factors = []
        if "**RISK_FACTORS:**" in response and "**MARKET_EDGE:**" in response:
            risks_text = response.split("**RISK_FACTORS:**")[1].split("**MARKET_EDGE:**")[0]
            risk_factors = [
                line.strip().lstrip("-").strip()
                for line in risks_text.split("\n")
                if line.strip().startswith("-")
            ]

        # Extract market edge
        market_edge = ""
        if "**MARKET_EDGE:**" in response:
            edge_text = response.split("**MARKET_EDGE:**")[1]
            # Take first paragraph
            market_edge = edge_text.split("\n\n")[0].strip()

        # Create signal
        return TradingSignal(
            ticker=market_analysis.market.ticker,
            signal=signal,
            confidence=confidence,
            expected_return=expected_return,
            reasoning=reasoning,
            key_factors=key_factors,
            risk_factors=risk_factors,
            market_edge=market_edge
        )


# Global instance
signal_agent = SignalSelectionAgent()
