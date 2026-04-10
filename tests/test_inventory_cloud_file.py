"""Tests for the cloud snapshot inventory provider."""

from __future__ import annotations

import asyncio
import json

from custom_components.improved_tlocal.const import (
    TEMPLATE_SMART_LIGHT_RGBCW,
    TEMPLATE_SMART_PLUG_BASIC,
    TEMPLATE_SMART_PLUG_POWER,
)
from custom_components.improved_tlocal.inventory.cloud_file import (
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
    assert device.template_candidates == [TEMPLATE_SMART_PLUG_POWER, TEMPLATE_SMART_PLUG_BASIC]
    assert set(device.dp_schema) == {"1", "18", "19"}


def test_cloud_snapshot_provider_returns_empty_when_no_file_exists(hass) -> None:
    """Missing snapshot files should not crash discovery."""
    provider = CloudSnapshotInventoryProvider(paths=[hass.config.base_path / "missing.json"])

    devices = asyncio.run(provider.async_fetch_devices(hass))

    assert devices == []


def test_cloud_snapshot_provider_infers_rgbcw_light_template(tmp_path, hass) -> None:
    """RGB+CCT light snapshots should resolve to the light template candidate."""
    snapshot_path = tmp_path / "devices_cloud_live.json"
    snapshot_path.write_text(
        json.dumps(
            [
                {
                    "name": "HallLED1",
                    "id": "bf-light-1",
                    "key": "light-secret",
                    "mac": "E4AEE4539A0A",
                    "category": "dj",
                    "product_name": "Smart Light RGBCW",
                    "model": "Smart Light RGBCW",
                    "mapping": {
                        "20": {"code": "switch_led", "type": "Boolean", "values": {}},
                        "21": {"code": "work_mode", "type": "Enum", "values": {}},
                        "22": {"code": "bright_value_v2", "type": "Integer", "values": {"min": 10, "max": 1000}},
                        "23": {"code": "temp_value_v2", "type": "Integer", "values": {"min": 0, "max": 1000}},
                        "24": {"code": "colour_data_v2", "type": "Json", "values": {}},
                    },
                }
            ]
        ),
        encoding="utf-8",
    )
    provider = CloudSnapshotInventoryProvider(paths=[snapshot_path])

    devices = asyncio.run(provider.async_fetch_devices(hass))

    assert len(devices) == 1
    assert devices[0].template_candidates == [TEMPLATE_SMART_LIGHT_RGBCW]
