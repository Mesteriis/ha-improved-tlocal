"""Tests for runtime plug entity plumbing."""

from __future__ import annotations

import asyncio

from custom_components.improved_tlocal.credentials import DeviceCredentials
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


class StaticCredentialsStore:
    """Return one static credentials object."""

    async def async_get_credentials(self, hass, device_id: str) -> DeviceCredentials | None:
        return DeviceCredentials(device_id=device_id, local_key="secret", protocol_version="3.4")


class FakePlugTransport:
    """In-memory fake plug transport."""

    def __init__(self) -> None:
        self.dps = {"1": False, "18": 2300, "19": 1234}

    async def async_status(self, binding, credentials):
        return {"dps": dict(self.dps)}

    async def async_set_switch(self, binding, credentials, *, on: bool, switch: int = 1):
        self.dps[str(switch)] = on
        return {"dps": dict(self.dps)}


def test_runtime_registry_creates_switch_and_sensor_entities_for_bound_plug(hass) -> None:
    """Binding a supported plug should create runtime entities for loaded platforms."""
    from custom_components.improved_tlocal.const import DATA_DEVICE_PROVIDERS, DATA_ENDPOINT_PROVIDERS, DOMAIN

    hass.data[DOMAIN] = {
        DATA_DEVICE_PROVIDERS: [
            StaticDeviceProvider(
                [
                    InventoryDevice(
                        device_id="plug-1",
                        name="Desk Plug",
                        template_candidates=["smart_plug.power_monitor.v1"],
                        dp_schema={
                            "1": {"code": "switch_1", "values": {"scale": 0}},
                            "18": {"code": "cur_current", "values": {"scale": 3}},
                            "19": {"code": "cur_power", "values": {"scale": 2}},
                        },
                    )
                ]
            )
        ],
        DATA_ENDPOINT_PROVIDERS: [
            StaticEndpointProvider([NetworkEndpoint(ip="192.168.1.70", port=6668, observed_device_id="plug-1")])
        ],
    }
    manager = ImprovedTLocalManager(hass)
    manager.runtime_registry.credentials_store = StaticCredentialsStore()
    manager.runtime_registry.transport = FakePlugTransport()

    switch_entities: list[object] = []
    sensor_entities: list[object] = []

    def add_switches(entities, update_before_add=False):
        switch_entities.extend(entities)

    def add_sensors(entities, update_before_add=False):
        sensor_entities.extend(entities)

    asyncio.run(manager.async_register_runtime_platform("switch", add_switches))
    asyncio.run(manager.async_register_runtime_platform("sensor", add_sensors))
    asyncio.run(manager.async_discover_dry_run())
    bind_result = asyncio.run(manager.async_bind_device({"device_id": "plug-1"}))

    assert bind_result["ok"] is True
    assert len(switch_entities) == 1
    assert len(sensor_entities) == 2

    switch = switch_entities[0]
    power_sensor = next(entity for entity in sensor_entities if entity.unique_id == "plug-1_power")
    current_sensor = next(entity for entity in sensor_entities if entity.unique_id == "plug-1_current")

    asyncio.run(switch.async_update())
    assert switch.is_on is False
    assert power_sensor.native_value == 12.34
    assert current_sensor.native_value == 2.3

    asyncio.run(switch.async_turn_on())
    assert switch.is_on is True
