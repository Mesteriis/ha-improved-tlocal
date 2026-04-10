"""Tests for system health reporting."""

from __future__ import annotations

import asyncio

from custom_components.improved_tlocal.manager import ImprovedTLocalManager
from custom_components.improved_tlocal.models import InventoryDevice, NetworkEndpoint
from custom_components.improved_tlocal.system_health import async_register, system_health_info


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


def test_system_health_info_summarizes_domain_state(hass) -> None:
    """System health should report useful current counts."""
    from custom_components.improved_tlocal.const import DATA_DEVICE_PROVIDERS, DATA_ENDPOINT_PROVIDERS, DOMAIN

    hass.data[DOMAIN] = {
        DATA_DEVICE_PROVIDERS: [
            StaticDeviceProvider(
                [
                    InventoryDevice(
                        device_id="plug-1",
                        name="Desk Plug",
                        template_candidates=["smart_plug.power_monitor.v1"],
                        dp_schema={"1": {"code": "switch_1"}, "19": {"code": "cur_power"}},
                    )
                ]
            )
        ],
        DATA_ENDPOINT_PROVIDERS: [
            StaticEndpointProvider([NetworkEndpoint(ip="192.168.1.60", port=6668, observed_device_id="plug-1")])
        ],
    }
    manager = ImprovedTLocalManager(hass)

    asyncio.run(manager.async_discover_dry_run())
    asyncio.run(manager.async_bind_device({"device_id": "plug-1"}))
    info = asyncio.run(system_health_info(hass))

    assert info["Loaded"] is True
    assert info["Device Providers"] == 1
    assert info["Endpoint Providers"] == 1
    assert info["Bound Devices"] == 1
    assert info["Inventory Devices"] == 1
    assert info["Matched Devices"] == 1
    assert info["Network Endpoints"] == 1
    assert info["Supported Templates"] == 3


def test_system_health_registers_callback() -> None:
    """System health registration should expose one info callback."""
    from tests.conftest import FakeHass, FakeSystemHealthRegistration

    register = FakeSystemHealthRegistration()
    async_register(FakeHass(), register)

    assert register.domain == "ImprovedTLocal"
    assert register.callback is system_health_info
