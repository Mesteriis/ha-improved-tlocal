"""Built-in template registry for ImprovedTLocal."""

from __future__ import annotations

from typing import Any

from .const import (
    TEMPLATE_SMART_LIGHT_RGBCW,
    TEMPLATE_SMART_PLUG_BASIC,
    TEMPLATE_SMART_PLUG_POWER,
)
from .models import DeviceTemplate, InventoryDevice

_TEMPLATES: dict[str, DeviceTemplate] = {
    TEMPLATE_SMART_PLUG_POWER: DeviceTemplate(
        template_id=TEMPLATE_SMART_PLUG_POWER,
        family="smart_plug",
        description="Single-channel Tuya smart plug with power metrics",
        required_dp_codes=["switch_1", "cur_power"],
        optional_dp_codes=["cur_current", "cur_voltage", "add_ele", "countdown_1"],
        platforms=["switch", "sensor"],
    ),
    TEMPLATE_SMART_PLUG_BASIC: DeviceTemplate(
        template_id=TEMPLATE_SMART_PLUG_BASIC,
        family="smart_plug",
        description="Single-channel Tuya smart plug without mandatory power metrics",
        required_dp_codes=["switch_1"],
        optional_dp_codes=["countdown_1"],
        platforms=["switch"],
    ),
    TEMPLATE_SMART_LIGHT_RGBCW: DeviceTemplate(
        template_id=TEMPLATE_SMART_LIGHT_RGBCW,
        family="smart_light",
        description="Tuya RGB+CCT light with white, colour temperature, and RGB control",
        required_dp_codes=["switch_led", "work_mode", "bright_value_v2", "temp_value_v2", "colour_data_v2"],
        optional_dp_codes=["scene_data_v2", "countdown_1"],
        platforms=["light"],
    ),
}


def get_template(template_id: str) -> DeviceTemplate | None:
    """Return one built-in template by id."""
    return _TEMPLATES.get(template_id)


def list_templates() -> list[DeviceTemplate]:
    """Return all built-in templates."""
    return list(_TEMPLATES.values())


def select_template_for_device(device: InventoryDevice, preferred_template_id: str | None = None) -> DeviceTemplate | None:
    """Pick the best supported template for one inventory device."""
    if preferred_template_id:
        template = get_template(preferred_template_id)
        if template and template_matches_device(template, device):
            return template
        return None

    for template_id in device.template_candidates:
        template = get_template(template_id)
        if template and template_matches_device(template, device):
            return template
    return None


def template_matches_device(template: DeviceTemplate, device: InventoryDevice) -> bool:
    """Check whether the device provides the required DP codes for a template."""
    codes = _device_dp_codes(device)
    return all(code in codes for code in template.required_dp_codes)


def _device_dp_codes(device: InventoryDevice) -> set[str]:
    """Extract normalized DP codes from one inventory device."""
    schema = device.dp_schema
    if not isinstance(schema, dict):
        return set()
    codes: set[str] = set()
    for value in schema.values():
        if isinstance(value, dict):
            code = value.get("code")
            if code:
                codes.add(str(code))
    return codes


def summarize_template(template: DeviceTemplate | None) -> dict[str, Any] | None:
    """Serialize template metadata when present."""
    return template.to_dict() if template else None
