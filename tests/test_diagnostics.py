"""Tests for diagnostics export."""

from __future__ import annotations

import asyncio

from custom_components.improved_tlocal.diagnostics import async_get_domain_diagnostics
from custom_components.improved_tlocal.manager import ImprovedTLocalManager
from custom_components.improved_tlocal.models import InventoryDevice, NetworkEndpoint


class StaticDeviceProvider:
    """Return a fixed device list."""

    def __init__(self, devices: list[InventoryDevice]) -> None:
        self.devices = devices

    async def async_fetch_devices(self, hass) -> list[InventoryDevice]:
        """Return the configured devices."""
        return list(self.devices)


class StaticEndpointProvider:
    """Return a fixed endpoint list."""

    def __init__(self, endpoints: list[NetworkEndpoint]) -> None:
        self.endpoints = endpoints

    async def async_fetch_endpoints(self, hass) -> list[NetworkEndpoint]:
        """Return the configured endpoints."""
        return list(self.endpoints)


def test_domain_diagnostics_redacts_sensitive_fields_and_filters_by_device(hass) -> None:
    """Diagnostics export should be redacted and filterable to one device."""
    from custom_components.improved_tlocal.const import DATA_DEVICE_PROVIDERS, DATA_ENDPOINT_PROVIDERS, DOMAIN

    hass.data[DOMAIN] = {
        DATA_DEVICE_PROVIDERS: [
            StaticDeviceProvider(
                [
                    InventoryDevice(
                        device_id="plug-1",
                        name="Desk Plug",
                        mac="aa:bb:cc:dd:ee:01",
                        uuid="uuid-1",
                        template_candidates=["smart_plug.power_monitor.v1"],
                        dp_schema={"1": {"code": "switch_1"}, "19": {"code": "cur_power"}},
                    )
                ]
            )
        ],
        DATA_ENDPOINT_PROVIDERS: [
            StaticEndpointProvider([NetworkEndpoint(ip="192.168.1.50", port=6668, observed_device_id="plug-1", mac="aa")])
        ],
    }
    manager = ImprovedTLocalManager(hass)

    asyncio.run(manager.async_discover_dry_run())
    asyncio.run(manager.async_bind_device({"device_id": "plug-1"}))
    diagnostics = asyncio.run(async_get_domain_diagnostics(hass, device_id="plug-1"))

    assert diagnostics["summary"]["binding_count"] == 1
    assert list(diagnostics["bindings"]) == ["plug-1"]
    assert diagnostics["bindings"]["plug-1"]["mac"] == "**REDACTED**"
    assert diagnostics["last_discovery_report"]["inventory_devices"][0]["mac"] == "**REDACTED**"
    assert diagnostics["last_discovery_report"]["inventory_devices"][0]["uuid"] == "**REDACTED**"
    assert diagnostics["binding_history"]["plug-1"][0]["next_binding"]["mac"] == "**REDACTED**"


def test_domain_diagnostics_can_skip_history(hass) -> None:
    """Diagnostics export should allow omitting mutation history."""
    diagnostics = asyncio.run(async_get_domain_diagnostics(hass, include_history=False))

    assert diagnostics["binding_history"] == {}
