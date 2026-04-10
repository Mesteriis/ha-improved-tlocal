"""Manager and dry-run discovery flow for ImprovedTLocal."""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from homeassistant.core import HomeAssistant

from .const import (
    DATA_DEVICE_PROVIDERS,
    DATA_ENDPOINT_PROVIDERS,
    DEFAULT_SCAN_PORTS,
    DEFAULT_SCAN_TIMEOUT,
    DOMAIN,
)
from .inventory.lan_scan import async_scan_open_ports
from .models import (
    BindingRecord,
    DiscoveryReport,
    InventoryDevice,
    MatchReason,
    MatchResult,
    NetworkEndpoint,
    utcnow_iso,
    verification_from_score,
)
from .storage import ImprovedTLocalStore


class DeviceInventoryProvider(Protocol):
    """Provider protocol for physical-device inventory."""

    async def async_fetch_devices(self, hass: HomeAssistant) -> list[InventoryDevice]:
        """Return known devices."""


class EndpointInventoryProvider(Protocol):
    """Provider protocol for network endpoint inventory."""

    async def async_fetch_endpoints(self, hass: HomeAssistant) -> list[NetworkEndpoint]:
        """Return observed endpoints."""


@dataclass(slots=True)
class DryRunOptions:
    """Normalized dry-run discovery options."""

    networks: list[str]
    ports: list[int]
    timeout: float
    include_lan_scan: bool


class ImprovedTLocalManager:
    """Main manager for dry-run discovery and persistence."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the manager."""
        self.hass = hass
        self.storage = ImprovedTLocalStore(hass)

    def normalize_options(self, raw: dict[str, Any]) -> DryRunOptions:
        """Normalize raw service-call options."""
        networks_raw = raw.get("networks")
        ports_raw = raw.get("ports")
        networks = _normalize_str_list(networks_raw)
        ports = [int(port) for port in _normalize_int_list(ports_raw)] or list(DEFAULT_SCAN_PORTS)
        timeout = float(raw.get("timeout") or DEFAULT_SCAN_TIMEOUT)
        include_lan_scan = bool(raw.get("include_lan_scan", bool(networks)))
        return DryRunOptions(
            networks=networks,
            ports=ports,
            timeout=timeout,
            include_lan_scan=include_lan_scan,
        )

    async def async_discover_dry_run(self, raw_options: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run one dry-run discovery pass and persist the report."""
        options = self.normalize_options(raw_options or {})
        devices = await self._async_collect_devices()
        endpoints = await self._async_collect_endpoints()
        if options.include_lan_scan and options.networks:
            endpoints.extend(
                await async_scan_open_ports(
                    options.networks,
                    options.ports,
                    timeout=options.timeout,
                )
            )
        endpoints = _dedupe_endpoints(endpoints)
        bindings = await self.storage.async_load_bindings()
        match_results = _build_match_results(devices, endpoints, bindings)
        unmatched_device_ids = [result.device_id for result in match_results if result.status == "unmatched"]
        report = DiscoveryReport(
            generated_at=utcnow_iso(),
            inventory_devices=devices,
            network_endpoints=endpoints,
            match_results=match_results,
            unmatched_device_ids=unmatched_device_ids,
            meta={
                "device_provider_count": len(self._device_providers),
                "endpoint_provider_count": len(self._endpoint_providers),
                "inventory_device_count": len(devices),
                "network_endpoint_count": len(endpoints),
                "templated_device_count": sum(bool(device.template_candidates) for device in devices),
                "supported_power_plug_count": sum(
                    "smart_plug.power_monitor.v1" in device.template_candidates for device in devices
                ),
                "lan_scan_enabled": options.include_lan_scan,
                "lan_scan_networks": options.networks,
                "lan_scan_ports": options.ports,
            },
        )
        await self.storage.async_save_discovery_report(report)
        return report.to_dict()

    @property
    def _device_providers(self) -> list[DeviceInventoryProvider]:
        """Return registered device providers."""
        return list(self.hass.data.setdefault(DOMAIN, {}).get(DATA_DEVICE_PROVIDERS, []))

    @property
    def _endpoint_providers(self) -> list[EndpointInventoryProvider]:
        """Return registered endpoint providers."""
        return list(self.hass.data.setdefault(DOMAIN, {}).get(DATA_ENDPOINT_PROVIDERS, []))

    async def _async_collect_devices(self) -> list[InventoryDevice]:
        """Collect devices from all registered providers."""
        devices: list[InventoryDevice] = []
        for provider in self._device_providers:
            devices.extend(await provider.async_fetch_devices(self.hass))
        return _dedupe_devices(devices)

    async def _async_collect_endpoints(self) -> list[NetworkEndpoint]:
        """Collect endpoints from all registered providers."""
        endpoints: list[NetworkEndpoint] = []
        for provider in self._endpoint_providers:
            endpoints.extend(await provider.async_fetch_endpoints(self.hass))
        return endpoints


def _normalize_str_list(value: Any) -> list[str]:
    """Normalize one-or-many string input into a list."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Iterable):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]


def _normalize_int_list(value: Any) -> list[int]:
    """Normalize one-or-many integer input into a list."""
    if value is None:
        return []
    if isinstance(value, int):
        return [value]
    if isinstance(value, Iterable) and not isinstance(value, (str, bytes)):
        return [int(item) for item in value]
    return [int(value)]


def _dedupe_devices(devices: Sequence[InventoryDevice]) -> list[InventoryDevice]:
    """Keep the last version of every physical device id."""
    deduped: dict[str, InventoryDevice] = {}
    for device in devices:
        deduped[device.device_id] = device
    ordered = list(deduped.values())
    ordered.sort(key=lambda device: device.device_id)
    return ordered


def _dedupe_endpoints(endpoints: Sequence[NetworkEndpoint]) -> list[NetworkEndpoint]:
    """Deduplicate endpoints by ip and port."""
    deduped: dict[tuple[str, int], NetworkEndpoint] = {}
    for endpoint in endpoints:
        deduped[(endpoint.ip, endpoint.port)] = endpoint
    ordered = list(deduped.values())
    ordered.sort(key=lambda endpoint: (endpoint.ip, endpoint.port))
    return ordered


def _build_match_results(
    devices: Sequence[InventoryDevice],
    endpoints: Sequence[NetworkEndpoint],
    bindings: dict[str, BindingRecord],
) -> list[MatchResult]:
    """Create explainable match results for one dry-run pass."""
    endpoints_by_device_id: dict[str, list[NetworkEndpoint]] = {}
    endpoints_by_mac: dict[str, list[NetworkEndpoint]] = {}
    endpoints_by_ip_port: dict[tuple[str, int], NetworkEndpoint] = {}

    for endpoint in endpoints:
        endpoints_by_ip_port[(endpoint.ip, endpoint.port)] = endpoint
        if endpoint.observed_device_id:
            endpoints_by_device_id.setdefault(endpoint.observed_device_id, []).append(endpoint)
        if endpoint.mac:
            endpoints_by_mac.setdefault(endpoint.mac.lower(), []).append(endpoint)

    results: list[MatchResult] = []
    for device in devices:
        candidates: list[tuple[float, bool, NetworkEndpoint, list[MatchReason]]] = []
        binding = bindings.get(device.device_id)
        if binding:
            endpoint = endpoints_by_ip_port.get((binding.bound_ip, binding.bound_port))
            if endpoint:
                candidates.append(
                    (
                        0.7,
                        False,
                        endpoint,
                        [
                            MatchReason(
                                code="binding_hit",
                                summary="Matched stored binding to a live endpoint",
                                details={"ip": endpoint.ip, "port": endpoint.port},
                            )
                        ],
                    )
                )

        for endpoint in endpoints_by_device_id.get(device.device_id, []):
            candidates.append(
                (
                    1.0,
                    True,
                    endpoint,
                    [
                        MatchReason(
                            code="device_id_probe",
                            summary="Endpoint observed the exact device id",
                            details={"ip": endpoint.ip, "port": endpoint.port},
                        )
                    ],
                )
            )

        if device.mac:
            for endpoint in endpoints_by_mac.get(device.mac.lower(), []):
                candidates.append(
                    (
                        0.8,
                        False,
                        endpoint,
                        [
                            MatchReason(
                                code="mac_match",
                                summary="Endpoint MAC matches the device MAC",
                                details={"ip": endpoint.ip, "port": endpoint.port, "mac": endpoint.mac},
                            )
                        ],
                    )
                )

        if not candidates:
            results.append(
                MatchResult(
                    device_id=device.device_id,
                    score=0.0,
                    status="unmatched",
                    reasons=[
                        MatchReason(
                            code="no_candidate",
                            summary="No candidate endpoint matched this device",
                        )
                    ],
                    recommended_action="retry_discovery",
                )
            )
            continue

        candidates.sort(key=lambda item: item[0], reverse=True)
        best_score = candidates[0][0]
        best_candidates = [item for item in candidates if item[0] == best_score]
        if len(best_candidates) > 1:
            conflict_ips = sorted({candidate.ip for _, _, candidate, _ in best_candidates})
            results.append(
                MatchResult(
                    device_id=device.device_id,
                    score=best_score,
                    status="conflict",
                    reasons=[
                        MatchReason(
                            code="multiple_candidates",
                            summary="More than one endpoint shares the top score",
                            details={"candidate_ips": conflict_ips},
                        )
                    ],
                    conflicts=conflict_ips,
                    recommended_action="manual_review",
                    verification_level=verification_from_score(best_score),
                )
            )
            continue

        score, strong_signal, endpoint, reasons = best_candidates[0]
        status = "matched" if strong_signal else "tentative"
        recommended_action = "apply" if strong_signal else "review"
        results.append(
            MatchResult(
                device_id=device.device_id,
                candidate_ip=endpoint.ip,
                candidate_port=endpoint.port,
                score=score,
                status=status,
                reasons=reasons,
                recommended_action=recommended_action,
                verification_level=verification_from_score(score, strong_signal=strong_signal),
            )
        )

    results.sort(key=lambda item: item.device_id)
    return results
