"""Tests for typed models."""

from __future__ import annotations

from custom_components.improved_tlocal.models import (
    BindingRecord,
    InventoryDevice,
    MatchReason,
    MatchResult,
    verification_from_score,
)


def test_model_serialization_normalizes_mac_and_compacts_none() -> None:
    """Serialized payloads should normalize MACs and drop null fields."""
    device = InventoryDevice(
        device_id="dev-1",
        name="Plug 1",
        mac="AABBCCDDEEFF",
        template_candidates=["plug.basic"],
    )
    binding = BindingRecord(
        device_id="dev-1",
        bound_ip="192.168.1.10",
        mac="AA-BB-CC-DD-EE-FF",
    )
    result = MatchResult(
        device_id="dev-1",
        candidate_ip="192.168.1.10",
        candidate_port=6668,
        reasons=[MatchReason(code="device_id_probe", summary="Exact device id")],
    )

    assert device.to_dict()["mac"] == "aa:bb:cc:dd:ee:ff"
    assert binding.to_dict()["mac"] == "aa:bb:cc:dd:ee:ff"
    assert "category" not in device.to_dict()
    assert result.to_dict()["reasons"][0]["code"] == "device_id_probe"


def test_verification_levels_follow_score_and_signal_strength() -> None:
    """Scores should map to stable verification levels."""
    assert verification_from_score(1.0, strong_signal=True) == "strongly_verified"
    assert verification_from_score(0.7) == "weakly_verified"
    assert verification_from_score(0.2) == "degraded"
    assert verification_from_score(0.0) == "unverified"
