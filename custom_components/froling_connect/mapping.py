"""Mapping of Fröling Connect parameters to Home Assistant entities.

The classification is data-driven and keyed on stable machine facts only
(parameter type, machine name, value ranges) — never on localized display
labels. Human-facing names and enum state labels come from this module's own
catalogs (mirrored into strings.json, enforced by a test).
"""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import Platform
from homeassistant.helpers.entity import EntityCategory

from .models import NUMERIC_PARAMETER_TYPE, Parameter

# stable unique ids: facility id + component id + parameter id
def build_parameter_unique_id(
    facility_id: int, component_id: str, parameter_id: str
) -> str:
    """Build the stable unique id of a component parameter entity."""
    return f"{facility_id}_{component_id}_{parameter_id}"


def build_facility_unique_id(facility_id: int, key: str) -> str:
    """Build the stable unique id of a facility-level entity."""
    return f"{facility_id}_{key}"


# ---------------------------------------------------------------- catalogs --
# English names per machine parameter name. Parameters not listed here keep
# their machine name (humanized) and never a localized label.
PARAMETER_NAMES: dict[str, str] = {
    "actualFlowTemp": "Actual flow temperature",
    "boilerOn": "Boiler",
    "boilerSetTemp": "Boiler set temperature",
    "boilerTemp": "Boiler temperature",
    "bufferPumpControl": "Buffer pump",
    "bufferSensorAmount": "Buffer sensor amount",
    "bufferTankCharge": "Buffer tank charge",
    "bufferTankChargeDiskret": "Buffer tank charge (discrete)",
    "bufferTempBottom": "Buffer bottom temperature",
    "bufferTempMiddleNewGeneration2": "Storage temperature sensor 2",
    "bufferTempMiddleNewGeneration3": "Storage temperature sensor 3",
    "bufferTempTop": "Buffer top temperature",
    "circuitPumpControl": "Circuit pump",
    "desiredRoomTemp": "Desired room temperature",
    "dhwPumpControl": "DHW pump",
    "dhwTempTop": "DHW top temperature",
    "fanControl": "Fan control",
    "flueGasTemp": "Flue gas temperature",
    "hoursSinceLastMaintenance": "Hours since last maintenance",
    "ignitionConfigured": "Ignition configured",
    "ignitionWhenBufferTempBelow": "Ignition when buffer temperature below",
    "mode": "Mode",
    "mode2": "Boiler mode",
    "notifications": "Notifications",
    "operationHours": "Operation hours",
    "outTemp": "Outside temperature",
    "remoteOn": "Remote control",
    "resOxygenContent": "Residual oxygen content",
    "returnFlowTemp": "Return flow temperature",
    "setDhwTemp": "DHW set temperature",
    "state": "Boiler state",
}

# Translated state labels per machine parameter name and raw value. Values not
# listed here fall back to the API's display text, then to the raw value.
STATE_LABELS: dict[str, dict[str, str]] = {
    "mode": {"0": "Off", "1": "Auto"},
    "mode2": {"0": "Full load", "1": "DHW heating", "2": "Automatic"},
    "state": {"19": "Standby"},
}

# Raw values that mean "on" for the two-valued enum parameters we expose as
# binary sensors (read from recorded fixtures; boilerOn: 0 = EIN).
BOOLEAN_ENUM_ON_VALUES: dict[str, str] = {
    "boilerOn": "0",
    "remoteOn": "1",
}

# Numeric parameters that act as on/off signals (pump control, 0 = off).
PUMP_NAME_FRAGMENT = "pump"

# Cumulative counters are total-increasing, everything else a measurement.
COUNTER_PARAMETERS = {"operationHours", "hoursSinceLastMaintenance"}

UNIT_DEVICE_CLASSES: dict[str, SensorDeviceClass] = {
    "°C": SensorDeviceClass.TEMPERATURE,
    "h": SensorDeviceClass.DURATION,
}

DEVICE_NAMES: dict[str, str] = {
    "BOILER": "Boiler",
    "CIRCUIT": "Heating circuit",
    "DHW": "DHW tank",
    "BUFFER_TANK": "Buffer tank",
    "PELLET_STORAGE": "Pellet storage",
    "SOLAR": "Solar",
}


def device_name(component_type: str, component_number: int) -> str:
    """Stable, unlocalized device name for a component."""
    base = DEVICE_NAMES.get(component_type, component_type.replace("_", " ").title())
    return f"{base} {component_number}"


def humanize_parameter_name(name: str) -> str:
    """Fallback entity name for catalog-unknown parameters: the machine name."""
    return name.replace("_", " ").strip()


# ------------------------------------------------------------ classification --
@dataclass(frozen=True)
class EntityMapping:
    """How one parameter maps to an entity."""

    platform: Platform
    translation_key: str | None  # None when the parameter is not catalogued
    device_class: SensorDeviceClass | None = None
    state_class: SensorStateClass | None = None
    diagnostic: bool = False
    # binary sensors: raw value that means "on" (enum) or numeric > 0 (pump)
    on_value: str | None = None


def classify_parameter(parameter: Parameter) -> EntityMapping:
    """Classify a parameter into its entity mapping using machine facts only."""
    name = parameter.name
    translation_key = name if name in PARAMETER_NAMES else None

    if parameter.parameter_type == NUMERIC_PARAMETER_TYPE:
        if PUMP_NAME_FRAGMENT in name.lower():
            return EntityMapping(
                platform=Platform.BINARY_SENSOR,
                translation_key=translation_key,
                on_value=None,
            )
        return EntityMapping(
            platform=Platform.SENSOR,
            translation_key=translation_key,
            device_class=UNIT_DEVICE_CLASSES.get(parameter.unit),
            state_class=(
                SensorStateClass.TOTAL_INCREASING
                if name in COUNTER_PARAMETERS
                else SensorStateClass.MEASUREMENT
            ),
        )

    # string-valued parameter
    on_value = BOOLEAN_ENUM_ON_VALUES.get(name)
    if on_value is not None and len(parameter.string_list) == 2:
        return EntityMapping(
            platform=Platform.BINARY_SENSOR,
            translation_key=translation_key,
            on_value=on_value,
        )
    return EntityMapping(
        platform=Platform.SENSOR,
        translation_key=translation_key,
        diagnostic=True,
    )


def enum_state_label(
    mapping: EntityMapping, parameter: Parameter, display_value: str | None
) -> str | None:
    """Human label for a (possibly enum) parameter's current raw value.

    Resolution order: our catalog, the API's display text, the raw value.
    """
    raw = parameter.raw_value
    label = STATE_LABELS.get(parameter.name, {}).get(raw)
    if label is not None:
        return label
    if display_value:
        return display_value
    return raw


def binary_is_on(mapping: EntityMapping, parameter: Parameter) -> bool | None:
    """Compute the binary sensor state, or None when the value is unknown."""
    raw = parameter.raw_value
    if raw is None or raw == "":
        return None
    if mapping.on_value is not None:
        return raw == mapping.on_value
    try:
        return float(raw) > 0
    except ValueError:
        return None
