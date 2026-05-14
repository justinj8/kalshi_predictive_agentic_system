"""
Policy & Self-Critic Agent
Final review and approval/blocking of trades using Claude 3.5 Sonnet
"""
from anthropic import Anthropic
import yaml
from src.utils.logger import get_logger
from src.orchestrator.state_models import (
    TradingSignal,
    PositionSizing,
    MarketAnalysis,
    PolicyDecision,
    TradingState
)
from config.settings import settings

logger = get_logger(__name__)


class PolicySelfCriticAgent:
    """AI-powered final review agent using Claude 3.5 Sonnet"""

    def __init__(self):
        """Initialize Policy & Self-Critic Agent"""
        self.client = Anthropic(api_key=settings.anthropic_api_key)
        self.model = settings.llm_model

        # Load trading policy
        with open("config/trading_policy.yaml", "r") as f:
            self.policy = yaml.safe_load(f)

    def review_trade(
        self,
        signal: TradingSignal,
        sizing: PositionSizing,
        market_analysis: MarketAnalysis,
        state: TradingState
    ) -> PolicyDecision:
        """
        Perform final review of proposed trade

        Args:
            signal: Trading signal
            sizing: Position sizing
            market_analysis: Market analysis
            state: Current trading state

        Returns:
            Policy decision to APPROVE or BLOCK
        """
        logger.info(f"Policy review for {signal.ticker} {signal.signal} trade...")

        # First, run rule-based checks
        rule_check, rule_reason = self._rule_based_checks(
            signal, sizing, market_analysis, state
        )

        if not rule_check:
            logger.warning(f"Trade blocked by rules: {rule_reason}")
            return PolicyDecision(
                ticker=signal.ticker,
                decision="BLOCK",
                confidence=100,
                reasoning=rule_reason,
                concerns=[rule_reason],
                checklist_results={},
                final_notes="Blocked by automated rule check"
            )

        # If rules pass, get Claude's review
        try:
            prompt = self._build_critic_prompt(
                signal, sizing, market_analysis, state
            )

            response = self.client.messages.create(
                model=self.model,
                max_tokens=settings.llm_max_tokens,
                temperature=0.3,  # Lower temperature for critical review
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ]
            )

            review_text = response.content[0].text
            logger.info(f"Claude critic review:\n{review_text}")

            # Parse decision
            decision = self._parse_decision(review_text, signal.ticker)

            logger.info(
                f"Policy decision: {decision.decision} "
                f"(Confidence: {decision.confidence}%)"
            )

            return decision

        except Exception as e:
            logger.error(f"Error in policy review: {e}")
            # Default to BLOCK on error (conservative)
            return PolicyDecision(
                ticker=signal.ticker,
                decision="BLOCK",
                confidence=100,
                reasoning=f"Error in policy review: {str(e)}",
                concerns=["Review system error"],
                checklist_results={},
                final_notes="Blocked due to system error"
            )

    def _rule_based_checks(
        self,
        signal: TradingSignal,
        sizing: PositionSizing,
        market_analysis: MarketAnalysis,
        state: TradingState
    ) -> tuple[bool, str]:
        """Run automated rule-based checks"""

        policy_rules = self.policy.get("policy_rules", {})
        signal_config = self.policy.get("signal_selection", {})

        # Check confidence threshold
        min_confidence = signal_config.get("min_confidence_score", 65)
        if signal.confidence < min_confidence:
            return False, f"Confidence {signal.confidence}% below minimum {min_confidence}%"

        # Check expected return threshold
        min_return = signal_config.get("min_expected_return", 10)
        if signal.expected_return < min_return:
            return False, f"Expected return {signal.expected_return}% below minimum {min_return}%"

        # Check position size
        if sizing.recommended_size == 0:
            return False, "Position size is zero"

        # Check fee-adjusted EV
        if sizing.fee_adjusted_ev_per_contract < settings.min_fee_adjusted_ev_per_contract:
            return (
                False,
                f"Fee-adjusted EV ${sizing.fee_adjusted_ev_per_contract:.4f}/contract "
                f"below minimum ${settings.min_fee_adjusted_ev_per_contract:.4f}"
            )

        # Check risk/reward ratio
        if sizing.risk_reward_ratio < 1.0:
            return False, f"Risk/reward ratio {sizing.risk_reward_ratio:.2f} is unfavorable (<1.0)"

        # Check market liquidity
        if market_analysis.market.open_interest < self.policy["risk_management"]["min_market_liquidity"]:
            return False, "Insufficient market liquidity"

        # Check spread before paying fees/slippage
        spread = (
            market_analysis.market.yes_ask - market_analysis.market.yes_bid
            if signal.signal == "LONG"
            else market_analysis.market.no_ask - market_analysis.market.no_bid
        )
        if spread * 100 > settings.order_max_spread_cents:
            return (
                False,
                f"Spread too wide: {spread * 100:.1f}c > {settings.order_max_spread_cents}c"
            )

        # Check if we have capacity for more trades
        if state.daily_trades >= self.policy["risk_management"]["max_daily_trades"]:
            return False, "Daily trade limit reached"

        # Check if we have capacity for more positions
        if state.open_positions >= self.policy["risk_management"]["max_concurrent_positions"]:
            return False, "Maximum concurrent positions reached"

        return True, "All rule-based checks passed"

    def _build_critic_prompt(
        self,
        signal: TradingSignal,
        sizing: PositionSizing,
        market_analysis: MarketAnalysis,
        state: TradingState
    ) -> str:
        """Build prompt for Claude's critical review"""

        market = market_analysis.market

        # Get self-critic checklist from policy
        checklist = self.policy.get("policy_rules", {}).get("self_critic_checklist", [])
        checklist_text = "\n".join([f"- {item}" for item in checklist])

        prompt = f"""You are a risk officer reviewing a proposed trade for a Kalshi predictive markets PAPER TRADING system. This is simulation mode for testing and learning.

PROPOSED TRADE:
==============
Market: {market.title}
Ticker: {market.ticker}
Direction: {signal.signal}
Quantity: {sizing.recommended_size} contracts @ ${market.yes_ask if signal.signal == "LONG" else market.no_ask:.2f}
Total Position Value: ${sizing.position_value:.2f}

SIGNAL ANALYSIS:
===============
Confidence: {signal.confidence}%
Expected Return: {signal.expected_return}%
Market Edge: {signal.market_edge}

Key Supporting Factors:
{chr(10).join([f"- {factor}" for factor in signal.key_factors])}

Identified Risks:
{chr(10).join([f"- {risk}" for risk in signal.risk_factors])}

Original Reasoning:
{signal.reasoning}

RISK PARAMETERS:
===============
Risk Amount: ${sizing.risk_amount:.2f} ({settings.risk_per_trade_percent}% of capital)
Maximum Loss: ${sizing.max_loss:.2f}
Stop Loss: ${sizing.stop_loss_price:.2f}
Take Profit: ${sizing.take_profit_price:.2f}
Risk/Reward Ratio: {sizing.risk_reward_ratio:.2f}:1

PORTFOLIO CONTEXT:
=================
Current Balance: ${state.current_balance:.2f}
Open Positions: {state.open_positions}
Daily Trades: {state.daily_trades} / {self.policy["risk_management"]["max_daily_trades"]}
Daily P&L: ${state.daily_pnl:.2f}

MARKET CONDITIONS:
=================
Current Price: YES ${market.yes_bid:.2f}-${market.yes_ask:.2f}, NO ${market.no_bid:.2f}-${market.no_ask:.2f}
Spread: {(market.yes_ask - market.yes_bid)*100:.1f}%
24h Volume: ${market.volume_24h:,.0f}
Open Interest: ${market.open_interest:,.0f}
Time to Close: {market.close_date}

NEWS CONTEXT:
============
{len(market_analysis.news_articles)} recent news articles found
{len(market_analysis.social_posts)} social media posts analyzed

CRITICAL REVIEW CHECKLIST:
===========================
{checklist_text}

YOUR TASK:
=========
Review this trade proposal. IMPORTANT CONTEXT:
- This is PAPER TRADING for testing - real money is NOT at risk
- We want to test the system's ability to identify and act on edges
- Statistical arbitrage (historical rates vs current pricing) IS a valid edge
- Short time horizons are acceptable - they reduce uncertainty

APPROVE the trade if:
- The edge is clearly articulated (e.g., historical probability >> market price)
- Risk management is reasonable (position size, stop loss)
- The trade thesis makes logical sense

BLOCK the trade ONLY if:
- The edge is unclear or the reasoning is fundamentally flawed
- Risk parameters violate policy limits
- There's a critical flaw that invalidates the thesis

REQUIRED OUTPUT FORMAT:
======================
**DECISION:** [APPROVE/BLOCK]

**CONFIDENCE:** [0-100]%

**REASONING:**
[2-3 paragraphs of analysis explaining your decision]

**CONCERNS:**
- [Concern 1]
- [Concern 2]
- [Concern 3]

**FINAL_NOTES:**
[Any additional notes or conditions]

Be balanced. APPROVE trades with clear edges even if there's some uncertainty (there always is in trading). We learn more by executing and tracking outcomes than by blocking everything.
"""

        return prompt

    def _parse_decision(self, response: str, ticker: str) -> PolicyDecision:
        """Parse Claude's review into a PolicyDecision"""

        # Extract decision
        decision = "BLOCK"  # Default to BLOCK
        if "**DECISION:**" in response:
            decision_line = response.split("**DECISION:**")[1].split("\n")[0]
            decision_line = decision_line.strip().upper()
            if "APPROVE" in decision_line:
                decision = "APPROVE"

        # Extract confidence
        confidence = 50.0
        if "**CONFIDENCE:**" in response:
            conf_line = response.split("**CONFIDENCE:**")[1].split("\n")[0]
            try:
                confidence = float(conf_line.strip().replace("%", ""))
            except:
                confidence = 50.0

        # Extract reasoning
        reasoning = ""
        if "**REASONING:**" in response and "**CONCERNS:**" in response:
            reasoning = response.split("**REASONING:**")[1].split("**CONCERNS:**")[0].strip()

        # Extract concerns
        concerns = []
        if "**CONCERNS:**" in response and "**FINAL_NOTES:**" in response:
            concerns_text = response.split("**CONCERNS:**")[1].split("**FINAL_NOTES:**")[0]
            concerns = [
                line.strip().lstrip("-").strip()
                for line in concerns_text.split("\n")
                if line.strip().startswith("-")
            ]

        # Extract final notes
        final_notes = ""
        if "**FINAL_NOTES:**" in response:
            final_notes = response.split("**FINAL_NOTES:**")[1].strip()

        return PolicyDecision(
            ticker=ticker,
            decision=decision,
            confidence=confidence,
            reasoning=reasoning,
            concerns=concerns,
            checklist_results={},
            final_notes=final_notes
        )


# Global instance
policy_agent = PolicySelfCriticAgent()
