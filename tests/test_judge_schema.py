"""Smoke tests for JudgeAgent's structured-output contract and JudgeDecision model."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.orchestrator.state_models import (
    DebateTranscript,
    DebateTurn,
    EvidencePack,
    JudgeDecision,
    LessonRef,
)
from src.agents.agentic.tools.registry import EMIT_TRADING_SIGNAL_TOOL


def _valid_judge_payload(**overrides):
    payload = {
        "ticker": "DEMO-1",
        "signal": "LONG",
        "confidence": 72.0,
        "calibrated_probability": 0.65,
        "expected_return_pct": 18.0,
        "kelly_fraction": 0.10,
        "reasoning": (
            "Calibrated probability materially exceeds the market-implied probability. "
            "Bull case is well supported by multiple independent sources and a base-rate edge. "
            "Red-team raised no critical concerns."
        ),
        "key_factors": ["base_rate_gap", "supportive_news"],
        "risk_factors": ["binary event risk", "news reversal possible"],
        "market_edge": "5% gap between calibrated p and market-implied p.",
        "invalidation_conditions": ["headline reversal", "OI drying up"],
        "lessons_applied": [1, 2],
        "debate_winner": "bull",
    }
    payload.update(overrides)
    return payload


def test_judge_decision_constructs_from_valid_payload():
    payload = _valid_judge_payload()
    dec = JudgeDecision(**payload)
    assert dec.signal == "LONG"
    assert 0 <= dec.calibrated_probability <= 1
    assert dec.kelly_fraction <= 0.25


def test_judge_decision_rejects_invalid_signal():
    with pytest.raises(ValidationError):
        JudgeDecision(**_valid_judge_payload(signal="MAYBE"))


def test_judge_decision_rejects_kelly_above_quarter():
    with pytest.raises(ValidationError):
        JudgeDecision(**_valid_judge_payload(kelly_fraction=0.40))


def test_emit_trading_signal_required_matches_judge_decision_fields():
    """The tool schema's `required` fields should be a subset of JudgeDecision fields."""
    schema_required = set(EMIT_TRADING_SIGNAL_TOOL["input_schema"]["required"])
    decision_fields = set(JudgeDecision.model_fields.keys())
    # ticker isn't in the tool schema (added by orchestrator), so allow that gap.
    missing = schema_required - decision_fields
    assert not missing, f"tool requires fields missing on JudgeDecision: {missing}"


def test_evidence_pack_minimal():
    pack = EvidencePack(
        ticker="DEMO-1",
        summary="x" * 60,
        bull_case_points=["a", "b"],
        bear_case_points=["c", "d"],
        market_implied_pct=55.0,
        confidence_in_evidence=0.6,
    )
    assert pack.confidence_in_evidence == 0.6


def test_debate_transcript_with_turns():
    bull = DebateTurn(
        role="bull",
        stance="LONG",
        probability_estimate=0.65,
        argument="...",
    )
    transcript = DebateTranscript(ticker="DEMO-1", bull=bull)
    assert transcript.bull.stance == "LONG"


def test_lesson_ref_clamps_similarity():
    # Similarity field has constraint [0,1]; out-of-range should error.
    with pytest.raises(ValidationError):
        LessonRef(id=1, similarity=1.5, lesson_type="x", snippet="y")
