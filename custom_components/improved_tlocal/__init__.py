"""ImprovedTLocal integration scaffold."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the ImprovedTLocal domain."""
    hass.data.setdefault(DOMAIN, {})
    return True
