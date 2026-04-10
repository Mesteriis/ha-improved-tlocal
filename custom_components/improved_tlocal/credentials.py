"""Credential resolution for ImprovedTLocal runtime."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from homeassistant.core import HomeAssistant

from .const import DEFAULT_CLOUD_SNAPSHOT_FILES


@dataclass(slots=True)
class DeviceCredentials:
    """Minimal runtime credentials for one Tuya device."""

    device_id: str
    local_key: str
    protocol_version: str | None = None


class FileSnapshotCredentialsStore:
    """Resolve local keys from Tuya snapshot files under `_tools`."""

    def __init__(self, paths: list[str | Path] | None = None) -> None:
        """Initialize the file-backed credentials store."""
        self._paths = [Path(path) for path in paths] if paths else None
        self._cache: dict[str, DeviceCredentials] | None = None

    async def async_get_credentials(self, hass: HomeAssistant, device_id: str) -> DeviceCredentials | None:
        """Return credentials for one device id."""
        cache = await self._async_load_cache(hass)
        return cache.get(device_id)

    async def _async_load_cache(self, hass: HomeAssistant) -> dict[str, DeviceCredentials]:
        """Load and cache all available credentials."""
        if self._cache is not None:
            return self._cache

        cache: dict[str, DeviceCredentials] = {}
        for path in self._resolve_paths(hass):
            if not path.is_file():
                continue
            raw_text = await asyncio.to_thread(path.read_text, encoding="utf-8")
            payload = json.loads(raw_text)
            if not isinstance(payload, list):
                continue
            for raw in payload:
                if not isinstance(raw, dict):
                    continue
                device_id = _clean_optional(raw.get("id"))
                local_key = _clean_optional(raw.get("key"))
                if not device_id or not local_key:
                    continue
                cache[device_id] = DeviceCredentials(
                    device_id=device_id,
                    local_key=local_key,
                    protocol_version=_clean_optional(raw.get("version")),
                )

        self._cache = cache
        return cache

    def _resolve_paths(self, hass: HomeAssistant) -> list[Path]:
        """Return candidate snapshot paths."""
        if self._paths is not None:
            return list(self._paths)

        config = getattr(hass, "config", None)
        config_path = getattr(config, "path", None)
        if callable(config_path):
            return [Path(config_path("_tools", filename)) for filename in DEFAULT_CLOUD_SNAPSHOT_FILES]
        return [Path.cwd() / "_tools" / filename for filename in DEFAULT_CLOUD_SNAPSHOT_FILES]


def _clean_optional(value: Any) -> str | None:
    """Normalize an optional string-ish value."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None
