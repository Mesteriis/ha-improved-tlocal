"""Service registration for ImprovedTLocal."""

from __future__ import annotations

import inspect
from typing import Any

import voluptuous as vol
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

try:
    from homeassistant.core import ServiceCall, SupportsResponse
except ImportError:  # pragma: no cover - compatibility fallback for tests
    ServiceCall = Any  # type: ignore[assignment]
    SupportsResponse = None  # type: ignore[assignment]

from .const import DATA_MANAGER, DATA_SERVICES_REGISTERED, DOMAIN, SERVICE_DISCOVER_DRY_RUN

DISCOVER_DRY_RUN_SCHEMA = vol.Schema(
    {
        vol.Optional("networks"): vol.Any([cv.string], cv.string),
        vol.Optional("ports"): vol.Any(
            [vol.All(vol.Coerce(int), vol.Range(min=1, max=65535))],
            vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
        ),
        vol.Optional("timeout"): vol.Coerce(float),
        vol.Optional("include_lan_scan"): cv.boolean,
    }
)


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register ImprovedTLocal services once."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get(DATA_SERVICES_REGISTERED):
        return

    def _async_register(service: str, handler, *, schema=None, supports_response=None) -> None:
        kwargs: dict[str, Any] = {}
        if schema is not None:
            kwargs["schema"] = schema
        if supports_response is not None:
            if "supports_response" in inspect.signature(hass.services.async_register).parameters:
                kwargs["supports_response"] = supports_response
        hass.services.async_register(DOMAIN, service, handler, **kwargs)

    async def async_handle_discover_dry_run(call: ServiceCall) -> dict[str, Any]:
        manager = hass.data[DOMAIN][DATA_MANAGER]
        return await manager.async_discover_dry_run(dict(call.data))

    supports_only = getattr(SupportsResponse, "ONLY", None)
    _async_register(
        SERVICE_DISCOVER_DRY_RUN,
        async_handle_discover_dry_run,
        schema=DISCOVER_DRY_RUN_SCHEMA,
        supports_response=supports_only,
    )
    domain_data[DATA_SERVICES_REGISTERED] = True
