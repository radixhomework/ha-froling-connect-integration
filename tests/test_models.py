"""Tests for the typed API models, verified against recorded fixtures."""

from custom_components.froling_connect.models import (
    NUMERIC_PARAMETER_TYPE,
    STRING_PARAMETER_TYPE,
    Component,
    Facility,
    FacilityOverview,
    Notification,
    Parameter,
    UserProfile,
)


#
# 2.1 — parameter and component models against the component fixture
#
def test_numeric_parameter_from_component_fixture(load_fixture):
    component = Component.from_dict(load_fixture("component.json"), detailed=True)
    assert component is not None
    assert component.component_id == "1_100"
    assert component.type == "BOILER"

    boiler_temp = component.parameters["boilerTemp"]
    assert boiler_temp.id == "3_0"
    assert boiler_temp.raw_value == "78"
    assert boiler_temp.value == 78.0
    assert boiler_temp.editable is False
    assert boiler_temp.unit == "°C"
    assert boiler_temp.min_val == -16000.0
    assert boiler_temp.max_val == 16000.0


def test_writable_parameters_keep_ranges_and_enums(load_fixture):
    component = Component.from_dict(load_fixture("component.json"), detailed=True)
    assert component is not None

    set_temp = component.parameters["boilerSetTemp"]
    assert set_temp.editable is True
    assert set_temp.min_val == 60.0
    assert set_temp.max_val == 90.0

    mode2 = component.parameters["mode2"]
    assert mode2.parameter_type == STRING_PARAMETER_TYPE
    assert mode2.editable is True
    assert mode2.string_list["2"] == "Automatik"


def test_component_list_fixture(load_fixture):
    components = [
        component for component in map(Component.from_dict, load_fixture("component_list.json"))
    ]
    assert [c.component_id for c in components] == [
        "1_100",
        "300_3100",
        "300_3110",
        "200_2100",
        "400_4100",
    ]
    assert components[0].type == "BOILER"
    # DHW entries carry no subType
    assert components[3].type == "DHW"
    assert components[3].sub_type == ""
    assert all(not component.parameters for component in components)


#
# 2.5 — value coercion by declared type
#
def test_numeric_values_coerce_to_float():
    numeric = Parameter(name="p", raw_value="60.0", parameter_type=NUMERIC_PARAMETER_TYPE)
    assert numeric.value == 60.0


def test_numeric_values_that_cannot_parse_yield_none(caplog):
    for raw in ("", "abc"):
        param = Parameter(name="p", raw_value=raw, parameter_type=NUMERIC_PARAMETER_TYPE)
        assert param.value is None


def test_string_values_stay_raw():
    param = Parameter(
        name="p",
        raw_value="2",
        parameter_type=STRING_PARAMETER_TYPE,
        string_list={"2": "Automatik"},
    )
    assert param.value == "2"


#
# overview, facility, user, notifications
#
def test_overview_fixture(load_fixture):
    overview = FacilityOverview.from_dict(load_fixture("overview.json"))
    assert overview is not None
    assert overview.out_temp is not None
    assert overview.out_temp.raw_value == "20"

    boiler = overview.components["1_100"]
    assert boiler.values["boilerTemp"].raw_value == "76"
    assert boiler.values["boilerTemp"].unit == "°C"
    assert boiler.values["state"].display_value == "Standby"

    buffer = overview.components["400_4100"]
    assert buffer.values["bufferTankCharge"].raw_value == "97"
    assert buffer.values["bufferTankCharge"].unit == "%"

    # schedules and picture URLs are metadata, not values
    assert "heatingPhase" not in buffer.values
    assert "svgUrl" not in buffer.values


def test_facility_fixture(load_fixture):
    facilities = [f for f in map(Facility.from_dict, load_fixture("facility.json"))]
    assert [f.facility_id for f in facilities] == [12345, 54321]
    assert facilities[0].product_type == "T4e 230-250"
    assert facilities[0].equipment_number == 100321123


def test_user_profile_fixture(load_fixture):
    profile = UserProfile.from_dict(load_fixture("login.json"))
    assert profile is not None
    assert profile.user_id == 12345
    assert profile.email == "user@example.com"
    assert profile.language == "de"


def test_notification_fixtures(load_fixture):
    notifications = [
        n for n in map(Notification.from_dict, load_fixture("notification_list.json"))
    ]
    assert len(notifications) == 3
    assert notifications[1].notification_type == "ALARM"
    assert notifications[1].unread is True
    assert notifications[2].facility_id is None

    single = Notification.from_dict(load_fixture("notification.json"))
    assert single is not None
    assert "text" in single.body


#
# tolerant parsing: garbage in, debug-skip out — never a crash
#
def test_malformed_objects_are_skipped():
    assert Parameter.from_dict(None) is None
    assert Parameter.from_dict({}) is None
    assert Parameter.from_dict({"name": "x"}) is None  # no value
    assert Parameter.from_dict({"value": "1"}) is None  # no name
    assert Component.from_dict("junk") is None
    assert Component.from_dict({"displayName": "no id"}) is None
    assert Facility.from_dict({"name": "no id"}) is None
    assert FacilityOverview.from_dict(None) is None
    assert Notification.from_dict({"subject": "no id"}) is None


def test_overview_with_junk_entries_is_tolerated():
    overview = FacilityOverview.from_dict(
        {
            "outTemp": "not-a-dict",
            "components": [
                "junk",
                {"componentId": "x_1", "active": True, "weirdParam": {"value": "3"}},
            ],
        }
    )
    assert overview is not None
    assert overview.out_temp is None
    assert set(overview.components) == {"x_1"}
    assert overview.components["x_1"].values["weirdParam"].raw_value == "3"
