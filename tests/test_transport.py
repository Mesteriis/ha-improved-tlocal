"""Tests for TinyTuya transport helpers."""

from __future__ import annotations

import asyncio

from custom_components.improved_tlocal.credentials import DeviceCredentials
from custom_components.improved_tlocal.models import BindingRecord
from custom_components.improved_tlocal.transport import TinyTuyaBulbTransport


class FakeBulbDevice:
    """TinyTuya-like bulb object that only succeeds on protocol 3.5."""

    attempts: list[float] = []

    def __init__(self, dev_id, address=None, local_key="", version=3.3, port=6668, persist=False, connection_timeout=5):
        self.version = version
        self.closed = False

    def set_version(self, version):
        self.version = version

    def set_retry(self, retry):
        return None

    def status(self):
        self.attempts.append(self.version)
        if self.version == 3.5:
            return {"dps": {"20": True}}
        if self.version == 3.4:
            return {"Error": "Check device key or version", "Err": "914", "Payload": None}
        return {"Error": "Unexpected Payload from Device", "Err": "904", "Payload": None}

    def close(self):
        self.closed = True


class FakeTinytuyaModule:
    """Minimal module exposing only BulbDevice."""

    BulbDevice = FakeBulbDevice


def test_bulb_transport_falls_back_to_protocol_35(monkeypatch) -> None:
    """Bulb transport should retry protocol candidates until it gets DPS data."""
    monkeypatch.setattr("custom_components.improved_tlocal.transport._import_tinytuya", lambda: FakeTinytuyaModule)
    FakeBulbDevice.attempts = []

    transport = TinyTuyaBulbTransport()
    payload = asyncio.run(
        transport.async_status(
            BindingRecord(device_id="light-1", bound_ip="192.168.1.90"),
            DeviceCredentials(device_id="light-1", local_key="secret", protocol_version=None),
        )
    )

    assert payload == {"dps": {"20": True}}
    assert FakeBulbDevice.attempts == [3.5]
