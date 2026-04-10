"""Switch platform for ImprovedTLocal runtime plugs."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity

from .const import DATA_MANAGER, DOMAIN


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None) -> None:
    """Set up runtime switch entities."""
    manager = hass.data.get(DOMAIN, {}).get(DATA_MANAGER)
    if manager is None:
        return
    await manager.async_register_runtime_platform("switch", async_add_entities)


def build_runtime_switch_entities(runtime) -> list["ImprovedTLocalPlugSwitchEntity"]:
    """Build switch entities for one runtime."""
    return [ImprovedTLocalPlugSwitchEntity(runtime)]


class ImprovedTLocalPlugSwitchEntity(SwitchEntity):
    """Main switch entity for a bound smart plug."""

    _attr_should_poll = True

    def __init__(self, runtime) -> None:
        """Initialize the switch entity."""
        self._runtime = runtime
        self._remove_listener = None
        self._attr_unique_id = f"{runtime.unique_id_prefix}_switch_1"
        self._attr_name = runtime.name

    @property
    def available(self) -> bool:
        """Return availability from the runtime."""
        return self._runtime.available

    @property
    def is_on(self) -> bool | None:
        """Return the switch state."""
        return self._runtime.is_on

    @property
    def device_info(self):
        """Return shared device-registry info."""
        return self._runtime.device_info

    async def async_added_to_hass(self) -> None:
        """Register runtime update listener."""
        if hasattr(super(), "async_added_to_hass"):
            await super().async_added_to_hass()
        self._remove_listener = self._runtime.register_listener(self._handle_runtime_update)

    async def async_will_remove_from_hass(self) -> None:
        """Unsubscribe runtime listener."""
        if self._remove_listener is not None:
            self._remove_listener()
            self._remove_listener = None
        if hasattr(super(), "async_will_remove_from_hass"):
            await super().async_will_remove_from_hass()

    async def async_update(self) -> None:
        """Refresh the shared runtime state."""
        await self._runtime.async_refresh()

    async def async_turn_on(self, **kwargs) -> None:
        """Turn the plug on."""
        await self._runtime.async_set_switch(True)

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the plug off."""
        await self._runtime.async_set_switch(False)

    def _handle_runtime_update(self) -> None:
        if hasattr(self, "async_write_ha_state"):
            self.async_write_ha_state()
