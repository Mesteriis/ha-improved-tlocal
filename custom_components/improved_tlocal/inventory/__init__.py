"""Inventory helpers for ImprovedTLocal."""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from ..const import DATA_DEVICE_PROVIDERS, DOMAIN
from .cloud_file import CloudSnapshotInventoryProvider


async def async_setup_inventory_providers(hass: HomeAssistant) -> None:
    """Register the default inventory providers once."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    device_providers = domain_data.setdefault(DATA_DEVICE_PROVIDERS, [])
    if not any(isinstance(provider, CloudSnapshotInventoryProvider) for provider in device_providers):
        device_providers.append(CloudSnapshotInventoryProvider())
