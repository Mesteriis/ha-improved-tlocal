"""Light platform for ImprovedTLocal runtime lamps."""

from __future__ import annotations

from homeassistant.components.light import ColorMode, LightEntity

from .const import DATA_MANAGER, DOMAIN, TEMPLATE_SMART_LIGHT_RGBCW


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None) -> None:
    """Set up runtime light entities."""
    manager = hass.data.get(DOMAIN, {}).get(DATA_MANAGER)
    if manager is None:
        return
    await manager.async_register_runtime_platform("light", async_add_entities)


def build_runtime_light_entities(runtime) -> list["ImprovedTLocalBulbEntity"]:
    """Build light entities for one runtime."""
    template = getattr(runtime, "template", None)
    if template is None or template.template_id != TEMPLATE_SMART_LIGHT_RGBCW:
        return []
    return [ImprovedTLocalBulbEntity(runtime)]


class ImprovedTLocalBulbEntity(LightEntity):
    """Single light entity for a bound Tuya bulb."""

    _attr_should_poll = True

    def __init__(self, runtime) -> None:
        """Initialize the bulb entity."""
        self._runtime = runtime
        self._remove_listener = None
        self._attr_unique_id = f"{runtime.unique_id_prefix}_light"
        self._attr_name = runtime.name
        self._attr_supported_color_modes = {ColorMode.COLOR_TEMP, ColorMode.RGB}

    @property
    def available(self) -> bool:
        """Return availability from the runtime."""
        return self._runtime.available

    @property
    def device_info(self):
        """Return shared device-registry info."""
        return self._runtime.device_info

    @property
    def is_on(self) -> bool | None:
        """Return the light on/off state."""
        return self._runtime.is_on

    @property
    def brightness(self) -> int | None:
        """Return HA brightness."""
        return self._runtime.brightness

    @property
    def color_temp_kelvin(self) -> int | None:
        """Return color temperature in Kelvin."""
        return self._runtime.color_temp_kelvin

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        """Return RGB color."""
        return self._runtime.rgb_color

    @property
    def color_mode(self):
        """Return the active color mode."""
        if self._runtime.mode == "colour":
            return ColorMode.RGB
        return ColorMode.COLOR_TEMP

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
        """Turn the light on with optional attributes."""
        await self._runtime.async_turn_on(
            brightness=kwargs.get("brightness"),
            rgb_color=kwargs.get("rgb_color"),
            color_temp_kelvin=kwargs.get("color_temp_kelvin"),
        )

    async def async_turn_off(self, **kwargs) -> None:
        """Turn the light off."""
        await self._runtime.async_turn_off()

    def _handle_runtime_update(self) -> None:
        if hasattr(self, "async_write_ha_state"):
            self.async_write_ha_state()
