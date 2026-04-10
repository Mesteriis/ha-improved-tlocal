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
    components = types.ModuleType("homeassistant.components")
    components_diagnostics = types.ModuleType("homeassistant.components.diagnostics")
    components_system_health = types.ModuleType("homeassistant.components.system_health")
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
    components_system_health.SystemHealthRegistration = FakeSystemHealthRegistration

    helpers_storage.Store = FakeStore
    helpers_typing.ConfigType = dict[str, Any]
    helpers_cv.string = vol.Coerce(str)
    helpers_cv.boolean = vol.Boolean()

    homeassistant.core = core
    homeassistant.helpers = helpers
    homeassistant.components = components
    helpers.storage = helpers_storage
    helpers.typing = helpers_typing
    helpers.config_validation = helpers_cv
    components.diagnostics = components_diagnostics
    components.system_health = components_system_health

    sys.modules["homeassistant"] = homeassistant
    sys.modules["homeassistant.core"] = core
    sys.modules["homeassistant.helpers"] = helpers
    sys.modules["homeassistant.components"] = components
    sys.modules["homeassistant.components.diagnostics"] = components_diagnostics
    sys.modules["homeassistant.components.system_health"] = components_system_health
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
