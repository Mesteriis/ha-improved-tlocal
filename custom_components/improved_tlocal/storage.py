"""Persistent storage helpers for ImprovedTLocal."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .const import STORE_KEY, STORE_VERSION
from .models import BindingRecord, DiscoveryReport


def _default_payload() -> dict[str, Any]:
    """Return the canonical store payload."""
    return {
        "bindings": {},
        "binding_history": {},
        "ignored_devices": [],
        "template_overrides": {},
        "last_discovery_report": None,
    }


class ImprovedTLocalStore:
    """Typed Store wrapper for ImprovedTLocal state."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the store wrapper."""
        self._store: Store[dict[str, Any]] = Store(hass, STORE_VERSION, STORE_KEY)

    async def async_load(self) -> dict[str, Any]:
        """Load the full state payload."""
        payload = await self._store.async_load()
        if not isinstance(payload, dict):
            return _default_payload()
        return {**_default_payload(), **payload}

    async def async_save(self, payload: dict[str, Any]) -> None:
        """Persist the full state payload."""
        canonical = {**_default_payload(), **payload}
        await self._store.async_save(canonical)

    async def async_load_bindings(self) -> dict[str, BindingRecord]:
        """Load persisted bindings."""
        payload = await self.async_load()
        raw_bindings = payload.get("bindings", {})
        if not isinstance(raw_bindings, dict):
            return {}
        bindings: dict[str, BindingRecord] = {}
        for device_id, raw in raw_bindings.items():
            if not isinstance(raw, dict):
                continue
            bindings[str(device_id)] = BindingRecord(
                device_id=str(raw.get("device_id") or device_id),
                bound_ip=str(raw.get("bound_ip") or ""),
                bound_port=int(raw.get("bound_port") or 6668),
                bound_protocol_version=raw.get("bound_protocol_version"),
                verification_level=str(raw.get("verification_level") or "unverified"),
                template_id=raw.get("template_id"),
                confidence=float(raw.get("confidence") or 0.0),
                verified_at=raw.get("verified_at"),
                verification_method=raw.get("verification_method"),
                failure_streak=int(raw.get("failure_streak") or 0),
                mac=raw.get("mac"),
            )
        return bindings

    async def async_save_bindings(self, bindings: dict[str, BindingRecord]) -> None:
        """Persist bindings into the store payload."""
        payload = await self.async_load()
        payload["bindings"] = {device_id: binding.to_dict() for device_id, binding in bindings.items()}
        await self.async_save(payload)

    async def async_append_binding_history(self, device_id: str, event: dict[str, Any]) -> None:
        """Append one binding mutation event to per-device history."""
        payload = await self.async_load()
        history = payload.get("binding_history")
        if not isinstance(history, dict):
            history = {}
        events = history.get(device_id)
        if not isinstance(events, list):
            events = []
        events.append(event)
        history[device_id] = events
        payload["binding_history"] = history
        await self.async_save(payload)

    async def async_load_binding_history(self, device_id: str) -> list[dict[str, Any]]:
        """Load per-device binding history events."""
        payload = await self.async_load()
        history = payload.get("binding_history", {})
        if not isinstance(history, dict):
            return []
        events = history.get(device_id, [])
        return events if isinstance(events, list) else []

    async def async_save_discovery_report(self, report: DiscoveryReport) -> None:
        """Persist the latest dry-run discovery report."""
        payload = await self.async_load()
        payload["last_discovery_report"] = report.to_dict()
        await self.async_save(payload)

    async def async_load_discovery_report(self) -> dict[str, Any] | None:
        """Return the last persisted dry-run report."""
        payload = await self.async_load()
        report = payload.get("last_discovery_report")
        return report if isinstance(report, dict) else None
