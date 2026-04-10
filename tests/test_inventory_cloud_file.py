"""Tests for the cloud snapshot inventory provider."""

from __future__ import annotations

import asyncio
import json

from custom_components.improved_tlocal.inventory.cloud_file import (
    SMART_PLUG_BASIC_TEMPLATE,
    SMART_PLUG_POWER_TEMPLATE,
    CloudSnapshotInventoryProvider,
)


def test_cloud_snapshot_provider_normalizes_power_plug(tmp_path, hass) -> None:
    """Snapshot provider should infer plug templates and normalize canonical fields."""
    snapshot_path = tmp_path / "devices_cloud_live.json"
    snapshot_path.write_text(
        json.dumps(
            [
                {
                    "name": "Desk Plug",
                    "id": "bf-device-1",
                    "key": "secret-key",
                    "mac": "FC3CD74232F0",
                    "uuid": "uuid-1",
                    "category": "cz",
                    "product_id": "prod-1",
                    "product_name": "Smart Energy Meter",
                    "model": "AT2PL",
                    "mapping": {
                        "1": {"code": "switch_1", "type": "Boolean", "values": {}},
                        "18": {"code": "cur_current", "type": "Integer", "values": {}},
                        "19": {"code": "cur_power", "type": "Integer", "values": {}},
                    },
                },
                {
                    "name": "Ignored Broken Device",
                    "mapping": {},
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    provider = CloudSnapshotInventoryProvider(paths=[snapshot_path])

    devices = asyncio.run(provider.async_fetch_devices(hass))

    assert len(devices) == 1
    device = devices[0]
    assert device.device_id == "bf-device-1"
    assert device.name == "Desk Plug"
    assert device.model == "Smart Energy Meter"
    assert device.model_id == "AT2PL"
    assert device.mac == "FC3CD74232F0"
    assert device.cloud_online is True
    assert device.template_candidates == [SMART_PLUG_POWER_TEMPLATE, SMART_PLUG_BASIC_TEMPLATE]
    assert set(device.dp_schema) == {"1", "18", "19"}


def test_cloud_snapshot_provider_returns_empty_when_no_file_exists(hass) -> None:
    """Missing snapshot files should not crash discovery."""
    provider = CloudSnapshotInventoryProvider(paths=[hass.config.base_path / "missing.json"])

    devices = asyncio.run(provider.async_fetch_devices(hass))

    assert devices == []
