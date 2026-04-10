"""Typed models for ImprovedTLocal."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from .const import (
    VERIFICATION_DEGRADED,
    VERIFICATION_STRONG,
    VERIFICATION_UNVERIFIED,
    VERIFICATION_WEAK,
)

VerificationLevel = Literal[
    "unverified",
    "weakly_verified",
    "strongly_verified",
    "degraded",
]
MatchStatus = Literal["matched", "tentative", "conflict", "unmatched"]


def utcnow_iso() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def normalize_mac(value: str | None) -> str | None:
    """Normalize a MAC address to lowercase colon-separated form."""
    if not value:
        return None
    compact = "".join(ch for ch in value.lower() if ch.isalnum())
    if len(compact) != 12:
        return value.lower()
    return ":".join(compact[i : i + 2] for i in range(0, 12, 2))


def _compact_dict(value: dict[str, Any]) -> dict[str, Any]:
    """Drop None values recursively from a dictionary."""
    compact: dict[str, Any] = {}
    for key, item in value.items():
        if item is None:
            continue
        if isinstance(item, dict):
            compact[key] = _compact_dict(item)
            continue
        if isinstance(item, list):
            compact[key] = [_compact_dict(v) if isinstance(v, dict) else v for v in item]
            continue
        compact[key] = item
    return compact


@dataclass(slots=True)
class InventoryDevice:
    """Canonical physical-device facts."""

    device_id: str
    name: str
    category: str | None = None
    product_id: str | None = None
    model: str | None = None
    model_id: str | None = None
    uuid: str | None = None
    mac: str | None = None
    parent_device_id: str | None = None
    node_id: str | None = None
    is_subdevice: bool = False
    transport_scope: str = "direct"
    power_profile: str | None = None
    local_key_ref: str | None = None
    cloud_online: bool | None = None
    dp_schema: dict[str, Any] | None = None
    template_candidates: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the device to a compact dictionary."""
        payload = asdict(self)
        payload["mac"] = normalize_mac(self.mac)
        return _compact_dict(payload)


@dataclass(slots=True)
class NetworkEndpoint:
    """Mutable network endpoint facts."""

    ip: str
    port: int
    protocol_version: str | None = None
    protocol_version_candidates: list[str] = field(default_factory=list)
    observed_device_id: str | None = None
    mac: str | None = None
    scan_source: str = "unknown"
    last_seen_at: str | None = None
    fingerprint: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the endpoint to a compact dictionary."""
        payload = asdict(self)
        payload["mac"] = normalize_mac(self.mac)
        return _compact_dict(payload)


@dataclass(slots=True)
class BindingRecord:
    """Persisted binding between a physical device and network endpoint."""

    device_id: str
    bound_ip: str
    bound_port: int = 6668
    bound_protocol_version: str | None = None
    verification_level: VerificationLevel = VERIFICATION_UNVERIFIED
    template_id: str | None = None
    confidence: float = 0.0
    verified_at: str | None = None
    verification_method: str | None = None
    failure_streak: int = 0
    mac: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the binding to a compact dictionary."""
        payload = asdict(self)
        payload["mac"] = normalize_mac(self.mac)
        return _compact_dict(payload)


@dataclass(slots=True)
class MatchReason:
    """One explainable reason behind a match outcome."""

    code: str
    summary: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the reason to a dictionary."""
        return _compact_dict(asdict(self))


@dataclass(slots=True)
class MatchResult:
    """Outcome of matching one device to one candidate endpoint."""

    device_id: str
    candidate_ip: str | None = None
    candidate_port: int | None = None
    score: float = 0.0
    status: MatchStatus = "unmatched"
    reasons: list[MatchReason] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    recommended_action: str = "ignore"
    verification_level: VerificationLevel = VERIFICATION_UNVERIFIED

    def to_dict(self) -> dict[str, Any]:
        """Serialize the match result to a dictionary."""
        payload = asdict(self)
        payload["reasons"] = [reason.to_dict() for reason in self.reasons]
        return _compact_dict(payload)


@dataclass(slots=True)
class DiscoveryReport:
    """Structured output from one dry-run discovery pass."""

    generated_at: str
    inventory_devices: list[InventoryDevice]
    network_endpoints: list[NetworkEndpoint]
    match_results: list[MatchResult]
    unmatched_device_ids: list[str]
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the report to a dictionary."""
        return {
            "generated_at": self.generated_at,
            "inventory_devices": [device.to_dict() for device in self.inventory_devices],
            "network_endpoints": [endpoint.to_dict() for endpoint in self.network_endpoints],
            "match_results": [match.to_dict() for match in self.match_results],
            "unmatched_device_ids": list(self.unmatched_device_ids),
            "meta": _compact_dict(dict(self.meta)),
        }


@dataclass(slots=True)
class DeviceTemplate:
    """Template metadata for one supported device family."""

    template_id: str
    family: str
    description: str
    required_dp_codes: list[str] = field(default_factory=list)
    optional_dp_codes: list[str] = field(default_factory=list)
    platforms: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the template descriptor to a compact dictionary."""
        return _compact_dict(asdict(self))


def verification_from_score(score: float, *, strong_signal: bool = False) -> VerificationLevel:
    """Map a score and signal strength to a verification level."""
    if strong_signal and score >= 0.9:
        return VERIFICATION_STRONG
    if score >= 0.6:
        return VERIFICATION_WEAK
    if score > 0:
        return VERIFICATION_DEGRADED
    return VERIFICATION_UNVERIFIED
