"""Tests for binding apply and rebind flows."""

from __future__ import annotations

import asyncio

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


def test_bind_device_applies_strong_match_and_persists_history(hass) -> None:
    """Strong report matches should bind immediately and keep mutation history."""
    from custom_components.improved_tlocal.const import DATA_DEVICE_PROVIDERS, DATA_ENDPOINT_PROVIDERS, DOMAIN

    hass.data[DOMAIN] = {
        DATA_DEVICE_PROVIDERS: [
            StaticDeviceProvider(
                [
                    InventoryDevice(
                        device_id="plug-1",
                        name="Desk Plug",
                        mac="aa:bb:cc:dd:ee:01",
                        template_candidates=["smart_plug.power_monitor.v1"],
                        dp_schema={
                            "1": {"code": "switch_1"},
                            "19": {"code": "cur_power"},
                        },
                    )
                ]
            )
        ],
        DATA_ENDPOINT_PROVIDERS: [
            StaticEndpointProvider(
                [NetworkEndpoint(ip="192.168.1.30", port=6668, observed_device_id="plug-1", protocol_version="3.4")]
            )
        ],
    }
    manager = ImprovedTLocalManager(hass)

    asyncio.run(manager.async_discover_dry_run())
    result = asyncio.run(manager.async_bind_device({"device_id": "plug-1"}))
    bindings = asyncio.run(manager.storage.async_load_bindings())
    history = asyncio.run(manager.storage.async_load_binding_history("plug-1"))

    assert result["ok"] is True
    assert result["action"] == "created"
    assert result["binding"]["bound_ip"] == "192.168.1.30"
    assert result["binding"]["bound_protocol_version"] == "3.4"
    assert result["binding"]["template_id"] == "smart_plug.power_monitor.v1"
    assert result["template"]["family"] == "smart_plug"
    assert bindings["plug-1"].bound_ip == "192.168.1.30"
    assert len(history) == 1
    assert history[0]["action"] == "created"


def test_bind_device_rejects_tentative_without_explicit_confirmation(hass) -> None:
    """Tentative matches should require allow_tentative before binding."""
    from custom_components.improved_tlocal.const import DATA_DEVICE_PROVIDERS, DATA_ENDPOINT_PROVIDERS, DOMAIN

    hass.data[DOMAIN] = {
        DATA_DEVICE_PROVIDERS: [
            StaticDeviceProvider(
                [
                    InventoryDevice(
                        device_id="plug-2",
                        name="Weak Plug",
                        mac="aa:bb:cc:dd:ee:02",
                        template_candidates=["smart_plug.power_monitor.v1"],
                        dp_schema={
                            "1": {"code": "switch_1"},
                            "19": {"code": "cur_power"},
                        },
                    )
                ]
            )
        ],
        DATA_ENDPOINT_PROVIDERS: [
            StaticEndpointProvider([NetworkEndpoint(ip="192.168.1.31", port=6668, mac="aa:bb:cc:dd:ee:02")])
        ],
    }
    manager = ImprovedTLocalManager(hass)

    asyncio.run(manager.async_discover_dry_run())
    rejected = asyncio.run(manager.async_bind_device({"device_id": "plug-2"}))
    accepted = asyncio.run(manager.async_bind_device({"device_id": "plug-2", "allow_tentative": True}))

    assert rejected["ok"] is False
    assert rejected["error_code"] == "tentative_requires_confirmation"
    assert accepted["ok"] is True
    assert accepted["action"] == "created"


def test_bind_device_rebinds_existing_binding_without_losing_template(hass) -> None:
    """A new strong match should rebind an existing device and preserve identity."""
    from custom_components.improved_tlocal.const import DATA_DEVICE_PROVIDERS, DATA_ENDPOINT_PROVIDERS, DOMAIN

    provider = StaticEndpointProvider([NetworkEndpoint(ip="192.168.1.40", port=6668, observed_device_id="plug-3")])
    hass.data[DOMAIN] = {
        DATA_DEVICE_PROVIDERS: [
            StaticDeviceProvider(
                [
                    InventoryDevice(
                        device_id="plug-3",
                        name="Rebind Plug",
                        template_candidates=["smart_plug.power_monitor.v1"],
                        dp_schema={
                            "1": {"code": "switch_1"},
                            "19": {"code": "cur_power"},
                        },
                    )
                ]
            )
        ],
        DATA_ENDPOINT_PROVIDERS: [provider],
    }
    manager = ImprovedTLocalManager(hass)

    asyncio.run(manager.async_discover_dry_run())
    first = asyncio.run(manager.async_bind_device({"device_id": "plug-3"}))
    provider.endpoints = [NetworkEndpoint(ip="192.168.1.41", port=6668, observed_device_id="plug-3")]
    asyncio.run(manager.async_discover_dry_run())
    second = asyncio.run(manager.async_bind_device({"device_id": "plug-3"}))
    bindings = asyncio.run(manager.storage.async_load_bindings())
    history = asyncio.run(manager.storage.async_load_binding_history("plug-3"))

    assert first["action"] == "created"
    assert second["ok"] is True
    assert second["action"] == "rebound"
    assert second["previous_binding"]["bound_ip"] == "192.168.1.40"
    assert second["binding"]["bound_ip"] == "192.168.1.41"
    assert bindings["plug-3"].template_id == "smart_plug.power_monitor.v1"
    assert len(history) == 2
    assert history[1]["action"] == "rebound"
