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

from .const import (
    DATA_MANAGER,
    DATA_SERVICES_REGISTERED,
    DOMAIN,
    SERVICE_BIND_DEVICE,
    SERVICE_DISCOVER_DRY_RUN,
    SERVICE_EXPORT_DIAGNOSTICS,
    SERVICE_SYNC_RUNTIME,
)
from .diagnostics import async_get_domain_diagnostics

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

BIND_DEVICE_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): cv.string,
        vol.Optional("ip"): cv.string,
        vol.Optional("port"): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
        vol.Optional("protocol_version"): cv.string,
        vol.Optional("template_id"): cv.string,
        vol.Optional("allow_tentative", default=False): cv.boolean,
    }
)

EXPORT_DIAGNOSTICS_SCHEMA = vol.Schema(
    {
        vol.Optional("device_id"): cv.string,
        vol.Optional("include_history", default=True): cv.boolean,
    }
)

SYNC_RUNTIME_SCHEMA = vol.Schema({})


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

    async def async_handle_bind_device(call: ServiceCall) -> dict[str, Any]:
        manager = hass.data[DOMAIN][DATA_MANAGER]
        return await manager.async_bind_device(dict(call.data))

    async def async_handle_export_diagnostics(call: ServiceCall) -> dict[str, Any]:
        return await async_get_domain_diagnostics(
            hass,
            device_id=call.data.get("device_id"),
            include_history=bool(call.data.get("include_history", True)),
        )

    async def async_handle_sync_runtime(call: ServiceCall) -> dict[str, Any]:
        manager = hass.data[DOMAIN][DATA_MANAGER]
        return await manager.async_sync_runtime_entities()

    supports_only = getattr(SupportsResponse, "ONLY", None)
    _async_register(
        SERVICE_DISCOVER_DRY_RUN,
        async_handle_discover_dry_run,
        schema=DISCOVER_DRY_RUN_SCHEMA,
        supports_response=supports_only,
    )
    _async_register(
        SERVICE_BIND_DEVICE,
        async_handle_bind_device,
        schema=BIND_DEVICE_SCHEMA,
        supports_response=supports_only,
    )
    _async_register(
        SERVICE_EXPORT_DIAGNOSTICS,
        async_handle_export_diagnostics,
        schema=EXPORT_DIAGNOSTICS_SCHEMA,
        supports_response=supports_only,
    )
    _async_register(
        SERVICE_SYNC_RUNTIME,
        async_handle_sync_runtime,
        schema=SYNC_RUNTIME_SCHEMA,
        supports_response=supports_only,
    )
    domain_data[DATA_SERVICES_REGISTERED] = True
