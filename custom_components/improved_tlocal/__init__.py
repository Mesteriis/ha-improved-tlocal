"""ImprovedTLocal integration scaffold."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import DATA_MANAGER, DOMAIN
from .inventory import async_setup_inventory_providers
from .manager import ImprovedTLocalManager
from .runtime import async_setup_runtime_platforms
from .services import async_setup_services


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the ImprovedTLocal domain."""
    hass.data.setdefault(DOMAIN, {})
    if DATA_MANAGER not in hass.data[DOMAIN]:
        hass.data[DOMAIN][DATA_MANAGER] = ImprovedTLocalManager(hass)
    await async_setup_inventory_providers(hass)
    await async_setup_services(hass)
    await async_setup_runtime_platforms(hass)
    return True
