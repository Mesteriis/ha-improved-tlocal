"""System health information for ImprovedTLocal."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant, callback

try:
    from homeassistant.components import system_health
except ImportError:  # pragma: no cover - compatibility fallback for tests
    system_health = None  # type: ignore[assignment]

from .const import DATA_DEVICE_PROVIDERS, DATA_ENDPOINT_PROVIDERS, DOMAIN
from .diagnostics import async_get_domain_diagnostics


@callback
def async_register(hass: HomeAssistant, register) -> None:
    """Register system health callbacks."""
    if hasattr(register, "domain"):
        register.domain = "ImprovedTLocal"
    register.async_register_info(system_health_info)


async def system_health_info(hass: HomeAssistant) -> dict[str, Any]:
    """Return operational system health info."""
    domain_data = hass.data.get(DOMAIN, {})
    diagnostics = await async_get_domain_diagnostics(hass, include_history=False)
    summary = diagnostics.get("summary", {})

    return {
        "Loaded": DOMAIN in hass.data,
        "Device Providers": len(domain_data.get(DATA_DEVICE_PROVIDERS, [])),
        "Endpoint Providers": len(domain_data.get(DATA_ENDPOINT_PROVIDERS, [])),
        "Bound Devices": summary.get("binding_count", 0),
        "Last Discovery": summary.get("last_discovery_generated_at") or "never",
        "Inventory Devices": summary.get("last_inventory_device_count", 0),
        "Matched Devices": summary.get("matched_device_count", 0),
        "Tentative Devices": summary.get("tentative_device_count", 0),
        "Conflicting Devices": summary.get("conflict_device_count", 0),
        "Unmatched Devices": summary.get("unmatched_device_count", 0),
        "Network Endpoints": summary.get("last_network_endpoint_count", 0),
        "Supported Templates": summary.get("supported_template_count", 0),
    }
