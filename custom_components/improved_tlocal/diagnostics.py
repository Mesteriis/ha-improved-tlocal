"""Diagnostics helpers for ImprovedTLocal."""

from __future__ import annotations

from typing import Any

try:
    from homeassistant.components.diagnostics import async_redact_data
except ImportError:  # pragma: no cover - compatibility fallback for tests
    def async_redact_data(data: Any, to_redact: set[str] | tuple[str, ...] | list[str]) -> Any:
        """Fallback redaction helper for non-HA test environments."""
        redact_keys = set(to_redact)

        def _redact(value: Any) -> Any:
            if isinstance(value, dict):
                return {
                    key: "**REDACTED**" if key in redact_keys else _redact(item)
                    for key, item in value.items()
                }
            if isinstance(value, list):
                return [_redact(item) for item in value]
            return value

        return _redact(data)

from homeassistant.core import HomeAssistant

from .const import DATA_DEVICE_PROVIDERS, DATA_ENDPOINT_PROVIDERS, DATA_MANAGER, DOMAIN
from .storage import ImprovedTLocalStore
from .templates import list_templates

REDACT_KEYS = {
    "mac",
    "uuid",
    "local_key",
    "local_key_ref",
}


async def async_get_domain_diagnostics(
    hass: HomeAssistant,
    *,
    device_id: str | None = None,
    include_history: bool = True,
) -> dict[str, Any]:
    """Return diagnostics for the whole domain or a single device."""
    domain_data = hass.data.get(DOMAIN, {})
    manager = domain_data.get(DATA_MANAGER)
    storage = manager.storage if manager is not None else ImprovedTLocalStore(hass)
    payload = await storage.async_load()

    bindings = payload.get("bindings", {})
    history = payload.get("binding_history", {})
    report = payload.get("last_discovery_report")

    if device_id:
        bindings = _filter_bindings(bindings, device_id)
        history = _filter_history(history, device_id) if include_history else {}
        report = _filter_report(report, device_id)
    elif not include_history:
        history = {}

    diagnostics = {
        "loaded": DOMAIN in hass.data,
        "summary": {
            "device_provider_count": len(domain_data.get(DATA_DEVICE_PROVIDERS, [])),
            "endpoint_provider_count": len(domain_data.get(DATA_ENDPOINT_PROVIDERS, [])),
            "binding_count": len(bindings) if isinstance(bindings, dict) else 0,
            "binding_history_device_count": len(history) if isinstance(history, dict) else 0,
            "last_discovery_generated_at": _report_meta(report, "generated_at"),
            "last_inventory_device_count": _report_meta(report, "inventory_devices", expect_len=True),
            "last_match_count": _report_meta(report, "match_results", expect_len=True),
            "matched_device_count": _count_report_status(report, "matched"),
            "tentative_device_count": _count_report_status(report, "tentative"),
            "conflict_device_count": _count_report_status(report, "conflict"),
            "unmatched_device_count": _count_report_status(report, "unmatched"),
            "last_network_endpoint_count": _report_meta(report, "network_endpoints", expect_len=True),
            "supported_template_count": len(list_templates()),
            "runtime_device_count": manager.runtime_registry.summary().get("runtime_device_count", 0)
            if manager is not None
            else 0,
            "runtime_entity_count": manager.runtime_registry.summary().get("registered_entity_count", 0)
            if manager is not None
            else 0,
        },
        "bindings": bindings if isinstance(bindings, dict) else {},
        "binding_history": history if isinstance(history, dict) else {},
        "last_discovery_report": report if isinstance(report, dict) else None,
        "templates": [template.to_dict() for template in list_templates()],
        "runtime": manager.runtime_registry.summary() if manager is not None else {},
    }
    return async_redact_data(diagnostics, REDACT_KEYS)


def _report_meta(report: dict[str, Any] | None, key: str, *, expect_len: bool = False) -> Any:
    """Return one report metadata field or derived list length."""
    if not isinstance(report, dict):
        return None
    value = report.get(key)
    if expect_len:
        return len(value) if isinstance(value, list) else 0
    return value


def _count_report_status(report: dict[str, Any] | None, status: str) -> int:
    """Count match results with one specific status."""
    if not isinstance(report, dict):
        return 0
    matches = report.get("match_results", [])
    if not isinstance(matches, list):
        return 0
    return sum(1 for item in matches if isinstance(item, dict) and item.get("status") == status)


def _filter_bindings(bindings: Any, device_id: str) -> dict[str, Any]:
    """Filter bindings to one device."""
    if not isinstance(bindings, dict):
        return {}
    binding = bindings.get(device_id)
    return {device_id: binding} if binding is not None else {}


def _filter_history(history: Any, device_id: str) -> dict[str, Any]:
    """Filter binding history to one device."""
    if not isinstance(history, dict):
        return {}
    events = history.get(device_id)
    return {device_id: events} if events is not None else {}


def _filter_report(report: Any, device_id: str) -> dict[str, Any] | None:
    """Filter one serialized discovery report down to a single device."""
    if not isinstance(report, dict):
        return None

    filtered_inventory = [
        item for item in report.get("inventory_devices", []) if isinstance(item, dict) and item.get("device_id") == device_id
    ]
    filtered_matches = [
        item for item in report.get("match_results", []) if isinstance(item, dict) and item.get("device_id") == device_id
    ]

    candidate_targets = {
        (item.get("candidate_ip"), int(item.get("candidate_port") or 0))
        for item in filtered_matches
        if isinstance(item, dict) and item.get("candidate_ip")
    }
    filtered_endpoints = [
        item
        for item in report.get("network_endpoints", [])
        if isinstance(item, dict) and (item.get("ip"), int(item.get("port") or 0)) in candidate_targets
    ]

    return {
        **report,
        "inventory_devices": filtered_inventory,
        "match_results": filtered_matches,
        "network_endpoints": filtered_endpoints,
        "unmatched_device_ids": [item for item in report.get("unmatched_device_ids", []) if item == device_id],
    }
