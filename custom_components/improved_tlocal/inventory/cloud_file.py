"""Cloud snapshot inventory provider for ImprovedTLocal."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant

from ..const import DEFAULT_CLOUD_SNAPSHOT_FILES, TEMPLATE_SMART_PLUG_BASIC, TEMPLATE_SMART_PLUG_POWER
from ..models import InventoryDevice


class CloudSnapshotInventoryProvider:
    """Load normalized device inventory from Tuya cloud snapshot files."""

    def __init__(self, paths: Sequence[str | Path] | None = None) -> None:
        """Initialize the snapshot provider."""
        self._paths = [Path(path) for path in paths] if paths else None

    async def async_fetch_devices(self, hass: HomeAssistant) -> list[InventoryDevice]:
        """Return normalized devices from the first available snapshot file."""
        snapshot_path = self._resolve_snapshot_path(hass)
        if snapshot_path is None:
            return []

        raw_text = await asyncio.to_thread(snapshot_path.read_text, encoding="utf-8")
        payload = json.loads(raw_text)
        if not isinstance(payload, list):
            return []

        devices: list[InventoryDevice] = []
        for raw_device in payload:
            if not isinstance(raw_device, dict):
                continue
            device = _normalize_inventory_device(raw_device, source_name=snapshot_path.name)
            if device is not None:
                devices.append(device)
        return devices

    def _resolve_snapshot_path(self, hass: HomeAssistant) -> Path | None:
        """Return the first configured snapshot path that exists."""
        candidate_paths = self._paths or _default_snapshot_paths(hass)
        for path in candidate_paths:
            if path.is_file():
                return path
        return None


def _default_snapshot_paths(hass: HomeAssistant) -> list[Path]:
    """Build default snapshot paths inside the Home Assistant config directory."""
    config = getattr(hass, "config", None)
    config_path = getattr(config, "path", None)
    if callable(config_path):
        return [Path(config_path("_tools", filename)) for filename in DEFAULT_CLOUD_SNAPSHOT_FILES]
    return [Path.cwd() / "_tools" / filename for filename in DEFAULT_CLOUD_SNAPSHOT_FILES]


def _normalize_inventory_device(raw: dict[str, Any], *, source_name: str) -> InventoryDevice | None:
    """Translate one raw snapshot device into the canonical inventory model."""
    device_id = str(raw.get("id") or "").strip()
    name = str(raw.get("name") or "").strip()
    if not device_id or not name:
        return None

    mapping = raw.get("mapping")
    dp_schema = mapping if isinstance(mapping, dict) else None
    is_subdevice = bool(raw.get("sub"))

    return InventoryDevice(
        device_id=device_id,
        name=name,
        category=_clean_optional(raw.get("category")),
        product_id=_clean_optional(raw.get("product_id")),
        model=_clean_optional(raw.get("product_name")) or _clean_optional(raw.get("model")),
        model_id=_clean_optional(raw.get("model")),
        uuid=_clean_optional(raw.get("uuid")),
        mac=_clean_optional(raw.get("mac")),
        parent_device_id=_clean_optional(raw.get("gateway_id")) if is_subdevice else None,
        node_id=_clean_optional(raw.get("node_id")) or _clean_optional(raw.get("cid")),
        is_subdevice=is_subdevice,
        transport_scope="hub" if is_subdevice else "direct",
        cloud_online=True if source_name == "devices_cloud_live.json" else None,
        dp_schema=dp_schema,
        template_candidates=_infer_template_candidates(raw),
    )


def _infer_template_candidates(raw: dict[str, Any]) -> list[str]:
    """Infer the first supported template candidates from Tuya metadata."""
    mapping = raw.get("mapping")
    if not isinstance(mapping, dict):
        return []

    codes = {
        str(item.get("code")).strip()
        for item in mapping.values()
        if isinstance(item, dict) and item.get("code")
    }
    if "switch_1" not in codes:
        return []

    templates: list[str] = []
    if codes.intersection({"cur_power", "cur_current", "cur_voltage", "add_ele"}):
        templates.append(TEMPLATE_SMART_PLUG_POWER)
    templates.append(TEMPLATE_SMART_PLUG_BASIC)
    return templates


def _clean_optional(value: Any) -> str | None:
    """Convert optional string-ish values into stripped strings."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None
