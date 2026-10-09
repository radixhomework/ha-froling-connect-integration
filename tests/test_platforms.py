"""Platform tests: entities created from fixtures, device grouping (tasks 5.2/5.3)."""

from datetime import timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.froling_connect.const import (
    CONF_FACILITY_ID,
    CONF_UPDATE_INTERVAL,
    DOMAIN,
)
from custom_components.froling_connect.models import (
    Component,
    FacilityOverview,
    Notification,
)

FACILITY_ID = 12345
INIT_CLIENT = "custom_components.froling_connect.FroelingClient"


def make_client(load_fixture, overview: FacilityOverview | None = None, component: dict | None = None) -> MagicMock:
    """Client mock serving the recorded boiler fixtures (component + overview)."""
    listing = [
        c
        for c in map(Component.from_dict, load_fixture("component_list.json"))
        if c.component_id == "1_100"
    ]
    client = MagicMock()
    client.login = AsyncMock()
    client.get_component_list = AsyncMock(return_value=listing)
    client.get_component = AsyncMock(
        return_value=Component.from_dict(
            component or load_fixture("component.json"), detailed=True
        )
    )
    client.get_overview = AsyncMock(
        return_value=overview or FacilityOverview.from_dict(load_fixture("overview.json"))
    )
    client.get_notifications = AsyncMock(
        return_value=[
            notification
            for notification in map(Notification.from_dict, load_fixture("notification_list.json"))
        ]
    )
    return client


async def setup_integration(
    hass,
    load_fixture,
    overview: FacilityOverview | None = None,
    options: dict | None = None,
    component: dict | None = None,
):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=str(FACILITY_ID),
        title="My heating",
        data={
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "secret",
            CONF_FACILITY_ID: FACILITY_ID,
        },
        options=options or {},
    )
    entry.add_to_hass(hass)
    client = make_client(load_fixture, overview=overview, component=component)
    # patch the class so construction yields the scripted instance
    with patch(INIT_CLIENT, MagicMock(return_value=client)):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    return entry, client


def state_of(hass, unique_id: str):
    """Resolve an entity through the registry and return its HA state."""
    registry = er.async_get(hass)
    entry = registry.async_get_entity_id("sensor", DOMAIN, unique_id) or registry.async_get_entity_id(
        "binary_sensor", DOMAIN, unique_id
    )
    assert entry is not None, unique_id
    return hass.states.get(entry)


#
# 5.2 — entities created from the recorded fixtures
#
async def test_fixture_parameters_become_read_only_entities(hass, load_fixture):
    await setup_integration(hass, load_fixture)

    # boiler temperature: live value from the component response, unit and
    # device class applied
    boiler_temp = state_of(hass, f"{FACILITY_ID}_1_100_3_0")
    assert boiler_temp.state == "78.0"
    assert boiler_temp.attributes["unit_of_measurement"] == "°C"
    assert boiler_temp.attributes["device_class"] == "temperature"

    # boiler state enum: catalog translation wins over the localized API text
    state = state_of(hass, f"{FACILITY_ID}_1_100_77_457")
    assert state.state == "Standby"
    registry_entry = er.async_get(hass).async_get(state.entity_id)
    assert registry_entry.entity_category == "diagnostic"

    # boiler set temperature: schema value (no overview counterpart)
    set_temp = state_of(hass, f"{FACILITY_ID}_1_100_7_28")
    assert set_temp.state == "80.0"

    # boilerOn: fixture raw "0" means on for this parameter
    boiler_on = state_of(hass, f"{FACILITY_ID}_1_100_995_9887")
    assert boiler_on.domain == "binary_sensor"
    assert boiler_on.state == "on"

    # operation hours: cumulative counter from the schema
    hours = state_of(hass, f"{FACILITY_ID}_1_100_70_98")
    assert hours.state == "1234.0"
    assert hours.attributes["unit_of_measurement"] == "h"

    # bufferPumpControl: pump parameter, raw "0" means off
    pump = state_of(hass, f"{FACILITY_ID}_1_100_3_140")
    assert pump.domain == "binary_sensor"
    assert pump.state == "off"

    # unknown-catalog parameter: keeps its machine name, still a sensor
    primary_air = state_of(hass, f"{FACILITY_ID}_1_100_3_16")
    assert primary_air is not None

    # facility-level outside temperature on the facility device
    out_temp = state_of(hass, f"{FACILITY_ID}_outTemp")
    assert out_temp.state == "20.0"
    assert out_temp.attributes["unit_of_measurement"] == "°C"

    # notifications: unread count + the recent list as attributes
    notifications = state_of(hass, f"{FACILITY_ID}_notifications")
    assert notifications.state == "1"  # only Subject 2 (ALARM) is unread
    listed = notifications.attributes["notifications"]
    assert listed[1]["subject"] == "Subject 2"
    assert listed[1]["type"] == "ALARM"
    assert listed[1]["unread"] is True


#
# 5.3 — device grouping
#
async def test_devices_group_by_component_with_facility_device(hass, load_fixture):
    await setup_integration(hass, load_fixture)

    device_registry = dr.async_get(hass)
    by_id = {
        next(iter(device.identifiers)): device
        for device in device_registry.devices.values()
        if any(identifier[0] == DOMAIN for identifier in device.identifiers)
    }

    facility = by_id[(DOMAIN, str(FACILITY_ID))]
    assert facility.name == "My heating"

    boiler = by_id[(DOMAIN, f"{FACILITY_ID}_1_100")]
    assert boiler.name == "Boiler 1"
    assert boiler.via_device_id is not None  # linked under the facility device

    # the notifications entity belongs to the facility device
    registry = er.async_get(hass)
    notification_entry = registry.async_get(
        state_of(hass, f"{FACILITY_ID}_notifications").entity_id
    )
    assert notification_entry.device_id == facility.id

    # the boiler temperature entity belongs to the boiler device
    registry = er.async_get(hass)
    entity_entry = registry.async_get(
        registry.async_get_entity_id("sensor", DOMAIN, f"{FACILITY_ID}_1_100_3_0")
    )
    assert entity_entry.device_id == boiler.id


#
# data-refresh spec: interval defaults, configuration, and read-only surface
#
async def test_default_interval_is_60_seconds(hass, load_fixture):
    entry, _ = await setup_integration(hass, load_fixture)
    assert entry.runtime_data.update_interval == timedelta(seconds=60)


async def test_configured_interval_is_applied(hass, load_fixture):
    entry, _ = await setup_integration(
        hass, load_fixture, options={CONF_UPDATE_INTERVAL: 120}
    )
    assert entry.runtime_data.update_interval == timedelta(seconds=120)


async def test_no_services_are_registered(hass, load_fixture):
    """The integration is read-only: it registers no services at all."""
    component_dir = (
        Path(__file__).parents[1] / "custom_components" / "froling_connect"
    )
    assert not (component_dir / "services.yaml").exists()
