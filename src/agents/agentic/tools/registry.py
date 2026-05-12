"""Anthropic tool schemas + dispatcher for the agentic core.

Tools are declared here as JSON schemas (Anthropic's `tool_use` format) and
implemented in sibling modules. A single dispatcher routes by tool name so
every agent can share the same executor closure.
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

from src.utils.logger import get_logger
from src.agents.agentic.tools import (
    news_tools,
    market_tools,
    memory_tools,
    stats_tools,
    sim_tools,
)

logger = get_logger(__name__)


# ----------------------------------------------------------------------------
# Tool schemas (Anthropic tool_use definitions)
# ----------------------------------------------------------------------------

SEARCH_NEWS_TOOL: Dict[str, Any] = {
    "name": "search_news",
    "description": (
        "Search recent news articles relevant to a query. "
        "Use for political, economic, market-moving headlines from NewsAPI / Alpha Vantage. "
        "Returns title, source, summary, published_at, url for up to `max_results` items."
    ),
    "input_schema": {
        "type": "object",
        "required": ["query"],
        "properties": {
            "query": {"type": "string", "description": "Search query - keywords or topic."},
            "lookback_hours": {"type": "integer", "minimum": 1, "maximum": 720, "default": 48},
            "max_results": {"type": "integer", "minimum": 1, "maximum": 20, "default": 8},
        },
    },
}

GET_MARKET_ORDERBOOK_TOOL: Dict[str, Any] = {
    "name": "get_market_orderbook",
    "description": (
        "Get the current order book for a Kalshi ticker: bids, asks, depth, and "
        "computed microstructure metrics (imbalance, depth-weighted mid)."
    ),
    "input_schema": {
        "type": "object",
        "required": ["ticker"],
        "properties": {
            "ticker": {"type": "string", "description": "Kalshi market ticker."},
        },
    },
}

GET_MARKET_HISTORY_TOOL: Dict[str, Any] = {
    "name": "get_market_history",
    "description": (
        "Recent trade history for a ticker: price series, volume, OHLC summary. "
        "Useful for momentum, volatility, recent price action context."
    ),
    "input_schema": {
        "type": "object",
        "required": ["ticker"],
        "properties": {
            "ticker": {"type": "string"},
            "limit": {"type": "integer", "minimum": 10, "maximum": 500, "default": 100},
        },
    },
}

GET_RELATED_MARKETS_TOOL: Dict[str, Any] = {
    "name": "get_related_markets",
    "description": (
        "Find related Kalshi markets by event-ticker prefix and title similarity. "
        "Returns up to k markets with their current prices and similarity scores. "
        "Use to spot complement arbitrage, basket plays, or cross-market signals."
    ),
    "input_schema": {
        "type": "object",
        "required": ["ticker"],
        "properties": {
            "ticker": {"type": "string"},
            "k": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
        },
    },
}

CALCULATE_TECHNICAL_INDICATORS_TOOL: Dict[str, Any] = {
    "name": "calculate_technical_indicators",
    "description": (
        "Compute RSI, momentum, volatility regime, volume profile, order book imbalance, "
        "and a qualitative overall_signal for a ticker."
    ),
    "input_schema": {
        "type": "object",
        "required": ["ticker"],
        "properties": {
            "ticker": {"type": "string"},
        },
    },
}

GET_HISTORICAL_BASE_RATE_TOOL: Dict[str, Any] = {
    "name": "get_historical_base_rate",
    "description": (
        "Approximate historical base-rate probability for a market category / question pattern, "
        "computed over resolved markets in our database. Returns sample_size and base_rate_pct."
    ),
    "input_schema": {
        "type": "object",
        "required": ["category"],
        "properties": {
            "category": {"type": "string", "description": "Market category (e.g. politics, economics)."},
            "question_pattern": {"type": "string", "description": "Optional keyword to filter titles."},
        },
    },
}

RECALL_LESSONS_TOOL: Dict[str, Any] = {
    "name": "recall_lessons",
    "description": (
        "Retrieve top-k previously-stored lessons most similar to a query. "
        "Lessons are written by the ReflectionAgent after positions close. "
        "Returns lesson id, type, text snippet, ticker, outcome_pnl, similarity."
    ),
    "input_schema": {
        "type": "object",
        "required": ["query"],
        "properties": {
            "query": {"type": "string", "description": "Description of the current situation."},
            "k": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
        },
    },
}

GET_CALIBRATION_CURVE_TOOL: Dict[str, Any] = {
    "name": "get_calibration_curve",
    "description": (
        "Look up the empirical hit rate for a given raw confidence bucket and return "
        "the multiplicative calibration factor that should be applied."
    ),
    "input_schema": {
        "type": "object",
        "required": ["confidence"],
        "properties": {
            "confidence": {"type": "number", "minimum": 0, "maximum": 100},
        },
    },
}

SIMULATE_OUTCOME_TOOL: Dict[str, Any] = {
    "name": "simulate_outcome",
    "description": (
        "Closed-form expected-value calculator for a binary Kalshi contract. "
        "Returns EV, variance, Kelly fraction, and recommended contracts for a given "
        "side / price / win_probability / capital."
    ),
    "input_schema": {
        "type": "object",
        "required": ["side", "price", "win_probability", "capital"],
        "properties": {
            "side": {"enum": ["YES", "NO"]},
            "price": {"type": "number", "minimum": 0.01, "maximum": 0.99},
            "win_probability": {"type": "number", "minimum": 0, "maximum": 1},
            "capital": {"type": "number", "minimum": 0},
        },
    },
}

# Final-output sinks (Claude calls these to deliver structured results).
# Their handlers in dispatch() simply return the input back so the loop knows
# they were called; the orchestrator extracts the call from AgentRunResult.final_tool_use.

SUBMIT_EVIDENCE_TOOL: Dict[str, Any] = {
    "name": "submit_evidence",
    "description": (
        "FINAL OUTPUT TOOL for ResearchAgent. Call exactly once with your structured "
        "evidence pack. After calling this, you are done researching."
    ),
    "input_schema": {
        "type": "object",
        "required": ["summary", "bull_case_points", "bear_case_points"],
        "properties": {
            "summary": {"type": "string", "minLength": 50},
            "bull_case_points": {"type": "array", "items": {"type": "string"}, "minItems": 1},
            "bear_case_points": {"type": "array", "items": {"type": "string"}, "minItems": 1},
            "base_rate_pct": {"type": "number", "minimum": 0, "maximum": 100},
            "market_implied_pct": {"type": "number", "minimum": 0, "maximum": 100},
            "edge_estimate_pct": {"type": "number"},
            "catalysts": {"type": "array", "items": {"type": "string"}},
            "risk_flags": {"type": "array", "items": {"type": "string"}},
            "news_highlights": {"type": "array", "items": {"type": "object"}},
            "web_findings": {"type": "array", "items": {"type": "object"}},
            "technical_summary": {"type": "object"},
            "related_markets": {"type": "array", "items": {"type": "object"}},
            "confidence_in_evidence": {"type": "number", "minimum": 0, "maximum": 1},
        },
    },
}

EMIT_TRADING_SIGNAL_TOOL: Dict[str, Any] = {
    "name": "emit_trading_signal",
    "description": (
        "FINAL OUTPUT TOOL for JudgeAgent. Call exactly once with your structured trading "
        "decision. After calling this, you are done."
    ),
    "input_schema": {
        "type": "object",
        "required": [
            "signal",
            "confidence",
            "calibrated_probability",
            "expected_return_pct",
            "kelly_fraction",
            "reasoning",
            "key_factors",
            "risk_factors",
            "market_edge",
            "invalidation_conditions",
            "debate_winner",
        ],
        "properties": {
            "signal": {"enum": ["LONG", "SHORT", "NO_TRADE"]},
            "confidence": {"type": "number", "minimum": 0, "maximum": 100},
            "calibrated_probability": {"type": "number", "minimum": 0, "maximum": 1},
            "expected_return_pct": {"type": "number"},
            "kelly_fraction": {"type": "number", "minimum": 0, "maximum": 0.25},
            "reasoning": {"type": "string", "minLength": 200},
            "key_factors": {"type": "array", "items": {"type": "string"}, "minItems": 2},
            "risk_factors": {"type": "array", "items": {"type": "string"}, "minItems": 2},
            "market_edge": {"type": "string"},
            "invalidation_conditions": {"type": "array", "items": {"type": "string"}},
            "lessons_applied": {"type": "array", "items": {"type": "integer"}},
            "debate_winner": {"enum": ["bull", "bear", "mixed", "none"]},
        },
    },
}


ALL_TOOL_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "search_news": SEARCH_NEWS_TOOL,
    "get_market_orderbook": GET_MARKET_ORDERBOOK_TOOL,
    "get_market_history": GET_MARKET_HISTORY_TOOL,
    "get_related_markets": GET_RELATED_MARKETS_TOOL,
    "calculate_technical_indicators": CALCULATE_TECHNICAL_INDICATORS_TOOL,
    "get_historical_base_rate": GET_HISTORICAL_BASE_RATE_TOOL,
    "recall_lessons": RECALL_LESSONS_TOOL,
    "get_calibration_curve": GET_CALIBRATION_CURVE_TOOL,
    "simulate_outcome": SIMULATE_OUTCOME_TOOL,
    "submit_evidence": SUBMIT_EVIDENCE_TOOL,
    "emit_trading_signal": EMIT_TRADING_SIGNAL_TOOL,
}


# ----------------------------------------------------------------------------
# Dispatcher
# ----------------------------------------------------------------------------


def dispatch(tool_name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    """Route a tool_use call to its implementation. Returns a JSON-able dict."""
    try:
        if tool_name == "search_news":
            return news_tools.search_news(**tool_input)
        if tool_name == "get_market_orderbook":
            return market_tools.get_market_orderbook(**tool_input)
        if tool_name == "get_market_history":
            return market_tools.get_market_history(**tool_input)
        if tool_name == "get_related_markets":
            return market_tools.get_related_markets(**tool_input)
        if tool_name == "calculate_technical_indicators":
            return market_tools.calculate_technical_indicators(**tool_input)
        if tool_name == "get_historical_base_rate":
            return stats_tools.get_historical_base_rate(**tool_input)
        if tool_name == "recall_lessons":
            return memory_tools.recall_lessons(**tool_input)
        if tool_name == "get_calibration_curve":
            return stats_tools.get_calibration_curve(**tool_input)
        if tool_name == "simulate_outcome":
            return sim_tools.simulate_outcome(**tool_input)
        if tool_name in ("submit_evidence", "emit_trading_signal"):
            # Final-output tools: just echo. The orchestrator extracts the
            # actual structured payload from AgentRunResult.final_tool_use.
            return {"ok": True, "received": True}
        return {"ok": False, "error": f"Unknown tool: {tool_name}"}
    except Exception as exc:  # noqa: BLE001
        logger.error(f"Tool '{tool_name}' failed: {exc}", exc_info=True)
        return {"ok": False, "error": str(exc)}


def build_tool_list(*names: str, include_web_search: bool = False) -> List[Dict[str, Any]]:
    """Build a tool list for an agent by name. Optionally appends web_search."""
    tools = [ALL_TOOL_SCHEMAS[n] for n in names if n in ALL_TOOL_SCHEMAS]
    if include_web_search:
        from src.agents.agentic.anthropic_client import WEB_SEARCH_TOOL
        tools.append(WEB_SEARCH_TOOL)
    return tools


def make_executor() -> Callable[[str, Dict[str, Any]], Dict[str, Any]]:
    """Convenience: return a closure usable as tool_executor in run_agent()."""
    return dispatch
