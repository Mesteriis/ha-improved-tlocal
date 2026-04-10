"""Runtime entity plumbing for ImprovedTLocal."""

from __future__ import annotations

import asyncio
import colorsys
import json
from collections.abc import Callable
from time import monotonic
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import discovery

from .const import (
    DOMAIN,
    TEMPLATE_SMART_LIGHT_RGBCW,
    TEMPLATE_SMART_PLUG_BASIC,
    TEMPLATE_SMART_PLUG_POWER,
)
from .credentials import FileSnapshotCredentialsStore
from .models import BindingRecord, DeviceTemplate, InventoryDevice
from .templates import get_template, select_template_for_device
from .transport import TinyTuyaBulbTransport, TinyTuyaPlugTransport

PLATFORMS: tuple[str, ...] = ("switch", "sensor", "light")


async def async_setup_runtime_platforms(hass: HomeAssistant) -> None:
    """Load runtime platforms for dynamic entity registration."""
    for platform in PLATFORMS:
        await discovery.async_load_platform(hass, platform, DOMAIN, {}, {})


class PlugRuntimeRegistry:
    """Track bound plug runtimes and add matching entities to platforms."""

    def __init__(self, hass: HomeAssistant, manager) -> None:
        """Initialize the runtime registry."""
        self.hass = hass
        self.manager = manager
        self.credentials_store = FileSnapshotCredentialsStore()
        self.transport = TinyTuyaPlugTransport()
        self.light_transport = TinyTuyaBulbTransport()
        self._platform_adders: dict[str, list[Callable[..., Any]]] = {}
        self._runtimes: dict[str, Any] = {}
        self._added_unique_ids: set[str] = set()

    async def async_register_platform(self, platform: str, async_add_entities) -> None:
        """Register one runtime platform callback and backfill entities."""
        self._platform_adders.setdefault(platform, []).append(async_add_entities)
        await self.async_sync_entities()

    async def async_sync_entities(self) -> None:
        """Ensure bound supported devices have runtime entities."""
        bindings = await self.manager.storage.async_load_bindings()
        report = await self.manager.storage.async_load_discovery_report()

        for device_id, binding in bindings.items():
            device = await self.manager._async_get_inventory_device(device_id, report)
            if device is None:
                continue

            template = _resolve_runtime_template(device, binding)
            if template is None or template.family not in {"smart_plug", "smart_light"}:
                continue

            runtime = self._runtimes.get(device_id)
            if runtime is None:
                runtime = self._build_runtime(device, binding, template)
                self._runtimes[device_id] = runtime
            else:
                runtime.update(binding=binding, device=device, template=template)

            await self._async_add_runtime_entities(runtime)

    def summary(self) -> dict[str, Any]:
        """Return a compact runtime summary."""
        return {
            "runtime_device_count": len(self._runtimes),
            "loaded_platform_count": len(self._platform_adders),
            "loaded_platforms": sorted(self._platform_adders),
            "registered_entity_count": len(self._added_unique_ids),
            "registered_entity_ids": sorted(self._added_unique_ids),
        }

    async def _async_add_runtime_entities(self, runtime: "BoundPlugRuntime") -> None:
        """Add missing entities for one runtime to registered platforms."""
        from .light import build_runtime_light_entities
        from .sensor import build_runtime_sensor_entities
        from .switch import build_runtime_switch_entities

        platform_entities: dict[str, list[Any]] = {
            "switch": build_runtime_switch_entities(runtime),
            "sensor": build_runtime_sensor_entities(runtime),
            "light": build_runtime_light_entities(runtime),
        }

        for platform, entities in platform_entities.items():
            adders = self._platform_adders.get(platform, [])
            if not adders:
                continue

            fresh_entities = [entity for entity in entities if entity.unique_id not in self._added_unique_ids]
            if not fresh_entities:
                continue

            for entity in fresh_entities:
                self._added_unique_ids.add(entity.unique_id)

            for async_add_entities in adders:
                async_add_entities(fresh_entities, True)

    def _build_runtime(self, device: InventoryDevice, binding: BindingRecord, template: DeviceTemplate):
        """Construct one runtime object for the resolved template family."""
        if template.family == "smart_plug":
            return BoundPlugRuntime(
                hass=self.hass,
                device=device,
                binding=binding,
                template=template,
                credentials_store=self.credentials_store,
                transport=self.transport,
            )
        if template.family == "smart_light":
            return BoundLightRuntime(
                hass=self.hass,
                device=device,
                binding=binding,
                template=template,
                credentials_store=self.credentials_store,
                transport=self.light_transport,
            )
        raise ValueError(f"Unsupported runtime family: {template.family}")


class BoundPlugRuntime:
    """Single-device runtime state for a bound smart plug."""

    def __init__(
        self,
        *,
        hass: HomeAssistant,
        device: InventoryDevice,
        binding: BindingRecord,
        template: DeviceTemplate,
        credentials_store: FileSnapshotCredentialsStore,
        transport: TinyTuyaPlugTransport,
    ) -> None:
        """Initialize the runtime state."""
        self.hass = hass
        self.device = device
        self.binding = binding
        self.template = template
        self.credentials_store = credentials_store
        self.transport = transport
        self._status_payload: dict[str, Any] = {}
        self._available = False
        self._lock = asyncio.Lock()
        self._listeners: list[Callable[[], None]] = []
        self._last_refresh_monotonic = 0.0
        self._refresh_cache_seconds = 2.0

    def update(self, *, binding: BindingRecord, device: InventoryDevice, template: DeviceTemplate) -> None:
        """Update runtime context after rebind or metadata refresh."""
        self.binding = binding
        self.device = device
        self.template = template

    @property
    def device_id(self) -> str:
        """Return the canonical device id."""
        return self.device.device_id

    @property
    def available(self) -> bool:
        """Return whether the latest poll succeeded."""
        return self._available

    @property
    def name(self) -> str:
        """Return the display name."""
        return self.device.name

    @property
    def unique_id_prefix(self) -> str:
        """Return the stable unique-id prefix."""
        return self.device.device_id

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device-registry information."""
        info = {
            "identifiers": {(DOMAIN, self.device.device_id)},
            "name": self.device.name,
            "manufacturer": "Tuya",
            "model": self.device.model or self.device.model_id or self.device.product_id or "Smart Plug",
        }
        if self.device.mac:
            info["connections"] = {("mac", self.device.mac.lower())}
        return info

    async def async_refresh(self, *, force: bool = False) -> None:
        """Refresh state from the bound device."""
        async with self._lock:
            if not force and (monotonic() - self._last_refresh_monotonic) < self._refresh_cache_seconds:
                return

            credentials = await self.credentials_store.async_get_credentials(self.hass, self.device.device_id)
            if credentials is None:
                self._available = False
                self._status_payload = {}
                self._notify_listeners()
                return

            try:
                payload = await self.transport.async_status(self.binding, credentials)
            except Exception:
                self._available = False
                self._status_payload = {}
                self._last_refresh_monotonic = monotonic()
                self._notify_listeners()
                return

            self._status_payload = payload if isinstance(payload, dict) else {}
            self._available = isinstance(self._status_payload.get("dps"), dict)
            self._last_refresh_monotonic = monotonic()
            self._notify_listeners()

    async def async_set_switch(self, on: bool) -> None:
        """Change the main switch state."""
        async with self._lock:
            credentials = await self.credentials_store.async_get_credentials(self.hass, self.device.device_id)
            if credentials is None:
                self._available = False
                self._status_payload = {}
                self._notify_listeners()
                return

            payload = await self.transport.async_set_switch(
                self.binding,
                credentials,
                on=on,
                switch=self.switch_dp_index,
            )
            self._status_payload = payload if isinstance(payload, dict) else {}
            self._available = isinstance(self._status_payload.get("dps"), dict)
            self._last_refresh_monotonic = monotonic()
            self._notify_listeners()

    def register_listener(self, callback: Callable[[], None]) -> Callable[[], None]:
        """Register a state listener and return an unsubscribe function."""
        self._listeners.append(callback)

        def _remove() -> None:
            if callback in self._listeners:
                self._listeners.remove(callback)

        return _remove

    @property
    def switch_dp_index(self) -> int:
        """Return the primary switch DP index."""
        return int(self.dp_index_for_code("switch_1") or 1)

    def dp_index_for_code(self, code: str) -> str | None:
        """Return the DP index for one Tuya code."""
        schema = self.device.dp_schema
        if not isinstance(schema, dict):
            return None
        for index, meta in schema.items():
            if isinstance(meta, dict) and str(meta.get("code")) == code:
                return str(index)
        return None

    def has_code(self, code: str) -> bool:
        """Return whether the device exposes one DP code."""
        return self.dp_index_for_code(code) is not None

    @property
    def is_on(self) -> bool | None:
        """Return the switch state when known."""
        return self._raw_bool("switch_1")

    def scaled_value(self, code: str) -> float | None:
        """Return one DP value scaled according to schema metadata."""
        raw = self._raw_value(code)
        if raw is None:
            return None

        scale = self._scale_for_code(code)
        try:
            numeric = float(raw)
        except (TypeError, ValueError):
            return None
        return numeric / (10**scale)

    def _raw_bool(self, code: str) -> bool | None:
        raw = self._raw_value(code)
        if raw is None:
            return None
        return bool(raw)

    def _raw_value(self, code: str) -> Any:
        index = self.dp_index_for_code(code)
        dps = self._status_payload.get("dps")
        if index is None or not isinstance(dps, dict):
            return None
        return dps.get(index)

    def _scale_for_code(self, code: str) -> int:
        index = self.dp_index_for_code(code)
        schema = self.device.dp_schema
        if index is None or not isinstance(schema, dict):
            return 0
        meta = schema.get(index)
        if not isinstance(meta, dict):
            return 0
        values = meta.get("values")
        if not isinstance(values, dict):
            return 0
        try:
            return int(values.get("scale", 0))
        except (TypeError, ValueError):
            return 0

    def _notify_listeners(self) -> None:
        for callback in list(self._listeners):
            callback()


class BoundLightRuntime:
    """Single-device runtime state for a bound smart light."""

    def __init__(
        self,
        *,
        hass: HomeAssistant,
        device: InventoryDevice,
        binding: BindingRecord,
        template: DeviceTemplate,
        credentials_store: FileSnapshotCredentialsStore,
        transport: TinyTuyaBulbTransport,
    ) -> None:
        """Initialize the light runtime state."""
        self.hass = hass
        self.device = device
        self.binding = binding
        self.template = template
        self.credentials_store = credentials_store
        self.transport = transport
        self._status_payload: dict[str, Any] = {}
        self._available = False
        self._lock = asyncio.Lock()
        self._listeners: list[Callable[[], None]] = []
        self._last_refresh_monotonic = 0.0
        self._refresh_cache_seconds = 2.0

    def update(self, *, binding: BindingRecord, device: InventoryDevice, template: DeviceTemplate) -> None:
        """Update runtime context after rebind or metadata refresh."""
        self.binding = binding
        self.device = device
        self.template = template

    @property
    def device_id(self) -> str:
        """Return the canonical device id."""
        return self.device.device_id

    @property
    def available(self) -> bool:
        """Return whether the latest poll succeeded."""
        return self._available

    @property
    def name(self) -> str:
        """Return the display name."""
        return self.device.name

    @property
    def unique_id_prefix(self) -> str:
        """Return the stable unique-id prefix."""
        return self.device.device_id

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device-registry information."""
        info = {
            "identifiers": {(DOMAIN, self.device.device_id)},
            "name": self.device.name,
            "manufacturer": "Tuya",
            "model": self.device.model or self.device.model_id or self.device.product_id or "Smart Light",
        }
        if self.device.mac:
            info["connections"] = {("mac", self.device.mac.lower())}
        return info

    async def async_refresh(self, *, force: bool = False) -> None:
        """Refresh state from the bound device."""
        async with self._lock:
            if not force and (monotonic() - self._last_refresh_monotonic) < self._refresh_cache_seconds:
                return

            credentials = await self.credentials_store.async_get_credentials(self.hass, self.device.device_id)
            if credentials is None:
                self._available = False
                self._status_payload = {}
                self._notify_listeners()
                return

            try:
                payload = await self.transport.async_status(self.binding, credentials)
            except Exception:
                self._available = False
                self._status_payload = {}
                self._last_refresh_monotonic = monotonic()
                self._notify_listeners()
                return

            self._status_payload = payload if isinstance(payload, dict) else {}
            self._available = isinstance(self._status_payload.get("dps"), dict)
            self._last_refresh_monotonic = monotonic()
            self._notify_listeners()

    async def async_turn_off(self) -> None:
        """Turn the light off."""
        async with self._lock:
            credentials = await self.credentials_store.async_get_credentials(self.hass, self.device.device_id)
            if credentials is None:
                self._available = False
                self._status_payload = {}
                self._notify_listeners()
                return
            payload = await self.transport.async_turn_off(self.binding, credentials)
            self._status_payload = payload if isinstance(payload, dict) else {}
            self._available = isinstance(self._status_payload.get("dps"), dict)
            self._last_refresh_monotonic = monotonic()
            self._notify_listeners()

    async def async_turn_on(
        self,
        *,
        brightness: int | None = None,
        rgb_color: tuple[int, int, int] | None = None,
        color_temp_kelvin: int | None = None,
    ) -> None:
        """Turn the light on with optional white or RGB settings."""
        async with self._lock:
            credentials = await self.credentials_store.async_get_credentials(self.hass, self.device.device_id)
            if credentials is None:
                self._available = False
                self._status_payload = {}
                self._notify_listeners()
                return

            if rgb_color is not None:
                scaled_rgb = _scale_rgb_for_brightness(rgb_color, brightness)
                payload = await self.transport.async_set_colour(self.binding, credentials, rgb=scaled_rgb)
            elif brightness is not None or color_temp_kelvin is not None:
                brightness_pct = _ha_brightness_to_percentage(brightness if brightness is not None else self.brightness)
                colourtemp_pct = _kelvin_to_percentage(
                    color_temp_kelvin if color_temp_kelvin is not None else self.color_temp_kelvin
                )
                payload = await self.transport.async_set_white(
                    self.binding,
                    credentials,
                    brightness_percentage=brightness_pct,
                    colourtemp_percentage=colourtemp_pct,
                )
            else:
                payload = await self.transport.async_turn_on(self.binding, credentials)

            self._status_payload = payload if isinstance(payload, dict) else {}
            self._available = isinstance(self._status_payload.get("dps"), dict)
            self._last_refresh_monotonic = monotonic()
            self._notify_listeners()

    def register_listener(self, callback: Callable[[], None]) -> Callable[[], None]:
        """Register a state listener and return an unsubscribe function."""
        self._listeners.append(callback)

        def _remove() -> None:
            if callback in self._listeners:
                self._listeners.remove(callback)

        return _remove

    def dp_index_for_code(self, code: str) -> str | None:
        """Return the DP index for one Tuya code."""
        schema = self.device.dp_schema
        if not isinstance(schema, dict):
            return None
        for index, meta in schema.items():
            if isinstance(meta, dict) and str(meta.get("code")) == code:
                return str(index)
        return None

    def has_code(self, code: str) -> bool:
        """Return whether the device exposes one DP code."""
        return self.dp_index_for_code(code) is not None

    @property
    def is_on(self) -> bool | None:
        """Return the switch state when known."""
        return self._raw_bool("switch_led")

    @property
    def mode(self) -> str | None:
        """Return the current work mode."""
        raw = self._raw_value("work_mode")
        return str(raw) if raw is not None else None

    @property
    def brightness(self) -> int | None:
        """Return Home Assistant brightness 0-255."""
        raw = self._raw_value("bright_value_v2")
        if raw is None:
            return None
        return _tuya_scaled_to_ha_brightness(float(raw), self._range_for_code("bright_value_v2"))

    @property
    def color_temp_kelvin(self) -> int | None:
        """Return an approximate colour temperature in Kelvin."""
        raw = self._raw_value("temp_value_v2")
        if raw is None:
            return None
        value_range = self._range_for_code("temp_value_v2")
        percentage = _tuya_range_to_percentage(float(raw), value_range)
        return _percentage_to_kelvin(percentage)

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        """Return RGB color when the bulb is in colour mode."""
        colour = self._raw_value("colour_data_v2")
        if colour is None:
            return None
        if isinstance(colour, str):
            try:
                colour = json.loads(colour)
            except ValueError:
                return None
        if not isinstance(colour, dict):
            return None

        try:
            hue = float(colour.get("h", 0))
            sat = float(colour.get("s", 0)) / 1000.0
            val = float(colour.get("v", 0)) / 1000.0
        except (TypeError, ValueError):
            return None

        red, green, blue = colorsys.hsv_to_rgb(hue / 360.0, sat, val)
        return (round(red * 255), round(green * 255), round(blue * 255))

    def _raw_bool(self, code: str) -> bool | None:
        raw = self._raw_value(code)
        if raw is None:
            return None
        return bool(raw)

    def _raw_value(self, code: str) -> Any:
        index = self.dp_index_for_code(code)
        dps = self._status_payload.get("dps")
        if index is None or not isinstance(dps, dict):
            return None
        return dps.get(index)

    def _range_for_code(self, code: str) -> tuple[float, float]:
        """Return the min/max range declared for one DP code."""
        index = self.dp_index_for_code(code)
        schema = self.device.dp_schema
        if index is None or not isinstance(schema, dict):
            return (0.0, 1000.0)
        meta = schema.get(index)
        if not isinstance(meta, dict):
            return (0.0, 1000.0)
        values = meta.get("values")
        if not isinstance(values, dict):
            return (0.0, 1000.0)
        try:
            return (float(values.get("min", 0.0)), float(values.get("max", 1000.0)))
        except (TypeError, ValueError):
            return (0.0, 1000.0)

    def _notify_listeners(self) -> None:
        for callback in list(self._listeners):
            callback()


def _resolve_runtime_template(device: InventoryDevice, binding: BindingRecord) -> DeviceTemplate | None:
    """Resolve one supported runtime template for a bound device."""
    if binding.template_id:
        template = get_template(binding.template_id)
        if template is not None:
            return template
    return select_template_for_device(device)


def is_supported_runtime_template(template_id: str | None) -> bool:
    """Return whether a template has runtime entity support in v0.1."""
    return template_id in {
        TEMPLATE_SMART_PLUG_POWER,
        TEMPLATE_SMART_PLUG_BASIC,
        TEMPLATE_SMART_LIGHT_RGBCW,
    }


def _tuya_scaled_to_ha_brightness(value: float, value_range: tuple[float, float]) -> int:
    """Convert a Tuya DP brightness into HA brightness."""
    min_value, max_value = value_range
    if max_value <= min_value:
        return 255
    normalized = max(0.0, min(1.0, (value - min_value) / (max_value - min_value)))
    return round(normalized * 255)


def _tuya_range_to_percentage(value: float, value_range: tuple[float, float]) -> int:
    """Convert a Tuya DP value into a 0-100 percentage."""
    min_value, max_value = value_range
    if max_value <= min_value:
        return 0
    normalized = max(0.0, min(1.0, (value - min_value) / (max_value - min_value)))
    return round(normalized * 100)


def _ha_brightness_to_percentage(brightness: int | None) -> int:
    """Convert HA brightness into percentage for TinyTuya."""
    if brightness is None:
        return 100
    clamped = max(0, min(255, int(brightness)))
    return round(clamped * 100 / 255)


def _percentage_to_kelvin(percentage: int) -> int:
    """Map a white-temperature percentage to an approximate Kelvin value."""
    clamped = max(0, min(100, int(percentage)))
    return round(6500 - ((6500 - 2700) * clamped / 100))


def _kelvin_to_percentage(kelvin: int | None) -> int:
    """Map approximate Kelvin back to the Tuya percentage domain."""
    if kelvin is None:
        return 0
    clamped = max(2700, min(6500, int(kelvin)))
    return round((6500 - clamped) * 100 / (6500 - 2700))


def _scale_rgb_for_brightness(rgb: tuple[int, int, int], brightness: int | None) -> tuple[int, int, int]:
    """Scale RGB channels to match an optional HA brightness value."""
    if brightness is None:
        return tuple(max(0, min(255, int(channel))) for channel in rgb)
    factor = max(0.0, min(1.0, brightness / 255.0))
    return tuple(max(0, min(255, round(int(channel) * factor))) for channel in rgb)
