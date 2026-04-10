"""Tests for file-backed credentials."""

from __future__ import annotations

import asyncio
import json

from custom_components.improved_tlocal.credentials import FileSnapshotCredentialsStore


def test_file_snapshot_credentials_store_returns_local_key_and_version(tmp_path, hass) -> None:
    """Credentials store should resolve local key and protocol version from snapshots."""
    snapshot = tmp_path / "devices.json"
    snapshot.write_text(
        json.dumps(
            [
                {
                    "id": "plug-1",
                    "key": "secret-local-key",
                    "version": "3.4",
                }
            ]
        ),
        encoding="utf-8",
    )
    store = FileSnapshotCredentialsStore(paths=[snapshot])

    credentials = asyncio.run(store.async_get_credentials(hass, "plug-1"))

    assert credentials is not None
    assert credentials.device_id == "plug-1"
    assert credentials.local_key == "secret-local-key"
    assert credentials.protocol_version == "3.4"
