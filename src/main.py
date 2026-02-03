"""
Main entry point for the Kalshi Predictive Markets Trading System
Runs the trading system on a 15-minute schedule
"""
import sys
import signal
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.interval import IntervalTrigger
from src.utils.logger import get_logger
from src.orchestrator.langgraph_flow import orchestrator
from src.database.models import init_database
from config.settings import settings

logger = get_logger(__name__)

# Global scheduler
scheduler = None


def run_trading_cycle():
    """Run one trading cycle"""
    logger.info("")
    logger.info("=" * 100)
    logger.info(f"TRADING CYCLE STARTED - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 100)

    try:
        result = orchestrator.run_trading_cycle()

        logger.info("")
        logger.info("CYCLE SUMMARY:")
        logger.info(f"  Markets Scanned: {result.get('markets_scanned', 0)}")
        logger.info(f"  Opportunities Found: {result.get('opportunities_found', 0)}")
        
        # List each top opportunity with recommendation
        top_opps = result.get('top_opportunities', [])
        if top_opps:
            logger.info("  Top Opportunities Analyzed:")
            for i, opp in enumerate(top_opps, 1):
                rec = opp.get('recommendation', 'N/A')
                conf = opp.get('edge_confidence', 0)
                yes_price = opp.get('yes_price', 0) * 100
                logger.info(f"    {i}. {opp.get('ticker', 'N/A')}: {opp.get('title', 'N/A')}")
                logger.info(f"       → BUY {rec} @ {yes_price:.0f}¢ (Confidence: {conf:.0f}%)")
        
        # List arbitrage opportunities
        arb_opps = result.get('arbitrage_opportunities', [])
        if arb_opps:
            logger.info(f"  Arbitrage Opportunities ({len(arb_opps)}):")
            for i, opp in enumerate(arb_opps[:5], 1):  # Show top 5
                markets = ', '.join(opp.get('markets', []))
                conf = opp.get('confidence', 0)
                logger.info(f"    {i}. [{opp.get('type', 'N/A')}] {markets}")
                logger.info(f"       → {opp.get('profit_pct', 0):.2f}% profit (Confidence: {conf:.0f}%)")
        
        logger.info(f"  Trades Executed: {result.get('trades_executed', 0)}")
        logger.info(f"  Trades Blocked: {result.get('trades_blocked', 0)}")

        if result.get('errors'):
            logger.error(f"  Errors: {len(result['errors'])}")
            for error in result['errors']:
                logger.error(f"    - {error}")

        if result.get('warnings'):
            logger.warning(f"  Warnings: {len(result['warnings'])}")

        logger.info("=" * 100)
        logger.info(f"Next cycle in {settings.scheduler_interval_minutes} minutes")
        logger.info("=" * 100)

    except Exception as e:
        logger.error(f"Error in trading cycle: {e}", exc_info=True)


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    logger.info("")
    logger.info("Shutdown signal received. Stopping trading system...")

    if scheduler:
        scheduler.shutdown(wait=False)

    logger.info("Trading system stopped.")
    sys.exit(0)


def main():
    """Main entry point"""
    global scheduler

    logger.info("")
    logger.info("*" * 100)
    logger.info("KALSHI PREDICTIVE MARKETS AGENTIC AI TRADING SYSTEM")
    logger.info("*" * 100)
    logger.info("")
    logger.info("Configuration:")
    logger.info(f"  Trading Mode: {settings.trading_mode.upper()}")
    logger.info(f"  Starting Capital: ${settings.starting_capital:,.2f}")
    logger.info(f"  Risk Per Trade: {settings.risk_per_trade_percent}%")
    logger.info(f"  LLM Model: {settings.llm_model}")
    logger.info(f"  Scheduler Interval: {settings.scheduler_interval_minutes} minutes")
    logger.info(f"  Max Daily Trades: {settings.max_daily_trades}")
    logger.info(f"  Max Daily Loss: {settings.max_daily_loss_percent}%")
    logger.info("")

    # Initialize database
    logger.info("Initializing database...")
    init_database()
    logger.info("Database initialized successfully")
    logger.info("")

    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Run first cycle immediately
    logger.info("Running initial trading cycle...")
    run_trading_cycle()

    # Set up scheduler
    logger.info("")
    logger.info(f"Starting scheduler (runs every {settings.scheduler_interval_minutes} minutes)...")
    scheduler = BlockingScheduler()

    scheduler.add_job(
        run_trading_cycle,
        trigger=IntervalTrigger(minutes=settings.scheduler_interval_minutes),
        id='trading_cycle',
        name='Kalshi Trading Cycle',
        replace_existing=True
    )

    try:
        logger.info("Trading system is running. Press Ctrl+C to stop.")
        logger.info("")
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Scheduler error: {e}", exc_info=True)


if __name__ == "__main__":
    main()
