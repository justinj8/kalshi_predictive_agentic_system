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
from src.database.models import TradingSession, get_session, get_db_session
from config.settings import settings

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

        # Bonding and arbitrage scans run in sequence
        workflow.add_edge("bonding_scan", "arbitrage_scan")
        workflow.add_edge("arbitrage_scan", "select_opportunity")

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
            from src.orchestrator.state_models import BondingOpportunity
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

        # If top_opportunities is empty, populate it
        if not state.top_opportunities and state.all_markets:
            # Rank markets
            top_markets = market_data_fetcher._rank_markets(state.all_markets, top_n=10)

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
        """Generate trading signal"""
        logger.info("Node: Generating Signal")

        if state.current_market:
            signal = signal_agent.generate_signal(state.current_market, state)
            state.trading_signal = signal

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
        """Policy review and approval"""
        logger.info("Node: Policy Review")

        if state.trading_signal and state.position_sizing and state.current_market:
            decision = policy_agent.review_trade(
                state.trading_signal,
                state.position_sizing,
                state.current_market,
                state
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
                    take_profit=state.position_sizing.take_profit_price
                )

                # Update balance
                state.current_balance -= result.total_cost

        return state

    def _finalize_node(self, state: TradingState) -> TradingState:
        """Finalize the trading cycle"""
        logger.info("Node: Finalizing")
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
        # TODO: Get from database/API
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
                errors="\\n".join(get_attr('errors', [])) if get_attr('errors') else None
            )

            session_db.add(trading_session)
            session_db.commit()
            session_db.close()

        except Exception as e:
            logger.error(f"Failed to record session: {e}")


# Global instance
orchestrator = TradingOrchestrator()
