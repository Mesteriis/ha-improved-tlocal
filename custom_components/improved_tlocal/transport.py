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


class TinyTuyaBulbTransport:
    """Minimal runtime transport for Tuya bulbs."""

    async def async_status(self, binding: BindingRecord, credentials: DeviceCredentials) -> dict[str, Any]:
        """Fetch current DPS state from the bulb."""
        return await asyncio.to_thread(self._status_sync, binding, credentials)

    async def async_turn_on(self, binding: BindingRecord, credentials: DeviceCredentials) -> dict[str, Any]:
        """Turn the bulb on and return the resulting status."""
        return await asyncio.to_thread(self._turn_on_sync, binding, credentials)

    async def async_turn_off(self, binding: BindingRecord, credentials: DeviceCredentials) -> dict[str, Any]:
        """Turn the bulb off and return the resulting status."""
        return await asyncio.to_thread(self._turn_off_sync, binding, credentials)

    async def async_set_white(
        self,
        binding: BindingRecord,
        credentials: DeviceCredentials,
        *,
        brightness_percentage: int,
        colourtemp_percentage: int,
    ) -> dict[str, Any]:
        """Set white mode with brightness and colour temperature percentages."""
        return await asyncio.to_thread(
            self._set_white_sync,
            binding,
            credentials,
            brightness_percentage,
            colourtemp_percentage,
        )

    async def async_set_colour(
        self,
        binding: BindingRecord,
        credentials: DeviceCredentials,
        *,
        rgb: tuple[int, int, int],
    ) -> dict[str, Any]:
        """Set RGB colour and return the resulting status."""
        return await asyncio.to_thread(self._set_colour_sync, binding, credentials, rgb)

    def _status_sync(self, binding: BindingRecord, credentials: DeviceCredentials) -> dict[str, Any]:
        return self._run_with_candidate_versions(
            binding,
            credentials,
            lambda device: device.status(),
        )

    def _turn_on_sync(self, binding: BindingRecord, credentials: DeviceCredentials) -> dict[str, Any]:
        return self._run_with_candidate_versions(
            binding,
            credentials,
            lambda device: _execute_and_status(device, lambda: device.turn_on()),
        )

    def _turn_off_sync(self, binding: BindingRecord, credentials: DeviceCredentials) -> dict[str, Any]:
        return self._run_with_candidate_versions(
            binding,
            credentials,
            lambda device: _execute_and_status(device, lambda: device.turn_off()),
        )

    def _set_white_sync(
        self,
        binding: BindingRecord,
        credentials: DeviceCredentials,
        brightness_percentage: int,
        colourtemp_percentage: int,
    ) -> dict[str, Any]:
        return self._run_with_candidate_versions(
            binding,
            credentials,
            lambda device: _execute_and_status(
                device,
                lambda: device.set_white_percentage(
                    brightness=brightness_percentage,
                    colourtemp=colourtemp_percentage,
                ),
            ),
        )

    def _set_colour_sync(
        self,
        binding: BindingRecord,
        credentials: DeviceCredentials,
        rgb: tuple[int, int, int],
    ) -> dict[str, Any]:
        return self._run_with_candidate_versions(
            binding,
            credentials,
            lambda device: _execute_and_status(device, lambda: device.set_colour(*rgb)),
        )

    def _run_with_candidate_versions(self, binding: BindingRecord, credentials: DeviceCredentials, operation) -> dict[str, Any]:
        """Try bulb operations across protocol candidates until one succeeds."""
        tinytuya = _import_tinytuya()
        last_payload: dict[str, Any] | None = None
        last_error: Exception | None = None

        for version in _candidate_versions(credentials.protocol_version or binding.bound_protocol_version, ["3.5", "3.4", "3.3"]):
            device = self._build_device(tinytuya, binding, credentials, version)
            try:
                payload = operation(device)
                if not isinstance(payload, dict):
                    raise RuntimeError("TinyTuya returned a non-dict status payload")
                if "dps" in payload:
                    return payload
                last_payload = payload
            except Exception as exc:
                last_error = exc
            finally:
                device.close()

        if last_payload is not None:
            return last_payload
        if last_error is not None:
            raise last_error
        raise RuntimeError("No protocol candidates were available for bulb transport")

    def _build_device(self, tinytuya, binding: BindingRecord, credentials: DeviceCredentials, version_text: str):
        """Construct a TinyTuya bulb instance for one binding."""
        version = float(version_text)
        device = tinytuya.BulbDevice(
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


def _execute_and_status(device, operation):
    """Run one device mutation and then fetch status."""
    operation()
    return device.status()


def _candidate_versions(explicit: str | None, fallbacks: list[str]) -> list[str]:
    """Return ordered protocol candidates with duplicates removed."""
    ordered = [explicit] if explicit else []
    ordered.extend(fallbacks)
    result: list[str] = []
    for item in ordered:
        if not item:
            continue
        if item not in result:
            result.append(item)
    return result
