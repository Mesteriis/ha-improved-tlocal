"""Constants for ImprovedTLocal."""

from __future__ import annotations

DOMAIN = "improved_tlocal"
NAME = "ImprovedTLocal"
VERSION = "0.1.0"

DATA_MANAGER = "manager"
DATA_SERVICES_REGISTERED = "services_registered"
DATA_DEVICE_PROVIDERS = "device_providers"
DATA_ENDPOINT_PROVIDERS = "endpoint_providers"

STORE_VERSION = 1
STORE_KEY = "improved_tlocal.storage"

SERVICE_DISCOVER_DRY_RUN = "discover_dry_run"

DEFAULT_SCAN_PORTS: tuple[int, ...] = (6668, 6669)
DEFAULT_SCAN_TIMEOUT = 0.35
DEFAULT_SCAN_MAX_CONCURRENCY = 256

VERIFICATION_UNVERIFIED = "unverified"
VERIFICATION_WEAK = "weakly_verified"
VERIFICATION_STRONG = "strongly_verified"
VERIFICATION_DEGRADED = "degraded"
