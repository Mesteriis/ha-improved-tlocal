"""Thin TinyTuya transport for ImprovedTLocal runtime."""

from __future__ import annotations

import asyncio
from typing import Any

from .credentials import DeviceCredentials
from .models import BindingRecord


class TinyTuyaPlugTransport:
    """Minimal runtime transport for Tuya smart plugs."""

    async def async_status(self, binding: BindingRecord, credentials: DeviceCredentials) -> dict[str, Any]:
        """Fetch current DPS state from the device."""
        return await asyncio.to_thread(self._status_sync, binding, credentials)

    async def async_set_switch(
        self,
        binding: BindingRecord,
        credentials: DeviceCredentials,
        *,
        on: bool,
        switch: int = 1,
    ) -> dict[str, Any]:
        """Write a switch state and then return current status."""
        return await asyncio.to_thread(self._set_switch_sync, binding, credentials, on, switch)

    def _status_sync(self, binding: BindingRecord, credentials: DeviceCredentials) -> dict[str, Any]:
        """Run a blocking TinyTuya status request."""
        tinytuya = _import_tinytuya()
        device = self._build_device(tinytuya, binding, credentials)
        try:
            payload = device.status()
            if not isinstance(payload, dict):
                raise RuntimeError("TinyTuya returned a non-dict status payload")
            return payload
        finally:
            device.close()

    def _set_switch_sync(
        self,
        binding: BindingRecord,
        credentials: DeviceCredentials,
        on: bool,
        switch: int,
    ) -> dict[str, Any]:
        """Run a blocking TinyTuya state write and follow-up status fetch."""
        tinytuya = _import_tinytuya()
        device = self._build_device(tinytuya, binding, credentials)
        try:
            device.set_status(on, switch=switch)
            payload = device.status()
            if not isinstance(payload, dict):
                raise RuntimeError("TinyTuya returned a non-dict status payload")
            return payload
        finally:
            device.close()

    def _build_device(self, tinytuya, binding: BindingRecord, credentials: DeviceCredentials):
        """Construct a TinyTuya device instance for one binding."""
        version_text = credentials.protocol_version or binding.bound_protocol_version or "3.3"
        version = float(version_text)
        device = tinytuya.OutletDevice(
            binding.device_id,
            address=binding.bound_ip,
            local_key=credentials.local_key,
            version=version,
            port=binding.bound_port,
            persist=False,
            connection_timeout=5,
        )
        device.set_version(version)
        device.set_retry(False)
        return device


def _import_tinytuya():
    """Import TinyTuya lazily so tests do not require the package."""
    try:
        import tinytuya  # type: ignore
    except ImportError as exc:  # pragma: no cover - depends on runtime environment
        raise RuntimeError("tinytuya is required for ImprovedTLocal runtime control") from exc
    return tinytuya
