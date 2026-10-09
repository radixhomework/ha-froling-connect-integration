"""Tests for the parameter-to-entity mapping layer (task 5.1) and the
translation catalog coverage (task 5.4)."""

import json
from pathlib import Path

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import Platform

from custom_components.froling_connect.mapping import (
    BOOLEAN_ENUM_ON_VALUES,
    PARAMETER_NAMES,
    PUMP_NAME_FRAGMENT,
    STATE_LABELS,
    binary_is_on,
    build_facility_unique_id,
    build_parameter_unique_id,
    classify_parameter,
    device_name,
    enum_state_label,
    humanize_parameter_name,
)
from custom_components.froling_connect.models import (
    NUMERIC_PARAMETER_TYPE,
    STRING_PARAMETER_TYPE,
    Component,
    Parameter,
)

COMPONENT_DIR = Path(__file__).parents[1] / "custom_components" / "froling_connect"


def numeric_param(name: str, unit: str = "") -> Parameter:
    return Parameter(name=name, raw_value="1", parameter_type=NUMERIC_PARAMETER_TYPE, unit=unit)


def string_param(name: str, string_list: dict[str, str] | None = None) -> Parameter:
    return Parameter(
        name=name,
        raw_value="0",
        parameter_type=STRING_PARAMETER_TYPE,
        string_list=string_list or {},
    )


#
# classification: machine facts only
#
def test_numeric_temperature_is_measurement_sensor():
    mapping = classify_parameter(numeric_param("boilerTemp", unit="°C"))
    assert mapping.platform == Platform.SENSOR
    assert mapping.device_class == SensorDeviceClass.TEMPERATURE
    assert mapping.state_class == SensorStateClass.MEASUREMENT
    assert mapping.diagnostic is False


def test_operation_hours_is_total_increasing():
    mapping = classify_parameter(numeric_param("operationHours", unit="h"))
    assert mapping.platform == Platform.SENSOR
    assert mapping.state_class == SensorStateClass.TOTAL_INCREASING


def test_enum_state_is_diagnostic_sensor():
    mapping = classify_parameter(string_param("state", {"19": "Standby", "5": "Fault"}))
    assert mapping.platform == Platform.SENSOR
    assert mapping.diagnostic is True


def test_two_valued_known_enum_is_binary_sensor():
    boiler_on = string_param("boilerOn", {"0": "Kessel EIN", "1": "Kessel AUS"})
    mapping = classify_parameter(boiler_on)
    assert mapping.platform == Platform.BINARY_SENSOR
    assert mapping.on_value == "0"  # recorded fixture: 0 = EIN = on


def test_pump_parameters_are_binary_sensors():
    for name in ("circuitPumpControl", "dhwPumpControl", "bufferPumpControl"):
        mapping = classify_parameter(numeric_param(name))
        assert mapping.platform == Platform.BINARY_SENSOR, name
        assert mapping.on_value is None  # numeric: on when > 0


def test_unknown_parameter_has_no_translation_key():
    mapping = classify_parameter(numeric_param("brandNewSensor", unit="°C"))
    assert mapping.platform == Platform.SENSOR
    assert mapping.translation_key is None
    assert humanize_parameter_name("brandNewSensor") == "brandNewSensor"


#
# stable identity, never label-derived
#
def test_unique_ids_are_stable_and_label_independent():
    labeled = Parameter(
        name="boilerTemp",
        raw_value="1",
        parameter_type=NUMERIC_PARAMETER_TYPE,
        unit="°C",
        id="3_0",
        display_name="Kesseltemperatur",
    )
    renamed = Parameter(
        name="boilerTemp",
        raw_value="1",
        parameter_type=NUMERIC_PARAMETER_TYPE,
        unit="°C",
        id="3_0",
        display_name="Boiler temperature",
    )
    assert (
        build_parameter_unique_id(12345, "1_100", labeled.id)
        == build_parameter_unique_id(12345, "1_100", renamed.id)
        == "12345_1_100_3_0"
    )
    assert build_facility_unique_id(12345, "outTemp") == "12345_outTemp"


def test_classification_of_every_component_fixture_parameter(load_fixture):
    component = Component.from_dict(load_fixture("component.json"), detailed=True)
    assert component is not None
    platforms = {
        name: classify_parameter(parameter).platform
        for name, parameter in component.parameters.items()
    }
    assert platforms["boilerTemp"] == Platform.SENSOR
    assert platforms["boilerSetTemp"] == Platform.SENSOR
    assert platforms["state"] == Platform.SENSOR  # diagnostic sensor
    assert platforms["mode2"] == Platform.SENSOR  # 3-valued: not binary
    assert platforms["boilerOn"] == Platform.BINARY_SENSOR
    assert platforms["remoteOn"] == Platform.BINARY_SENSOR


#
# state labels and binary state computation
#
def test_enum_label_resolves_from_catalog_then_display_then_raw():
    mapping = classify_parameter(string_param("state", {"19": "x"}))
    state = Parameter(
        name="state", raw_value="19", parameter_type=STRING_PARAMETER_TYPE
    )
    assert enum_state_label(mapping, state, None) == "Standby"  # catalog

    uncatalogued = Parameter(
        name="state", raw_value="42", parameter_type=STRING_PARAMETER_TYPE
    )
    assert enum_state_label(mapping, uncatalogued, "Error mode") == "Error mode"
    assert enum_state_label(mapping, uncatalogued, None) == "42"


def test_binary_is_on_semantics():
    boiler_on = classify_parameter(string_param("boilerOn", {"0": "a", "1": "b"}))
    on_param = Parameter(name="boilerOn", raw_value="0", parameter_type=STRING_PARAMETER_TYPE)
    off_param = Parameter(name="boilerOn", raw_value="1", parameter_type=STRING_PARAMETER_TYPE)
    assert binary_is_on(boiler_on, on_param) is True  # raw "0" means on here
    assert binary_is_on(boiler_on, off_param) is False

    pump = classify_parameter(numeric_param("dhwPumpControl"))
    assert binary_is_on(pump, Parameter(name="dhwPumpControl", raw_value="0", parameter_type=NUMERIC_PARAMETER_TYPE)) is False
    assert binary_is_on(pump, Parameter(name="dhwPumpControl", raw_value="35", parameter_type=NUMERIC_PARAMETER_TYPE)) is True
    assert binary_is_on(pump, Parameter(name="dhwPumpControl", raw_value="", parameter_type=NUMERIC_PARAMETER_TYPE)) is None


def test_device_names_are_unlocalized():
    assert device_name("BOILER", 1) == "Boiler 1"
    assert device_name("CIRCUIT", 2) == "Heating circuit 2"
    assert device_name("PELLET_STORAGE", 1) == "Pellet storage 1"
    assert device_name("SOMETHING_NEW", 3) == "Something New 3"


#
# 5.4 — the translation catalogs cover the keys the mapping uses
#
def test_strings_json_covers_entity_catalog():
    strings = json.loads(
        (COMPONENT_DIR / "strings.json").read_text(encoding="utf-8")
    )
    sensor_keys, binary_keys = {}, {}
    for name, label in PARAMETER_NAMES.items():
        if name in BOOLEAN_ENUM_ON_VALUES or PUMP_NAME_FRAGMENT in name.lower():
            binary_keys[name] = {"name": label}
        else:
            sensor_keys[name] = {"name": label}
    assert strings["entity"] == {
        "binary_sensor": binary_keys,
        "sensor": sensor_keys,
    }

    translations = json.loads(
        (COMPONENT_DIR / "translations" / "en.json").read_text(encoding="utf-8")
    )
    assert translations == strings
