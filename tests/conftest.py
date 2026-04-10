"""Test scaffolding for ImprovedTLocal."""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import mkdtemp
from typing import Any

import pytest
import voluptuous as vol

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class FakeStore:
    """Minimal in-memory replacement for Home Assistant Store."""

    _payloads: dict[str, Any] = {}

    def __init__(self, hass: Any, version: int, key: str) -> None:
        self.hass = hass
        self.version = version
        self.key = key

    async def async_load(self) -> Any:
        """Load the payload from memory."""
        return self._payloads.get(self.key)

    async def async_save(self, payload: Any) -> None:
        """Persist the payload in memory."""
        self._payloads[self.key] = payload

    @classmethod
    def reset(cls) -> None:
        """Clear in-memory payloads between tests."""
        cls._payloads = {}


@dataclass
class FakeServiceCall:
    """Small service-call holder."""

    data: dict[str, Any] = field(default_factory=dict)


class FakeSupportsResponse:
    """Compatibility shim for Home Assistant SupportsResponse enum."""

    ONLY = "only"


class FakeSystemHealthRegistration:
    """Capture system health registrations for assertions."""

    def __init__(self) -> None:
        self.domain: str | None = None
        self.callback: Any | None = None

    def async_register_info(self, callback: Any, manage_url: str | None = None) -> None:
        """Store the registered callback."""
        self.callback = callback


class FakeEntity:
    """Minimal entity base class for runtime platform tests."""

    _attr_unique_id: str | None = None
    _attr_name: str | None = None
    _attr_native_unit_of_measurement: str | None = None
    _attr_should_poll = False

    @property
    def unique_id(self) -> str | None:
        return self._attr_unique_id

    @property
    def name(self) -> str | None:
        return self._attr_name

    def async_write_ha_state(self) -> None:
        """No-op state writer for tests."""


class FakeSensorEntity(FakeEntity):
    """Minimal sensor entity stub."""


class FakeSwitchEntity(FakeEntity):
    """Minimal switch entity stub."""


class FakeLightEntity(FakeEntity):
    """Minimal light entity stub."""


class FakeColorMode:
    """Minimal color mode namespace."""

    COLOR_TEMP = "color_temp"
    RGB = "rgb"
    BRIGHTNESS = "brightness"
    ONOFF = "onoff"


class FakeServiceRegistry:
    """Capture service registrations for assertions."""

    def __init__(self) -> None:
        self.registered: dict[tuple[str, str], dict[str, Any]] = {}

    def async_register(
        self,
        domain: str,
        service: str,
        handler: Any,
        *,
        schema: Any | None = None,
        supports_response: Any | None = None,
    ) -> None:
        """Store the registration parameters."""
        self.registered[(domain, service)] = {
            "handler": handler,
            "schema": schema,
            "supports_response": supports_response,
        }


class FakeConfig:
    """Small Home Assistant config helper with a path() method."""

    def __init__(self) -> None:
        self.base_path = Path(mkdtemp(prefix="improved_tlocal_tests_"))

    def path(self, *parts: str) -> str:
        """Resolve a path below the temporary config root."""
        return str(self.base_path.joinpath(*parts))


class FakeHass:
    """Small Home Assistant stand-in for unit tests."""

    def __init__(self) -> None:
        self.data: dict[str, Any] = {}
        self.services = FakeServiceRegistry()
        self.config = FakeConfig()


def _install_homeassistant_stubs() -> None:
    """Install minimal Home Assistant modules for unit tests."""
    if "homeassistant" in sys.modules:
        return

    homeassistant = types.ModuleType("homeassistant")
    core = types.ModuleType("homeassistant.core")
    helpers = types.ModuleType("homeassistant.helpers")
    helpers_discovery = types.ModuleType("homeassistant.helpers.discovery")
    components = types.ModuleType("homeassistant.components")
    components_diagnostics = types.ModuleType("homeassistant.components.diagnostics")
    components_light = types.ModuleType("homeassistant.components.light")
    components_sensor = types.ModuleType("homeassistant.components.sensor")
    components_system_health = types.ModuleType("homeassistant.components.system_health")
    components_switch = types.ModuleType("homeassistant.components.switch")
    helpers_storage = types.ModuleType("homeassistant.helpers.storage")
    helpers_typing = types.ModuleType("homeassistant.helpers.typing")
    helpers_cv = types.ModuleType("homeassistant.helpers.config_validation")

    core.HomeAssistant = FakeHass
    core.ServiceCall = FakeServiceCall
    core.SupportsResponse = FakeSupportsResponse
    core.callback = lambda func: func

    def _async_redact_data(data: Any, to_redact: set[str] | tuple[str, ...] | list[str]) -> Any:
        redact_keys = set(to_redact)

        def _redact(value: Any) -> Any:
            if isinstance(value, dict):
                return {
                    key: "**REDACTED**" if key in redact_keys else _redact(item)
                    for key, item in value.items()
                }
            if isinstance(value, list):
                return [_redact(item) for item in value]
            return value

        return _redact(data)

    components_diagnostics.async_redact_data = _async_redact_data
    components_light.ColorMode = FakeColorMode
    components_light.LightEntity = FakeLightEntity
    components_system_health.SystemHealthRegistration = FakeSystemHealthRegistration
    components_sensor.SensorEntity = FakeSensorEntity
    components_switch.SwitchEntity = FakeSwitchEntity

    async def _async_load_platform(hass: Any, component: str, platform: str, discovered: Any, hass_config: Any) -> None:
        return None

    helpers_discovery.async_load_platform = _async_load_platform

    helpers_storage.Store = FakeStore
    helpers_typing.ConfigType = dict[str, Any]
    helpers_cv.string = vol.Coerce(str)
    helpers_cv.boolean = vol.Boolean()

    homeassistant.core = core
    homeassistant.helpers = helpers
    homeassistant.components = components
    helpers.discovery = helpers_discovery
    helpers.storage = helpers_storage
    helpers.typing = helpers_typing
    helpers.config_validation = helpers_cv
    components.diagnostics = components_diagnostics
    components.light = components_light
    components.sensor = components_sensor
    components.system_health = components_system_health
    components.switch = components_switch

    sys.modules["homeassistant"] = homeassistant
    sys.modules["homeassistant.core"] = core
    sys.modules["homeassistant.helpers"] = helpers
    sys.modules["homeassistant.helpers.discovery"] = helpers_discovery
    sys.modules["homeassistant.components"] = components
    sys.modules["homeassistant.components.diagnostics"] = components_diagnostics
    sys.modules["homeassistant.components.light"] = components_light
    sys.modules["homeassistant.components.sensor"] = components_sensor
    sys.modules["homeassistant.components.system_health"] = components_system_health
    sys.modules["homeassistant.components.switch"] = components_switch
    sys.modules["homeassistant.helpers.storage"] = helpers_storage
    sys.modules["homeassistant.helpers.typing"] = helpers_typing
    sys.modules["homeassistant.helpers.config_validation"] = helpers_cv


_install_homeassistant_stubs()


@pytest.fixture(autouse=True)
def reset_fake_store() -> None:
    """Reset global fake store state before each test."""
    FakeStore.reset()


@pytest.fixture
def hass() -> FakeHass:
    """Return a fresh fake Home Assistant object."""
    return FakeHass()
