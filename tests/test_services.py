"""Tests for service registration."""

from __future__ import annotations

import asyncio

from custom_components.improved_tlocal import async_setup
from custom_components.improved_tlocal.const import DATA_MANAGER, DOMAIN, SERVICE_DISCOVER_DRY_RUN
from custom_components.improved_tlocal.manager import ImprovedTLocalManager


def test_async_setup_registers_manager_and_service_once(hass) -> None:
    """Domain setup should create one manager and register one callable service."""
    assert asyncio.run(async_setup(hass, {})) is True
    assert DOMAIN in hass.data
    assert isinstance(hass.data[DOMAIN][DATA_MANAGER], ImprovedTLocalManager)

    service_entry = hass.services.registered[(DOMAIN, SERVICE_DISCOVER_DRY_RUN)]
    assert service_entry["supports_response"] == "only"

    asyncio.run(async_setup(hass, {}))
    assert len(hass.services.registered) == 1


def test_service_handler_returns_manager_report(hass) -> None:
    """Registered service should proxy to the manager and return its report."""
    asyncio.run(async_setup(hass, {}))
    manager = hass.data[DOMAIN][DATA_MANAGER]
    expected = {"ok": True, "generated_at": "2026-04-10T12:00:00+00:00"}

    async def fake_discover(options):
        return {**expected, "options": options}

    manager.async_discover_dry_run = fake_discover
    service_entry = hass.services.registered[(DOMAIN, SERVICE_DISCOVER_DRY_RUN)]
    result = asyncio.run(service_entry["handler"](type("Call", (), {"data": {"networks": ["192.168.1"]}})()))

    assert result == {"ok": True, "generated_at": "2026-04-10T12:00:00+00:00", "options": {"networks": ["192.168.1"]}}
