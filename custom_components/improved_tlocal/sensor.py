"""Sensor platform for ImprovedTLocal runtime plugs."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import SensorEntity

from .const import DATA_MANAGER, DOMAIN, TEMPLATE_SMART_PLUG_POWER


@dataclass(frozen=True, slots=True)
class PlugMetricSpec:
    """Description of one runtime metric sensor."""

    key: str
    code: str
    suffix: str
    unit: str


POWER_SPECS: tuple[PlugMetricSpec, ...] = (
    PlugMetricSpec("power", "cur_power", "Power", "W"),
    PlugMetricSpec("current", "cur_current", "Current", "A"),
    PlugMetricSpec("voltage", "cur_voltage", "Voltage", "V"),
    PlugMetricSpec("energy", "add_ele", "Energy", "kWh"),
)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None) -> None:
    """Set up runtime sensor entities."""
    manager = hass.data.get(DOMAIN, {}).get(DATA_MANAGER)
    if manager is None:
        return
    await manager.async_register_runtime_platform("sensor", async_add_entities)


def build_runtime_sensor_entities(runtime) -> list["ImprovedTLocalPlugMetricSensor"]:
    """Build sensor entities for one runtime."""
    if runtime.template.template_id != TEMPLATE_SMART_PLUG_POWER:
        return []

    return [
        ImprovedTLocalPlugMetricSensor(runtime, spec)
        for spec in POWER_SPECS
        if runtime.has_code(spec.code)
    ]


class ImprovedTLocalPlugMetricSensor(SensorEntity):
    """Metric sensor backed by one shared plug runtime."""

    _attr_should_poll = True

    def __init__(self, runtime, spec: PlugMetricSpec) -> None:
        """Initialize the metric sensor."""
        self._runtime = runtime
        self.entity_description = spec
        self._remove_listener = None
        self._attr_unique_id = f"{runtime.unique_id_prefix}_{spec.key}"
        self._attr_name = f"{runtime.name} {spec.suffix}"
        self._attr_native_unit_of_measurement = spec.unit

    @property
    def available(self) -> bool:
        """Return availability from the runtime."""
        return self._runtime.available

    @property
    def native_value(self) -> float | None:
        """Return the current metric value."""
        value = self._runtime.scaled_value(self.entity_description.code)
        return round(value, 3) if value is not None else None

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

    def _handle_runtime_update(self) -> None:
        if hasattr(self, "async_write_ha_state"):
            self.async_write_ha_state()
