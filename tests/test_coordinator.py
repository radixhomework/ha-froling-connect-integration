"""Coordinator tests: discovery, refresh cycle, pacing, backoff, recovery."""

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.froling_connect import coordinator as coordinator_module
from custom_components.froling_connect.const import (
    CONF_EMAIL,
    CONF_FACILITY_ID,
    CONF_PASSWORD,
    DOMAIN,
)
from custom_components.froling_connect.coordinator import (
    MAX_BACKOFF_INTERVAL,
    OVERVIEW_EVERY_CYCLES,
    FroelingConnectCoordinator,
)
from custom_components.froling_connect.exceptions import (
    AuthenticationError,
    NetworkError,
    RateLimitError,
)
from custom_components.froling_connect.models import Component, FacilityOverview

FACILITY_ID = 12345


def boiler_detailed() -> dict:
    return {
        "componentId": "1_100",
        "displayName": "Boiler",
        "componentNumber": 1,
        "type": "BOILER",
        "stateView": [
            {
                "name": "boilerTemp",
                "id": "3_0",
                "displayName": "Boiler temp",
                "editable": False,
                "parameterType": "NumValueObject",
                "unit": "°C",
                "value": "78",
                "minVal": "0",
                "maxVal": "16000",
            },
            {
                "name": "state",
                "id": "77_457",
                "displayName": "Boiler state",
                "editable": False,
                "parameterType": "StringValueObject",
                "unit": "",
                "value": "19",
                "stringListKeyValues": {"19": "Standby"},
            },
        ],
    }


def circuit_detailed() -> dict:
    return {
        "componentId": "300_3100",
        "displayName": "Circuit 1",
        "componentNumber": 1,
        "type": "CIRCUIT",
        "stateView": [
            {
                "name": "actualFlowTemp",
                "id": "300_1",
                "displayName": "Flow temp",
                "editable": False,
                "parameterType": "NumValueObject",
                "unit": "°C",
                "value": "35",
                "minVal": "0",
                "maxVal": "16000",
            }
        ],
    }


def make_client(load_fixture) -> MagicMock:
    """A client mock: two components, boiler/circuit details, overview fixture."""
    client = MagicMock()
    client.get_component_list = AsyncMock(
        return_value=[
            Component(component_id="1_100", display_name="Boiler", component_number=1, type="BOILER"),
            Component(component_id="300_3100", display_name="Circuit 1", component_number=1, type="CIRCUIT"),
        ]
    )
    detailed = {"1_100": boiler_detailed(), "300_3100": circuit_detailed()}
    client.get_component = AsyncMock(
        side_effect=lambda facility_id, cid: Component.from_dict(
            detailed[cid], detailed=True
        )
    )
    client.get_overview = AsyncMock(
        return_value=FacilityOverview.from_dict(load_fixture("overview.json"))
    )
    client.get_notifications = AsyncMock(return_value=[])
    return client


def make_coordinator(hass, client, update_interval: int = 60):
    return FroelingConnectCoordinator(
        hass, None, client, facility_id=FACILITY_ID, update_interval=update_interval
    )


def skip_slow_subcadences(coordinator) -> None:
    """Pretend overview/notifications were just fetched (isolate the value cycle)."""
    coordinator._cycles_since_overview = 0
    coordinator._cycles_since_notifications = 0


@pytest.fixture(autouse=True)
def no_pace(monkeypatch):
    """Keep the pacing pause out of test timing (mechanism is tested separately)."""
    monkeypatch.setattr(coordinator_module, "REQUEST_PAUSE", 0)


def test_coordinator_clamps_interval_to_floor(hass):
    client = MagicMock()
    coordinator = make_coordinator(hass, client, update_interval=10)
    assert coordinator.update_interval == timedelta(seconds=30)


#
# schema discovery
#
async def test_setup_discovers_component_schemas(hass, load_fixture):
    client = make_client(load_fixture)
    coordinator = make_coordinator(hass, client)

    await coordinator.async_setup()

    assert set(coordinator.data.components) == {"1_100", "300_3100"}
    assert "boilerTemp" in coordinator.data.components["1_100"].schema.parameters
    # componentList, then one component fetch per component, in order
    assert client.get_component_list.await_count == 1
    assert [call.args[1] for call in client.get_component.await_args_list] == [
        "1_100",
        "300_3100",
    ]


#
# value refresh: every component, every cycle
#
async def test_component_cycle_updates_all_values(hass, load_fixture):
    client = make_client(load_fixture)
    coordinator = make_coordinator(hass, client)
    await coordinator.async_setup()
    skip_slow_subcadences(coordinator)
    client.get_component.reset_mock()

    data = await coordinator._async_update_data()

    assert client.get_overview.await_count == 0
    assert client.get_notifications.await_count == 0
    assert [call.args[1] for call in client.get_component.await_args_list] == [
        "1_100",
        "300_3100",
    ]
    # values come from the component responses themselves
    assert data.components["1_100"].schema.parameters["boilerTemp"].value == 78.0
    assert data.components["300_3100"].schema.parameters["actualFlowTemp"].value == 35.0


#
# overview sub-cadence: facility value + enum display texts, every Nth cycle
#
async def test_overview_cadence_supplies_facility_value_and_display_texts(
    hass, load_fixture
):
    client = make_client(load_fixture)
    coordinator = make_coordinator(hass, client)
    await coordinator.async_setup()
    client.get_component.reset_mock()

    # cycle 1: forced overview fetch
    data = await coordinator._async_update_data()
    assert client.get_overview.await_count == 1
    assert data.out_temp.value == 20.0
    boiler = data.components["1_100"]
    assert boiler.display_texts["state"]["19"] == "Standby"
    assert boiler.display_texts["mode2"]["2"] == "Automatic"

    # cycles 2..5: values refresh, no overview request
    for _ in range(4):
        await coordinator._async_update_data()
    assert client.get_overview.await_count == 1
    assert client.get_component.await_count == 2 * 5

    # cycle 6: overview fetched again
    await coordinator._async_update_data()
    assert client.get_overview.await_count == 2


async def test_changed_state_never_shows_a_stale_label(hass, load_fixture):
    client = make_client(load_fixture)
    coordinator = make_coordinator(hass, client)
    await coordinator.async_setup()

    await coordinator._async_update_data()  # cycle 1: display text for "19"

    # the boiler state changes to a raw the overview has not labeled yet
    changed = boiler_detailed()
    for parameter in changed["stateView"]:
        if parameter["name"] == "state":
            parameter["value"] = "25"
    client.get_component = AsyncMock(
        side_effect=lambda facility_id, cid: Component.from_dict(
            changed, detailed=True
        )
    )
    skip_slow_subcadences(coordinator)
    data = await coordinator._async_update_data()

    parameter = data.components["1_100"].schema.parameters["state"]
    assert parameter.raw_value == "25"
    # no display text exists for the new raw: resolution must not reuse "19"'s
    assert "25" not in data.components["1_100"].display_texts.get("state", {})


#
# sequential pacing
#
async def test_component_fetches_are_paced_and_sequential(hass, load_fixture, monkeypatch):
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(coordinator_module.asyncio, "sleep", fake_sleep)
    client = make_client(load_fixture)
    coordinator = make_coordinator(hass, client)
    await coordinator.async_setup()
    sleeps.clear()
    skip_slow_subcadences(coordinator)

    await coordinator._async_update_data()

    # exactly one paced pause, between the two component requests
    assert len(sleeps) == 1


#
# rate limiting: doubling, Retry-After, cap, single warning, restore
#
async def test_rate_limit_honors_retry_after_then_doubles(hass, load_fixture):
    client = make_client(load_fixture)
    coordinator = make_coordinator(hass, client)
    await coordinator.async_setup()

    client.get_overview = AsyncMock(side_effect=RateLimitError(300))
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
    assert coordinator.update_interval == timedelta(seconds=300)

    client.get_overview = AsyncMock(side_effect=RateLimitError(None))
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
    assert coordinator.update_interval == timedelta(seconds=600)


async def test_rate_limit_caps_and_warns_once(hass, load_fixture, caplog):
    client = make_client(load_fixture)
    coordinator = make_coordinator(hass, client)
    await coordinator.async_setup()
    client.get_overview = AsyncMock(side_effect=RateLimitError(None))

    for _ in range(6):
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()

    assert coordinator.update_interval == timedelta(seconds=MAX_BACKOFF_INTERVAL)
    assert len([r for r in caplog.records if r.levelname == "WARNING"]) == 1


async def test_success_restores_interval_and_rearms_warning(hass, load_fixture, caplog):
    client = make_client(load_fixture)
    coordinator = make_coordinator(hass, client)
    await coordinator.async_setup()

    client.get_overview = AsyncMock(side_effect=RateLimitError(None))
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
    assert coordinator.update_interval == timedelta(seconds=120)

    client.get_overview = AsyncMock(
        return_value=FacilityOverview.from_dict(load_fixture("overview.json"))
    )
    await coordinator._async_update_data()
    assert coordinator.update_interval == timedelta(seconds=60)

    # a new rate-limit episode warns again (force the overview sub-cadence,
    # which the successful cycle just reset)
    caplog.clear()
    coordinator._cycles_since_overview = OVERVIEW_EVERY_CYCLES
    client.get_overview = AsyncMock(side_effect=RateLimitError(None))
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
    assert len([r for r in caplog.records if r.levelname == "WARNING"]) == 1


#
# transient failures: backoff, availability, recovery, reauth
#
async def test_transient_failures_back_off_and_recover(hass, load_fixture):
    client = make_client(load_fixture)
    coordinator = make_coordinator(hass, client)
    await coordinator.async_setup()

    # the authoritative value path fails: whole cycles fail and back off
    client.get_component = AsyncMock(side_effect=NetworkError("down"))
    for expected in (120, 240, 480):
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()
        assert coordinator.update_interval == timedelta(seconds=expected)

    # availability driver: a failed refresh marks the coordinator unsuccessful
    await coordinator.async_refresh()
    assert coordinator.last_update_success is False

    detailed = {"1_100": boiler_detailed(), "300_3100": circuit_detailed()}
    client.get_component = AsyncMock(
        side_effect=lambda facility_id, cid: Component.from_dict(
            detailed[cid], detailed=True
        )
    )
    data = await coordinator._async_update_data()
    await coordinator.async_refresh()
    assert coordinator.last_update_success is True  # entities available again
    assert coordinator.update_interval == timedelta(seconds=60)
    assert data.out_temp.value == 20.0


async def test_auth_failure_triggers_reauth(hass, load_fixture):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=str(FACILITY_ID),
        data={
            CONF_EMAIL: "user@example.com",
            CONF_PASSWORD: "secret",
            CONF_FACILITY_ID: FACILITY_ID,
        },
    )
    entry.add_to_hass(hass)
    client = make_client(load_fixture)
    coordinator = FroelingConnectCoordinator(
        hass, entry, client, facility_id=FACILITY_ID, update_interval=60
    )
    await coordinator.async_setup()

    with patch.object(entry, "async_start_reauth") as start_reauth:
        client.get_overview = AsyncMock(side_effect=AuthenticationError("dead"))
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()
        start_reauth.assert_called_once()
