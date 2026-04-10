"""Tests for dry-run discovery manager."""

from __future__ import annotations

import asyncio

from custom_components.improved_tlocal.const import DATA_DEVICE_PROVIDERS, DATA_ENDPOINT_PROVIDERS, DOMAIN
from custom_components.improved_tlocal.manager import ImprovedTLocalManager
from custom_components.improved_tlocal.models import BindingRecord, InventoryDevice, NetworkEndpoint


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


def test_discover_dry_run_builds_explainable_results(hass) -> None:
    """Dry-run discovery should classify strong, weak, conflicting, and missing matches."""
    devices = [
        InventoryDevice(device_id="dev-1", name="Plug 1", mac="aa:bb:cc:dd:ee:01"),
        InventoryDevice(device_id="dev-2", name="Plug 2", mac="aa:bb:cc:dd:ee:02"),
        InventoryDevice(device_id="dev-3", name="Plug 3"),
        InventoryDevice(device_id="dev-4", name="Plug 4"),
    ]
    endpoints = [
        NetworkEndpoint(ip="192.168.1.10", port=6668, observed_device_id="dev-1"),
        NetworkEndpoint(ip="192.168.1.11", port=6668, mac="aa:bb:cc:dd:ee:02"),
        NetworkEndpoint(ip="192.168.1.12", port=6668, observed_device_id="dev-3"),
        NetworkEndpoint(ip="192.168.1.13", port=6668, observed_device_id="dev-3"),
        NetworkEndpoint(ip="192.168.1.14", port=6668),
    ]
    hass.data[DOMAIN] = {
        DATA_DEVICE_PROVIDERS: [StaticDeviceProvider(devices)],
        DATA_ENDPOINT_PROVIDERS: [StaticEndpointProvider(endpoints)],
    }
    manager = ImprovedTLocalManager(hass)
    asyncio.run(
        manager.storage.async_save_bindings(
            {
                "dev-4": BindingRecord(
                    device_id="dev-4",
                    bound_ip="192.168.1.14",
                    bound_port=6668,
                )
            }
        )
    )

    report = asyncio.run(manager.async_discover_dry_run())
    results = {result["device_id"]: result for result in report["match_results"]}

    assert report["meta"]["device_provider_count"] == 1
    assert report["meta"]["endpoint_provider_count"] == 1
    assert results["dev-1"]["status"] == "matched"
    assert results["dev-1"]["verification_level"] == "strongly_verified"
    assert results["dev-2"]["status"] == "tentative"
    assert results["dev-2"]["recommended_action"] == "review"
    assert results["dev-3"]["status"] == "conflict"
    assert sorted(results["dev-3"]["conflicts"]) == ["192.168.1.12", "192.168.1.13"]
    assert results["dev-4"]["status"] == "tentative"
    assert results["dev-4"]["candidate_ip"] == "192.168.1.14"
    assert report["unmatched_device_ids"] == []


def test_discover_dry_run_scans_networks_when_requested(hass, monkeypatch) -> None:
    """LAN scan should run when networks are provided and no explicit override disables it."""
    hass.data[DOMAIN] = {
        DATA_DEVICE_PROVIDERS: [StaticDeviceProvider([InventoryDevice(device_id="dev-5", name="Plug 5")])],
        DATA_ENDPOINT_PROVIDERS: [],
    }
    manager = ImprovedTLocalManager(hass)
    calls: list[dict[str, object]] = []

    async def fake_scan(networks, ports, *, timeout):
        calls.append({"networks": list(networks), "ports": list(ports), "timeout": timeout})
        return [NetworkEndpoint(ip="192.168.50.10", port=6668)]

    monkeypatch.setattr("custom_components.improved_tlocal.manager.async_scan_open_ports", fake_scan)

    report = asyncio.run(
        manager.async_discover_dry_run(
            {
                "networks": ["192.168.50"],
                "ports": [6668],
            }
        )
    )

    assert calls == [{"networks": ["192.168.50"], "ports": [6668], "timeout": 0.35}]
    assert report["meta"]["lan_scan_enabled"] is True
    assert report["network_endpoints"][0]["ip"] == "192.168.50.10"
    assert report["unmatched_device_ids"] == ["dev-5"]
