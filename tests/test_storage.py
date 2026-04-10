"""Tests for persistent storage helpers."""

from __future__ import annotations

import asyncio

from custom_components.improved_tlocal.models import BindingRecord, DiscoveryReport
from custom_components.improved_tlocal.storage import ImprovedTLocalStore


def test_store_round_trip_bindings_and_report(hass) -> None:
    """Bindings and discovery reports should persist through the store wrapper."""
    store = ImprovedTLocalStore(hass)
    bindings = {
        "dev-1": BindingRecord(
            device_id="dev-1",
            bound_ip="192.168.1.20",
            bound_port=6668,
            confidence=1.0,
            verification_level="strongly_verified",
        )
    }
    report = DiscoveryReport(
        generated_at="2026-04-10T12:00:00+00:00",
        inventory_devices=[],
        network_endpoints=[],
        match_results=[],
        unmatched_device_ids=[],
        meta={"source": "test"},
    )

    asyncio.run(store.async_save_bindings(bindings))
    loaded_bindings = asyncio.run(store.async_load_bindings())
    asyncio.run(store.async_save_discovery_report(report))
    loaded_report = asyncio.run(store.async_load_discovery_report())

    assert set(loaded_bindings) == {"dev-1"}
    assert loaded_bindings["dev-1"].bound_ip == "192.168.1.20"
    assert loaded_bindings["dev-1"].verification_level == "strongly_verified"
    assert loaded_report is not None
    assert loaded_report["meta"]["source"] == "test"
