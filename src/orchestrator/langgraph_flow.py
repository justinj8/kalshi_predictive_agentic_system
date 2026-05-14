"""
LangGraph Orchestrator with Institutional Monitoring

Defines the state machine and flow control for the trading system
with comprehensive metrics and trace correlation.
"""
from typing import Dict, Any
from datetime import datetime
import uuid
import time
from langgraph.graph import StateGraph, END
from src.utils.logger import get_logger, set_cycle_id, set_trace_id
from src.orchestrator.state_models import TradingState
from src.agents.market_data_fetcher import market_data_fetcher
from src.agents.data_qa_circuit_breaker import circuit_breaker
from src.agents.signal_selection_agent import signal_agent
from src.agents.risk_allocation_agent import risk_agent
from src.agents.policy_self_critic_agent import policy_agent
from src.agents.execution_agent import execution_agent
from src.agents.position_manager import position_manager
from src.agents.bonding_strategy_agent import bonding_agent
from src.agents.arbitrage_detector import arbitrage_detector
from src.utils.edge_decay_tracker import edge_decay_tracker
from src.utils.external_odds_comparison import validate_edge_before_trading
from src.database.models import TradingSession, DecisionAudit, get_session, get_db_session
from config.settings import settings

# Agentic core — optional; importable even when the API key is absent.
from src.agents.agentic import research_agent as _research_mod
from src.agents.agentic import judge_agent as _judge_mod
from src.agents.agentic import calibration_agent as _calib_mod
from src.agents.agentic import memory_agent as _mem_mod
from src.agents.agentic import reflection_agent as _reflect_mod
from src.agents.agentic.cross_market_scout import run_scout as _run_scout
from src.agents.agentic.debate import bull_agent as _bull_mod
from src.agents.agentic.debate import bear_agent as _bear_mod
from src.agents.agentic.debate import red_team_agent as _red_team_mod
from src.orchestrator.state_models import (
    DebateTranscript,
    JudgeDecision,
    TradingSignal,
)

# Import metrics (optional - gracefully handle if not available)
try:
    from src.monitoring.metrics import metrics
    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False

logger = get_logger(__name__)


class TradingOrchestrator:
    """LangGraph-based orchestrator for the trading system"""

    def __init__(self):
        """Initialize orchestrator"""
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph state machine"""

        # Create workflow
        workflow = StateGraph(TradingState)

        # Add nodes (agents)
        workflow.add_node("update_positions", self._update_positions_node)
        workflow.add_node("fetch_markets", self._fetch_markets_node)
        workflow.add_node("circuit_breaker", self._circuit_breaker_node)
        workflow.add_node("bonding_scan", self._bonding_scan_node)
        workflow.add_node("arbitrage_scan", self._arbitrage_scan_node)
        workflow.add_node("cross_market_scout", self._cross_market_scout_node)
        workflow.add_node("select_opportunity", self._select_opportunity_node)
        workflow.add_node("enrich_data", self._enrich_data_node)
        workflow.add_node("generate_signal", self._generate_signal_node)
        workflow.add_node("calculate_sizing", self._calculate_sizing_node)
        workflow.add_node("policy_review", self._policy_review_node)
        workflow.add_node("execute_trade", self._execute_trade_node)
        workflow.add_node("finalize", self._finalize_node)

        # Set entry point
        workflow.set_entry_point("update_positions")

        # Define edges (flow)
        workflow.add_edge("update_positions", "fetch_markets")
        workflow.add_edge("fetch_markets", "circuit_breaker")

        # Circuit breaker decision
        workflow.add_conditional_edges(
            "circuit_breaker",
            self._should_continue_after_circuit_breaker,
            {
                "continue": "bonding_scan",
                "halt": "finalize"
            }
        )

        # Bonding and arbitrage scans run in sequence, then cross-market scout
        workflow.add_edge("bonding_scan", "arbitrage_scan")
        workflow.add_edge("arbitrage_scan", "cross_market_scout")
        workflow.add_edge("cross_market_scout", "select_opportunity")

        # Opportunity selection
        workflow.add_conditional_edges(
            "select_opportunity",
            self._has_opportunities,
            {
                "yes": "enrich_data",
                "no": "finalize"
            }
        )

        workflow.add_edge("enrich_data", "generate_signal")

        # Signal decision
        workflow.add_conditional_edges(
            "generate_signal",
            self._should_trade_signal,
            {
                "trade": "calculate_sizing",
                "no_trade": "select_opportunity",  # Try next opportunity
                "done": "finalize"  # No more opportunities
            }
        )

        workflow.add_edge("calculate_sizing", "policy_review")

        # Policy decision
        workflow.add_conditional_edges(
            "policy_review",
            self._is_trade_approved,
            {
                "approved": "execute_trade",
                "blocked": "select_opportunity",  # Try next opportunity
                "done": "finalize"  # No more opportunities
            }
        )

        workflow.add_edge("execute_trade", "select_opportunity")  # Continue with next opportunity
        workflow.add_edge("finalize", END)

        return workflow.compile()

    def run_trading_cycle(self) -> Dict[str, Any]:
        """
        Run one complete trading cycle with metrics

        Returns:
            Summary of the cycle
        """
        cycle_start = time.time()
        cycle_id = f"cycle_{uuid.uuid4().hex[:8]}"
        
        # Set trace/cycle IDs for log correlation
        set_cycle_id(cycle_id)
        set_trace_id(cycle_id)
        
        logger.info("=" * 80)
        logger.info("STARTING TRADING CYCLE")
        logger.info(f"Cycle ID: {cycle_id}")
        logger.info("=" * 80)

        # Initialize state
        initial_state = TradingState(
            session_id=f"session_{uuid.uuid4().hex[:8]}",
            timestamp=datetime.utcnow(),
            current_balance=self._get_current_balance(),
            open_positions=self._get_open_positions_count(),
            daily_trades=self._get_daily_trades_count(),
            daily_pnl=self._get_daily_pnl()
        )

        logger.info(f"Session ID: {initial_state.session_id}")
        logger.info(f"Starting Balance: ${initial_state.current_balance:.2f}")
        logger.info(f"Open Positions: {initial_state.open_positions}")
        logger.info(f"Daily Trades: {initial_state.daily_trades}")
        logger.info(f"Daily P&L: ${initial_state.daily_pnl:.2f}")
        
        # Update portfolio metrics
        if METRICS_AVAILABLE:
            metrics.positions_open.set(initial_state.open_positions)
            metrics.portfolio_value.set(initial_state.current_balance)
            metrics.daily_pnl.set(initial_state.daily_pnl)

        # Run the graph
        try:
            final_state = self.graph.invoke(initial_state)
            
            # LangGraph returns a dict, handle both dict and TradingState
            def get_state_attr(state, attr, default=None):
                if isinstance(state, dict):
                    return state.get(attr, default)
                return getattr(state, attr, default)

            # Record session
            self._record_session(final_state)

            logger.info("=" * 80)
            logger.info("TRADING CYCLE COMPLETE")
            logger.info(f"Markets Scanned: {get_state_attr(final_state, 'markets_scanned', 0)}")
            logger.info(f"Opportunities Found: {get_state_attr(final_state, 'opportunities_found', 0)}")
            logger.info(f"Bonding Opportunities: {len(get_state_attr(final_state, 'bonding_opportunities', []))}")
            logger.info(f"Arbitrage Opportunities: {len(get_state_attr(final_state, 'arbitrage_opportunities', []))}")
            logger.info(f"Trades Executed: {get_state_attr(final_state, 'trades_executed', 0)}")
            logger.info(f"Bonds Executed: {get_state_attr(final_state, 'bonds_executed', 0)}")
            logger.info(f"Arbitrages Executed: {get_state_attr(final_state, 'arbitrages_executed', 0)}")
            logger.info(f"Trades Blocked: {get_state_attr(final_state, 'trades_blocked', 0)}")
            logger.info("=" * 80)
            
            # Record cycle metrics
            cycle_duration = time.time() - cycle_start
            if METRICS_AVAILABLE:
                metrics.record_cycle("success", cycle_duration)
                # Record signals
                for _ in range(get_state_attr(final_state, 'trades_executed', 0)):
                    metrics.trades_total.inc(side="any", market="any", status="executed")
                for _ in range(get_state_attr(final_state, 'trades_blocked', 0)):
                    metrics.trades_total.inc(side="any", market="any", status="blocked")

            return {
                "session_id": get_state_attr(final_state, 'session_id', ''),
                "cycle_id": cycle_id,
                "cycle_duration_seconds": cycle_duration,
                "markets_scanned": get_state_attr(final_state, 'markets_scanned', 0),
                "opportunities_found": get_state_attr(final_state, 'opportunities_found', 0),
                "bonding_opportunities_found": len(get_state_attr(final_state, 'bonding_opportunities', [])),
                "arbitrage_opportunities_found": len(get_state_attr(final_state, 'arbitrage_opportunities', [])),
                "trades_executed": get_state_attr(final_state, 'trades_executed', 0),
                "bonds_executed": get_state_attr(final_state, 'bonds_executed', 0),
                "arbitrages_executed": get_state_attr(final_state, 'arbitrages_executed', 0),
                "trades_blocked": get_state_attr(final_state, 'trades_blocked', 0),
                "markets_analyzed": get_state_attr(final_state, 'markets_analyzed', 0),
                "llm_calls_used": get_state_attr(final_state, 'llm_calls_used', 0),
                "errors": get_state_attr(final_state, 'errors', []),
                "warnings": get_state_attr(final_state, 'warnings', []),
                # Include opportunity details for summary display
                "top_opportunities": [
                    {
                        "ticker": opp.market.ticker,
                        "title": opp.market.title[:50],
                        "sentiment": getattr(opp, 'combined_sentiment', 0),
                        "yes_price": opp.market.yes_ask,
                        "no_price": opp.market.no_ask,
                        # Recommend based on price - low YES price = buy YES opportunity
                        "recommendation": "YES" if opp.market.yes_ask < 0.50 else "NO" if opp.market.no_ask < 0.50 else "HOLD",
                        # Estimate confidence from price edge (how far from 50%)
                        "edge_confidence": min(90, 50 + abs(0.50 - opp.market.yes_ask) * 100)
                    }
                    for opp in get_state_attr(final_state, 'top_opportunities', [])
                ],
                "arbitrage_opportunities": [
                    {
                        "type": opp.type,
                        "markets": opp.markets,
                        "profit_pct": opp.profit_pct,
                        "confidence": opp.confidence,
                        "recommendation": f"Buy {opp.markets[0] if opp.markets else 'N/A'}"
                    }
                    for opp in get_state_attr(final_state, 'arbitrage_opportunities', [])
                ]
            }

        except Exception as e:
            cycle_duration = time.time() - cycle_start
            logger.error(f"Error in trading cycle: {e}", exc_info=True)
            
            # Record failed cycle
            if METRICS_AVAILABLE:
                metrics.record_cycle("error", cycle_duration)
            
            return {
                "error": str(e),
                "cycle_id": cycle_id,
                "cycle_duration_seconds": cycle_duration
            }

    # Node implementations
    def _update_positions_node(self, state: TradingState) -> TradingState:
        """Update all open positions"""
        logger.info("Node: Updating Positions")
        return position_manager.update_positions(state)

    def _fetch_markets_node(self, state: TradingState) -> TradingState:
        """Fetch all markets"""
        logger.info("Node: Fetching Markets")
        return market_data_fetcher.fetch_all_markets(state)

    def _circuit_breaker_node(self, state: TradingState) -> TradingState:
        """Run circuit breaker checks"""
        logger.info("Node: Circuit Breaker")
        return circuit_breaker.validate_and_check(state)

    def _bonding_scan_node(self, state: TradingState) -> TradingState:
        """Scan for bonding opportunities (high-probability contracts)"""
        logger.info("Node: Bonding Strategy Scan")

        # Bonding agent scans all markets and updates state with opportunities
        state = bonding_agent.scan_for_bonds(state)

        # Convert opportunities to proper format
        bonding_opps = state.debug_info.get('bonding_opportunities', [])
        if bonding_opps:
            from src.orchestrator.state_models import BondingOpportunity, MarketAnalysis
            state.bonding_opportunities = [
                BondingOpportunity(
                    market=opp['market'],
                    side=opp['metrics']['side'],
                    price=opp['metrics']['price'],
                    return_pct=opp['metrics']['return_pct'],
                    days_to_close=opp['metrics']['days_to_close'],
                    daily_return=opp['metrics']['daily_return'],
                    annual_return=opp['metrics']['annual_return'],
                    liquidity=opp['metrics']['liquidity'],
                    spread=opp['metrics']['spread']
                )
                for opp in bonding_opps
            ]

            # Bonding candidates often fail the normal probability filter by
            # design, so place them ahead of ordinary candidates for analysis.
            existing = {opp.market.ticker for opp in state.top_opportunities}
            bond_analyses = [
                MarketAnalysis(market=opp.market)
                for opp in state.bonding_opportunities
                if opp.market.ticker not in existing
            ]
            if bond_analyses:
                state.top_opportunities = bond_analyses + state.top_opportunities
                state.opportunities_found = len(state.top_opportunities)

        return state

    def _arbitrage_scan_node(self, state: TradingState) -> TradingState:
        """Scan for arbitrage opportunities"""
        logger.info("Node: Arbitrage Detection Scan")

        # Arbitrage detector scans all markets for mispricings
        state = arbitrage_detector.scan_for_arbitrage(state)
        
        # Get opportunities from debug_info
        opportunities = state.debug_info.get('arbitrage_opportunities', [])

        if opportunities:
            from src.orchestrator.state_models import ArbitrageOpportunity
            state.arbitrage_opportunities = [
                ArbitrageOpportunity(
                    type=opp['type'],
                    # Extract ticker string from MarketData if present
                    markets=[opp['market'].ticker if hasattr(opp.get('market'), 'ticker') else str(opp.get('market', ''))] if opp.get('market') else [],
                    profit_pct=opp['profit_pct'],
                    trades=opp.get('trades', []),
                    execution_complexity='low',
                    confidence=min(95, 50 + opp['profit_pct'] * 10)  # Higher profit = higher confidence
                )
                for opp in opportunities
            ]

            logger.info(f"Found {len(opportunities)} arbitrage opportunities")

        return state

    def _select_opportunity_node(self, state: TradingState) -> TradingState:
        """Select next opportunity to analyze"""
        logger.info("Node: Selecting Opportunity")

        capacity_ok, capacity_reason = self._has_capacity_for_analysis(state)
        if not capacity_ok:
            logger.info(f"No analysis capacity: {capacity_reason}")
            state.warnings.append(capacity_reason)
            state.current_market = None
            state.top_opportunities = []
            return state

        # If top_opportunities is empty, populate it
        if not state.top_opportunities and state.filtered_markets:
            # Rank only markets that passed policy filters.
            top_markets = market_data_fetcher._rank_markets(
                state.filtered_markets,
                top_n=settings.max_markets_per_cycle,
            )

            # Create MarketAnalysis objects (without enrichment yet)
            from src.orchestrator.state_models import MarketAnalysis
            state.top_opportunities = [
                MarketAnalysis(market=market)
                for market in top_markets
            ]

        # Select next opportunity
        if state.top_opportunities:
            state.current_market = state.top_opportunities.pop(0)
            logger.info(f"Selected: {state.current_market.market.ticker}")
        else:
            state.current_market = None
            logger.info("No more opportunities")

        return state

    def _enrich_data_node(self, state: TradingState) -> TradingState:
        """Enrich market data with news and social"""
        logger.info("Node: Enriching Data")

        if state.current_market:
            enriched = market_data_fetcher.enrich_market_data(
                state.current_market.market,
                fetch_news=True,
                fetch_social=True
            )
            state.current_market = enriched

        return state

    def _generate_signal_node(self, state: TradingState) -> TradingState:
        """Generate trading signal.

        When `settings.agentic_decision_path` is True (default), runs the full
        multi-agent core: memory_recall -> research -> debate (bull/bear/red_team)
        -> calibration -> judge, and persists a DecisionAudit. Otherwise falls
        back to the legacy single-shot signal_agent.
        """
        logger.info("Node: Generating Signal")

        if not state.current_market:
            return state

        capacity_ok, capacity_reason = self._has_capacity_for_analysis(state)
        if not capacity_ok:
            logger.info(f"Skipping signal generation: {capacity_reason}")
            state.trading_signal = self._no_trade_signal(
                state.current_market.market.ticker,
                capacity_reason,
            )
            return state

        state.markets_analyzed += 1

        if settings.agentic_decision_path:
            self._run_agentic_decision(state)
            state.llm_calls_used += 5
            # Optional shadow run of legacy pipeline for comparison.
            if settings.shadow_legacy:
                try:
                    legacy_signal = signal_agent.generate_signal(state.current_market, state)
                    state.legacy_signal_shadow = legacy_signal
                    state.llm_calls_used += 1
                except Exception as exc:
                    logger.warning(f"Legacy shadow signal failed: {exc}")
        else:
            # Pure legacy path.
            state.decision_path = "legacy"
            signal = signal_agent.generate_signal(state.current_market, state)
            state.trading_signal = signal
            state.llm_calls_used += 1

        self._record_edge_for_signal(state)

        return state

    # ----- Agentic decision core --------------------------------------------------

    def _run_agentic_decision(self, state: TradingState) -> None:
        """Multi-agent analysis & decision (mutates state in-place)."""
        ma = state.current_market
        ticker = ma.market.ticker
        logger.info(f"  [Agentic] ticker={ticker}")

        # 1. Memory recall
        try:
            state.recalled_lessons = _mem_mod.recall_for_market(ma)
        except Exception as exc:
            logger.warning(f"  [Agentic] memory recall failed: {exc}")
            state.recalled_lessons = []

        # 2. Research (tool-use loop)
        try:
            pack = _research_mod.research_agent.run(ma, state.recalled_lessons)
        except Exception as exc:
            logger.error(f"  [Agentic] research failed: {exc}", exc_info=True)
            pack = None
        state.evidence_pack = pack

        if pack is None:
            state.trading_signal = self._no_trade_signal(ticker, "Research failed.")
            self._persist_audit(state, calibrated={}, transcript=None, judge=None)
            return

        # 3. Debate — Bull / Bear / Red-Team in parallel via threads
        transcript = self._run_debate(pack, state.recalled_lessons)
        state.debate_transcript = transcript

        # 4. Calibration
        try:
            calibrated = _calib_mod.calibrate(pack, transcript)
            state.calibrated_probability = calibrated.get("calibrated_probability")
        except Exception as exc:
            logger.warning(f"  [Agentic] calibration failed: {exc}")
            calibrated = {"calibrated_probability": 0.5}
            state.calibrated_probability = 0.5

        # 5. Judge (Opus + extended thinking)
        try:
            decision: JudgeDecision = _judge_mod.judge_agent.run(
                market_analysis=ma,
                pack=pack,
                transcript=transcript,
                calibrated=calibrated,
                recalled_lessons=state.recalled_lessons,
                state=state,
            )
        except Exception as exc:
            logger.error(f"  [Agentic] judge failed: {exc}", exc_info=True)
            state.trading_signal = self._no_trade_signal(ticker, f"Judge failed: {exc}")
            self._persist_audit(state, calibrated=calibrated, transcript=transcript, judge=None)
            return

        state.judge_decision = decision
        state.trading_signal = self._judge_to_signal(decision, ma)

        # 6. Persist audit
        self._persist_audit(state, calibrated=calibrated, transcript=transcript, judge=decision)

    def _run_debate(self, pack, recalled_lessons) -> DebateTranscript:
        """Run Bull / Bear / Red-Team concurrently."""
        from concurrent.futures import ThreadPoolExecutor

        transcript = DebateTranscript(ticker=pack.ticker)
        if not settings.enable_debate:
            return transcript

        with ThreadPoolExecutor(max_workers=3) as ex:
            f_bull = ex.submit(_bull_mod.run_bull, pack)
            f_bear = ex.submit(_bear_mod.run_bear, pack)
            f_red = ex.submit(_red_team_mod.run_red_team, pack, recalled_lessons)

            try:
                transcript.bull = f_bull.result()
            except Exception as exc:
                logger.warning(f"  [Agentic] bull agent failed: {exc}")
            try:
                transcript.bear = f_bear.result()
            except Exception as exc:
                logger.warning(f"  [Agentic] bear agent failed: {exc}")
            try:
                transcript.red_team = f_red.result()
            except Exception as exc:
                logger.warning(f"  [Agentic] red-team agent failed: {exc}")

        return transcript

    @staticmethod
    def _no_trade_signal(ticker: str, reason: str) -> TradingSignal:
        return TradingSignal(
            ticker=ticker,
            signal="NO_TRADE",
            confidence=0,
            expected_return=0,
            reasoning=reason,
            key_factors=[],
            risk_factors=[reason],
            market_edge="None",
        )

    @staticmethod
    def _judge_to_signal(decision: JudgeDecision, ma) -> TradingSignal:
        return TradingSignal(
            ticker=decision.ticker,
            signal=decision.signal,
            confidence=decision.confidence,
            expected_return=decision.expected_return_pct,
            reasoning=decision.reasoning,
            key_factors=decision.key_factors,
            risk_factors=decision.risk_factors,
            market_edge=decision.market_edge,
        )

    def _persist_audit(self, state: TradingState, *, calibrated, transcript, judge) -> None:
        """Persist a DecisionAudit row for forensic review and shadow comparison."""
        try:
            with get_db_session() as session:
                row = DecisionAudit(
                    session_id=state.session_id,
                    ticker=state.current_market.market.ticker if state.current_market else "",
                    decision_path=state.decision_path,
                    evidence_pack=state.evidence_pack.dict() if state.evidence_pack else None,
                    debate_transcript=transcript.dict() if transcript else None,
                    calibrated_probability=state.calibrated_probability,
                    recalled_lesson_ids=[l.id for l in state.recalled_lessons],
                    judge_decision=judge.dict() if judge else None,
                    legacy_signal=(
                        state.legacy_signal_shadow.dict()
                        if state.legacy_signal_shadow
                        else None
                    ),
                    thinking_tokens_used=(judge.thinking_tokens_used if judge else 0),
                    outcome_label="open",
                )
                session.add(row)
        except Exception as exc:
            logger.warning(f"Failed to persist DecisionAudit: {exc}")

    # ------------------------------------------------------------------------------

    def _cross_market_scout_node(self, state: TradingState) -> TradingState:
        """Scout related markets + complement arbitrage opportunities."""
        logger.info("Node: Cross-Market Scout")
        try:
            return _run_scout(state)
        except Exception as exc:
            logger.warning(f"Cross-market scout failed: {exc}")
            return state

    def _calculate_sizing_node(self, state: TradingState) -> TradingState:
        """Calculate position sizing"""
        logger.info("Node: Calculating Position Sizing")

        if state.trading_signal and state.current_market:
            sizing = risk_agent.calculate_position_size(
                state.trading_signal,
                state.current_market,
                state
            )
            state.position_sizing = sizing

        return state

    def _policy_review_node(self, state: TradingState) -> TradingState:
        """Final policy gate.

        Under the agentic decision path the JudgeAgent has already done the
        deep self-critique, so this node enforces only the deterministic rule
        checks (liquidity, daily caps, confidence floor, etc.). Under the
        legacy path we delegate to the full single-shot policy_agent.
        """
        logger.info("Node: Policy Gate")

        if not (state.trading_signal and state.position_sizing and state.current_market):
            return state

        if settings.agentic_decision_path:
            ok, reason = policy_agent._rule_based_checks(
                state.trading_signal,
                state.position_sizing,
                state.current_market,
                state,
            )
            if ok:
                ok, reason = self._edge_external_fee_gate(state)
            from src.orchestrator.state_models import PolicyDecision
            state.policy_decision = PolicyDecision(
                ticker=state.trading_signal.ticker,
                decision="APPROVE" if ok else "BLOCK",
                confidence=100.0 if ok else 100.0,
                reasoning=reason,
                concerns=[] if ok else [reason],
                checklist_results={},
                final_notes="Agentic path: deterministic gate after Judge.",
            )
            if not ok:
                state.trades_blocked += 1
        else:
            decision = policy_agent.review_trade(
                state.trading_signal,
                state.position_sizing,
                state.current_market,
                state,
            )
            state.policy_decision = decision
            if decision.decision == "BLOCK":
                state.trades_blocked += 1

        return state

    def _execute_trade_node(self, state: TradingState) -> TradingState:
        """Execute approved trade"""
        logger.info("Node: Executing Trade")

        if (state.trading_signal and state.position_sizing and
            state.current_market and state.policy_decision):

            result = execution_agent.execute_trade(
                state.trading_signal,
                state.position_sizing,
                state.current_market,
                state
            )
            state.execution_result = result

            if result.success:
                state.trades_executed += 1
                state.daily_trades += 1

                # Create position
                position_manager.create_position(
                    ticker=state.trading_signal.ticker,
                    market_title=state.current_market.market.title,
                    category=state.current_market.market.category,
                    side=state.trading_signal.signal.lower(),
                    quantity=result.filled_quantity,
                    entry_price=result.filled_price,
                    stop_loss=state.position_sizing.stop_loss_price,
                    take_profit=state.position_sizing.take_profit_price,
                    position_id=result.position_id,
                )

                # Update balance
                state.current_balance -= result.total_cost

        return state

    def _finalize_node(self, state: TradingState) -> TradingState:
        """Finalize the trading cycle.

        Includes the post-cycle ReflectionAgent sweep: any positions closed
        during the cycle get a lesson written to the memory store.
        """
        logger.info("Node: Finalizing")

        # Mirror decision_path onto state for session-row stamping below.
        state.decision_path = "agentic_v1" if settings.agentic_decision_path else "legacy"

        if settings.enable_memory and settings.agentic_decision_path:
            try:
                written = _reflect_mod.reflect_on_closed_positions(state)
                if written:
                    logger.info(f"Reflection wrote {written} new lesson(s) to memory.")
            except Exception as exc:
                logger.warning(f"Reflection sweep failed: {exc}")

        return state

    # Conditional edge functions
    def _should_continue_after_circuit_breaker(self, state: TradingState) -> str:
        """Decide if trading should continue after circuit breaker"""
        if state.circuit_breaker and state.circuit_breaker.triggered:
            logger.warning("Circuit breaker triggered - halting trading")
            return "halt"
        return "continue"

    def _has_opportunities(self, state: TradingState) -> str:
        """Check if there are opportunities to analyze"""
        if state.current_market or state.top_opportunities:
            return "yes"
        return "no"

    def _should_trade_signal(self, state: TradingState) -> str:
        """Check if signal says to trade"""
        if not state.trading_signal:
            return "done"

        if state.trading_signal.signal == "NO_TRADE":
            logger.info("Signal is NO_TRADE, trying next opportunity")
            if state.top_opportunities:
                return "no_trade"
            else:
                return "done"

        return "trade"

    def _has_capacity_for_analysis(self, state: TradingState) -> tuple[bool, str]:
        """Avoid LLM spend when deterministic caps already prevent trading."""
        if state.daily_trades >= settings.max_daily_trades:
            return False, f"Daily trade limit reached ({state.daily_trades}/{settings.max_daily_trades})"

        max_positions = 5
        try:
            max_positions = int(
                policy_agent.policy.get("risk_management", {}).get(
                    "max_concurrent_positions", max_positions
                )
            )
        except Exception:
            pass
        if state.open_positions >= max_positions:
            return False, f"Maximum concurrent positions reached ({state.open_positions}/{max_positions})"

        if state.markets_analyzed >= settings.max_markets_per_cycle:
            return False, f"Market analysis budget reached ({state.markets_analyzed}/{settings.max_markets_per_cycle})"

        if state.llm_calls_used >= settings.max_llm_calls_per_cycle:
            return False, f"LLM call budget reached ({state.llm_calls_used}/{settings.max_llm_calls_per_cycle})"

        return True, "capacity available"

    def _record_edge_for_signal(self, state: TradingState) -> None:
        """Record edge immediately after a directional signal for pre-execution decay checks."""
        if not (state.current_market and state.trading_signal):
            return
        if state.trading_signal.signal == "NO_TRADE":
            return

        market = state.current_market.market
        signal = state.trading_signal
        side_price = market.yes_ask if signal.signal == "LONG" else market.no_ask

        if state.judge_decision and state.judge_decision.calibrated_probability is not None:
            fair_value = (
                state.judge_decision.calibrated_probability
                if signal.signal == "LONG"
                else 1.0 - state.judge_decision.calibrated_probability
            )
        else:
            fair_value = max(0.0, min(1.0, signal.confidence / 100.0))

        edge_decay_tracker.record_edge(
            ticker=signal.ticker,
            signal=signal.signal,
            our_fair_value=fair_value,
            market_price=side_price,
            confidence=signal.confidence,
            reasoning=signal.market_edge,
        )

    def _edge_external_fee_gate(self, state: TradingState) -> tuple[bool, str]:
        """Apply fee-adjusted EV, external consensus, and edge-decay gates."""
        signal = state.trading_signal
        sizing = state.position_sizing
        market = state.current_market.market

        if sizing.fee_adjusted_ev_per_contract < settings.min_fee_adjusted_ev_per_contract:
            return (
                False,
                f"Fee-adjusted EV ${sizing.fee_adjusted_ev_per_contract:.4f}/contract "
                f"below threshold ${settings.min_fee_adjusted_ev_per_contract:.4f}",
            )

        proceed, reason, _ = validate_edge_before_trading(
            ticker=market.ticker,
            title=market.title,
            category=market.category,
            our_confidence=signal.confidence,
            our_signal=signal.signal,
        )
        if not proceed:
            return False, reason

        current_price = sizing.entry_limit_price or (
            market.yes_ask if signal.signal == "LONG" else market.no_ask
        )
        persistence = edge_decay_tracker.check_edge_persistence(
            signal.ticker,
            current_price,
        )
        if not persistence.still_valid:
            return False, persistence.explanation

        if persistence.recommendation == "reduced_size":
            original_size = sizing.recommended_size
            sizing.recommended_size = max(1, sizing.recommended_size // 2)
            sizing.position_value = sizing.recommended_size * (sizing.entry_limit_price or current_price)
            sizing.estimated_fees = (
                sizing.estimated_fees * sizing.recommended_size / original_size
                if original_size > 0
                else sizing.estimated_fees
            )
            logger.info(
                f"Reduced position size for {signal.ticker}: "
                f"{original_size} -> {sizing.recommended_size} contracts"
            )

        return True, "All deterministic, external, fee, and edge-decay gates passed"

    def _is_trade_approved(self, state: TradingState) -> str:
        """Check if policy approved the trade"""
        if not state.policy_decision:
            return "done"

        if state.policy_decision.decision == "APPROVE":
            logger.info("Trade APPROVED by policy")
            return "approved"
        else:
            logger.info("Trade BLOCKED by policy")
            if state.top_opportunities:
                return "blocked"
            else:
                return "done"

    # Helper methods
    def _get_current_balance(self) -> float:
        """Get current account balance"""
        try:
            with get_db_session() as session:
                from src.database.models import Trade
                entries = session.query(Trade).filter(Trade.is_entry == True).all()
                exits = session.query(Trade).filter(Trade.is_entry == False).all()
                cash_spent = sum(t.total_cost or 0.0 for t in entries)
                cash_received = sum(t.total_cost or 0.0 for t in exits)
                return settings.starting_capital - cash_spent + cash_received
        except Exception:
            return settings.starting_capital

    def _get_open_positions_count(self) -> int:
        """Get number of open positions"""
        try:
            with get_db_session() as session:
                from src.database.models import Position
                count = session.query(Position).filter(Position.is_open == True).count()
                return count
        except:
            return 0

    def _get_daily_trades_count(self) -> int:
        """Get number of trades today"""
        try:
            with get_db_session() as session:
                from src.database.models import Trade
                from datetime import date
                count = session.query(Trade).filter(
                    Trade.timestamp >= datetime.combine(date.today(), datetime.min.time())
                ).count()
                return count
        except:
            return 0

    def _get_daily_pnl(self) -> float:
        """Get P&L for today"""
        try:
            with get_db_session() as session:
                from src.database.models import Trade
                from datetime import date
                trades = session.query(Trade).filter(
                    Trade.timestamp >= datetime.combine(date.today(), datetime.min.time()),
                    Trade.realized_pnl.isnot(None)
                ).all()
                pnl = sum([t.realized_pnl for t in trades])
                return pnl
        except:
            return 0.0

    def _record_session(self, state):
        """Record trading session in database"""
        try:
            session_db = get_session()
            
            # Helper to handle dict or object state
            def get_attr(attr, default=None):
                if isinstance(state, dict):
                    return state.get(attr, default)
                return getattr(state, attr, default)

            # Get circuit breaker info
            circuit_breaker = get_attr('circuit_breaker')
            cb_triggered = False
            cb_reason = None
            if circuit_breaker:
                if isinstance(circuit_breaker, dict):
                    cb_triggered = circuit_breaker.get('triggered', False)
                    cb_reason = circuit_breaker.get('reason')
                else:
                    cb_triggered = getattr(circuit_breaker, 'triggered', False)
                    cb_reason = getattr(circuit_breaker, 'reason', None)
            
            # Get opportunities for logging
            top_opps = get_attr('top_opportunities', [])
            opp_tickers = []
            if top_opps:
                for opp in top_opps:
                    if isinstance(opp, dict):
                        market = opp.get('market', {})
                        opp_tickers.append(market.get('ticker', '') if isinstance(market, dict) else getattr(market, 'ticker', ''))
                    else:
                        opp_tickers.append(getattr(opp.market, 'ticker', '') if hasattr(opp, 'market') else '')

            trading_session = TradingSession(
                timestamp=get_attr('timestamp', datetime.utcnow()),
                markets_scanned=get_attr('markets_scanned', 0),
                signals_generated=get_attr('opportunities_found', 0),
                trades_executed=get_attr('trades_executed', 0),
                starting_balance=settings.starting_capital,
                ending_balance=get_attr('current_balance', settings.starting_capital),
                session_pnl=get_attr('daily_pnl', 0.0),
                circuit_breaker_triggered=cb_triggered,
                circuit_breaker_reason=cb_reason,
                opportunities_analyzed=opp_tickers,
                execution_log=f"Executed {get_attr('trades_executed', 0)} trades, blocked {get_attr('trades_blocked', 0)}",
                errors="\\n".join(get_attr('errors', [])) if get_attr('errors') else None,
                decision_path=get_attr('decision_path', 'agentic_v1'),
            )

            session_db.add(trading_session)
            session_db.commit()
            session_db.close()

        except Exception as e:
            logger.error(f"Failed to record session: {e}")


# Global instance
orchestrator = TradingOrchestrator()
