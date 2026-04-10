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
from .runtime import PlugRuntimeRegistry
from .storage import ImprovedTLocalStore
from .templates import select_template_for_device, summarize_template


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


@dataclass(slots=True)
class BindOptions:
    """Normalized bind service options."""

    device_id: str
    candidate_ip: str | None
    candidate_port: int | None
    bound_protocol_version: str | None
    template_id: str | None
    allow_tentative: bool


class ImprovedTLocalManager:
    """Main manager for dry-run discovery and persistence."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the manager."""
        self.hass = hass
        self.storage = ImprovedTLocalStore(hass)
        self.runtime_registry = PlugRuntimeRegistry(hass, self)

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

    def normalize_bind_options(self, raw: dict[str, Any]) -> BindOptions:
        """Normalize raw binding options."""
        device_id = str(raw.get("device_id") or "").strip()
        return BindOptions(
            device_id=device_id,
            candidate_ip=_normalize_optional_str(raw.get("ip")),
            candidate_port=int(raw["port"]) if raw.get("port") is not None else None,
            bound_protocol_version=_normalize_optional_str(raw.get("protocol_version")),
            template_id=_normalize_optional_str(raw.get("template_id")),
            allow_tentative=bool(raw.get("allow_tentative", False)),
        )

    async def async_bind_device(self, raw_options: dict[str, Any]) -> dict[str, Any]:
        """Apply one binding from an existing dry-run report or explicit endpoint."""
        options = self.normalize_bind_options(raw_options)
        if not options.device_id:
            return {
                "ok": False,
                "error_code": "missing_device_id",
                "message": "device_id is required",
            }

        report = await self.storage.async_load_discovery_report()
        bindings = await self.storage.async_load_bindings()
        current_binding = bindings.get(options.device_id)

        device = await self._async_get_inventory_device(options.device_id, report)
        match_result = _find_report_match(report, options.device_id) if report else None

        if options.candidate_ip is None:
            resolution = _resolve_match_for_apply(match_result, allow_tentative=options.allow_tentative)
            if resolution["error_code"] is not None:
                return {
                    "ok": False,
                    "device_id": options.device_id,
                    "error_code": resolution["error_code"],
                    "message": resolution["message"],
                    "match_result": match_result,
                }
            candidate_ip = resolution["candidate_ip"]
            candidate_port = resolution["candidate_port"]
            verification_level = str(match_result.get("verification_level") or "unverified") if match_result else "unverified"
            confidence = float(match_result.get("score") or 0.0) if match_result else 0.0
            verification_method = "dry_run_report"
        else:
            candidate_ip = options.candidate_ip
            candidate_port = options.candidate_port or 6668
            verification_level = "unverified"
            confidence = 0.0
            verification_method = "manual_bind"

        if not candidate_ip:
            return {
                "ok": False,
                "device_id": options.device_id,
                "error_code": "missing_candidate_ip",
                "message": "No candidate IP was available for binding",
            }

        template = None
        if device is not None:
            template = select_template_for_device(device, preferred_template_id=options.template_id)
        elif options.template_id:
            template = None

        if template is None and current_binding and current_binding.template_id and options.template_id is None:
            selected_template_id = current_binding.template_id
        elif template is None and options.template_id:
            return {
                "ok": False,
                "device_id": options.device_id,
                "error_code": "unsupported_template",
                "message": f"Template {options.template_id} is not compatible with the selected device",
            }
        elif template is None:
            return {
                "ok": False,
                "device_id": options.device_id,
                "error_code": "no_supported_template",
                "message": "No supported template is available for this device",
            }
        else:
            selected_template_id = template.template_id

        next_binding = BindingRecord(
            device_id=options.device_id,
            bound_ip=candidate_ip,
            bound_port=candidate_port or 6668,
            bound_protocol_version=options.bound_protocol_version or _extract_endpoint_protocol_version(report, candidate_ip, candidate_port),
            verification_level=verification_level,
            template_id=selected_template_id,
            confidence=confidence,
            verified_at=utcnow_iso(),
            verification_method=verification_method,
            failure_streak=0,
            mac=device.mac if device else (current_binding.mac if current_binding else None),
        )

        action = _describe_binding_action(current_binding, next_binding)
        bindings[options.device_id] = next_binding
        await self.storage.async_save_bindings(bindings)
        await self.storage.async_append_binding_history(
            options.device_id,
            {
                "changed_at": utcnow_iso(),
                "action": action,
                "source": verification_method,
                "previous_binding": current_binding.to_dict() if current_binding else None,
                "next_binding": next_binding.to_dict(),
            },
        )
        await self.runtime_registry.async_sync_entities()
        return {
            "ok": True,
            "device_id": options.device_id,
            "action": action,
            "binding": next_binding.to_dict(),
            "previous_binding": current_binding.to_dict() if current_binding else None,
            "template": summarize_template(template),
        }

    async def async_register_runtime_platform(self, platform: str, async_add_entities) -> None:
        """Register one runtime platform callback."""
        await self.runtime_registry.async_register_platform(platform, async_add_entities)

    async def async_sync_runtime_entities(self) -> dict[str, Any]:
        """Synchronize runtime entities for all supported bound devices."""
        await self.runtime_registry.async_sync_entities()
        return {
            "ok": True,
            **self.runtime_registry.summary(),
        }

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

    async def _async_get_inventory_device(
        self,
        device_id: str,
        report: dict[str, Any] | None = None,
    ) -> InventoryDevice | None:
        """Resolve one inventory device from the report or live providers."""
        if report:
            device = _inventory_device_from_report(report, device_id)
            if device is not None:
                return device

        devices = await self._async_collect_devices()
        for device in devices:
            if device.device_id == device_id:
                return device
        return None


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


def _normalize_optional_str(value: Any) -> str | None:
    """Normalize an optional string-ish value."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


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


def _find_report_match(report: dict[str, Any] | None, device_id: str) -> dict[str, Any] | None:
    """Return one serialized match result from the report."""
    if not isinstance(report, dict):
        return None
    for result in report.get("match_results", []):
        if isinstance(result, dict) and result.get("device_id") == device_id:
            return result
    return None


def _inventory_device_from_report(report: dict[str, Any], device_id: str) -> InventoryDevice | None:
    """Reconstruct one inventory device from a serialized report entry."""
    for raw in report.get("inventory_devices", []):
        if not isinstance(raw, dict) or raw.get("device_id") != device_id:
            continue
        return InventoryDevice(
            device_id=str(raw.get("device_id")),
            name=str(raw.get("name") or device_id),
            category=_normalize_optional_str(raw.get("category")),
            product_id=_normalize_optional_str(raw.get("product_id")),
            model=_normalize_optional_str(raw.get("model")),
            model_id=_normalize_optional_str(raw.get("model_id")),
            uuid=_normalize_optional_str(raw.get("uuid")),
            mac=_normalize_optional_str(raw.get("mac")),
            parent_device_id=_normalize_optional_str(raw.get("parent_device_id")),
            node_id=_normalize_optional_str(raw.get("node_id")),
            is_subdevice=bool(raw.get("is_subdevice", False)),
            transport_scope=_normalize_optional_str(raw.get("transport_scope")) or "direct",
            power_profile=_normalize_optional_str(raw.get("power_profile")),
            local_key_ref=_normalize_optional_str(raw.get("local_key_ref")),
            cloud_online=raw.get("cloud_online"),
            dp_schema=raw.get("dp_schema") if isinstance(raw.get("dp_schema"), dict) else None,
            template_candidates=[str(item) for item in raw.get("template_candidates", []) if str(item).strip()],
        )
    return None


def _resolve_match_for_apply(match_result: dict[str, Any] | None, *, allow_tentative: bool) -> dict[str, Any]:
    """Resolve whether a report match can be safely applied."""
    if not isinstance(match_result, dict):
        return {
            "candidate_ip": None,
            "candidate_port": None,
            "error_code": "missing_match_result",
            "message": "Run discover_dry_run first or provide an explicit IP",
        }

    status = str(match_result.get("status") or "")
    if status == "matched":
        return {
            "candidate_ip": match_result.get("candidate_ip"),
            "candidate_port": match_result.get("candidate_port"),
            "error_code": None,
            "message": "Match is safe to apply",
        }
    if status == "tentative":
        if allow_tentative:
            return {
                "candidate_ip": match_result.get("candidate_ip"),
                "candidate_port": match_result.get("candidate_port"),
                "error_code": None,
                "message": "Tentative match accepted by caller",
            }
        return {
            "candidate_ip": None,
            "candidate_port": None,
            "error_code": "tentative_requires_confirmation",
            "message": "Tentative match requires allow_tentative=true",
        }
    if status == "conflict":
        return {
            "candidate_ip": None,
            "candidate_port": None,
            "error_code": "conflict",
            "message": "The last dry-run report has conflicting candidates for this device",
        }
    if status == "unmatched":
        return {
            "candidate_ip": None,
            "candidate_port": None,
            "error_code": "unmatched",
            "message": "The last dry-run report could not match this device",
        }
    return {
        "candidate_ip": None,
        "candidate_port": None,
        "error_code": "unknown_match_state",
        "message": "The last dry-run report contains an unsupported match state",
    }


def _extract_endpoint_protocol_version(
    report: dict[str, Any] | None,
    ip: str | None,
    port: int | None,
) -> str | None:
    """Return protocol version from a serialized endpoint when available."""
    if not isinstance(report, dict) or not ip or port is None:
        return None
    for endpoint in report.get("network_endpoints", []):
        if not isinstance(endpoint, dict):
            continue
        if endpoint.get("ip") == ip and int(endpoint.get("port") or 0) == port:
            version = endpoint.get("protocol_version")
            return str(version) if version else None
    return None


def _describe_binding_action(current: BindingRecord | None, new: BindingRecord) -> str:
    """Describe whether this mutation created, updated, or rebound a binding."""
    if current is None:
        return "created"
    if current.bound_ip != new.bound_ip or current.bound_port != new.bound_port:
        return "rebound"
    if current.template_id != new.template_id or current.bound_protocol_version != new.bound_protocol_version:
        return "updated"
    return "refreshed"
