"""Unit tests for the agentic tools registry + simulation tools.

These tests do not require network access or an Anthropic API key; they only
exercise the local tool wrappers and the schema/dispatch surface.
"""
from __future__ import annotations

import pytest

from src.agents.agentic.tools import registry
from src.agents.agentic.tools import sim_tools


def test_all_tools_have_schemas():
    expected = {
        "search_news",
        "get_market_orderbook",
        "get_market_history",
        "get_related_markets",
        "calculate_technical_indicators",
        "get_historical_base_rate",
        "recall_lessons",
        "get_calibration_curve",
        "simulate_outcome",
        "submit_evidence",
        "emit_trading_signal",
    }
    assert expected.issubset(set(registry.ALL_TOOL_SCHEMAS.keys()))


def test_tool_schemas_have_required_fields():
    for name, schema in registry.ALL_TOOL_SCHEMAS.items():
        assert schema["name"] == name, f"name mismatch in {name}"
        assert "description" in schema and schema["description"], f"{name} missing description"
        assert "input_schema" in schema, f"{name} missing input_schema"
        sch = schema["input_schema"]
        assert sch["type"] == "object", f"{name} input_schema not object"
        assert "properties" in sch, f"{name} missing properties"


def test_dispatch_unknown_tool_returns_error():
    out = registry.dispatch("does_not_exist", {})
    assert out["ok"] is False
    assert "error" in out


def test_dispatch_final_tools_echo():
    for name in ("submit_evidence", "emit_trading_signal"):
        out = registry.dispatch(name, {"foo": "bar"})
        assert out.get("ok") is True


def test_build_tool_list_filters_unknown():
    tools = registry.build_tool_list("search_news", "not_a_tool", "simulate_outcome")
    names = [t["name"] for t in tools]
    assert names == ["search_news", "simulate_outcome"]


def test_simulate_outcome_basic_long():
    out = sim_tools.simulate_outcome(
        side="YES", price=0.40, win_probability=0.60, capital=1000.0
    )
    assert out["ok"] is True
    assert out["ev_per_contract"] > 0  # 0.6*0.6 - 0.4*0.4 = 0.20
    assert out["kelly"]["recommended_size"] > 0


def test_simulate_outcome_no_edge_returns_zero_kelly():
    out = sim_tools.simulate_outcome(
        side="YES", price=0.50, win_probability=0.50, capital=1000.0
    )
    assert out["ok"] is True
    assert out["kelly"]["recommended_size"] == 0


def test_simulate_outcome_validates_inputs():
    bad = sim_tools.simulate_outcome(
        side="YES", price=1.5, win_probability=0.6, capital=100.0
    )
    assert bad["ok"] is False
    bad = sim_tools.simulate_outcome(
        side="MAYBE", price=0.5, win_probability=0.6, capital=100.0
    )
    assert bad["ok"] is False


def test_emit_trading_signal_schema_has_required_fields():
    schema = registry.EMIT_TRADING_SIGNAL_TOOL["input_schema"]
    required = set(schema["required"])
    for f in (
        "signal",
        "confidence",
        "calibrated_probability",
        "kelly_fraction",
        "reasoning",
        "key_factors",
        "risk_factors",
        "debate_winner",
    ):
        assert f in required, f"emit_trading_signal missing required field {f}"
    # Enum constraint on signal.
    assert schema["properties"]["signal"]["enum"] == ["LONG", "SHORT", "NO_TRADE"]
