"""Test scaffolding for ImprovedTLocal."""

from __future__ import annotations

import sys
import types
from dataclasses import dataclass, field
from pathlib import Path
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


class FakeHass:
    """Small Home Assistant stand-in for unit tests."""

    def __init__(self) -> None:
        self.data: dict[str, Any] = {}
        self.services = FakeServiceRegistry()


def _install_homeassistant_stubs() -> None:
    """Install minimal Home Assistant modules for unit tests."""
    if "homeassistant" in sys.modules:
        return

    homeassistant = types.ModuleType("homeassistant")
    core = types.ModuleType("homeassistant.core")
    helpers = types.ModuleType("homeassistant.helpers")
    helpers_storage = types.ModuleType("homeassistant.helpers.storage")
    helpers_typing = types.ModuleType("homeassistant.helpers.typing")
    helpers_cv = types.ModuleType("homeassistant.helpers.config_validation")

    core.HomeAssistant = FakeHass
    core.ServiceCall = FakeServiceCall
    core.SupportsResponse = FakeSupportsResponse
    helpers_storage.Store = FakeStore
    helpers_typing.ConfigType = dict[str, Any]
    helpers_cv.string = vol.Coerce(str)
    helpers_cv.boolean = vol.Boolean()

    homeassistant.core = core
    homeassistant.helpers = helpers
    helpers.storage = helpers_storage
    helpers.typing = helpers_typing
    helpers.config_validation = helpers_cv

    sys.modules["homeassistant"] = homeassistant
    sys.modules["homeassistant.core"] = core
    sys.modules["homeassistant.helpers"] = helpers
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
