"""Coordinator tests: discovery, refresh branches, pacing, backoff, recovery."""

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


@pytest.fixture(autouse=True)
def no_pace(monkeypatch):
    """Keep the pacing pause out of test timing (mechanism is tested separately)."""
    monkeypatch.setattr(coordinator_module, "REQUEST_PAUSE", 0)


def test_coordinator_clamps_interval_to_floor(hass):
    client = MagicMock()
    coordinator = make_coordinator(hass, client, update_interval=10)
    assert coordinator.update_interval == timedelta(seconds=30)


#
# 4.1 — schema discovery and the overview refresh cycle
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


async def test_overview_cycle_issues_one_request_and_matches_schema(hass, load_fixture):
    client = make_client(load_fixture)
    coordinator = make_coordinator(hass, client)
    await coordinator.async_setup()
    client.get_component.reset_mock()

    data = await coordinator._async_update_data()

    client.get_overview.assert_awaited_once_with(FACILITY_ID)
    client.get_component.assert_not_awaited()  # schema is cached, values only

    boiler = data.components["1_100"]
    # value comes from the overview ("76"), not the schema's stored one ("78")
    assert boiler.schema.parameters["boilerTemp"].value == 76.0
    assert boiler.display_values["state"] == "Standby"
    assert boiler.schema.parameters["state"].value == "19"
    # schema parameter whose value the overview also reports: overview wins
    assert data.components["300_3100"].schema.parameters["actualFlowTemp"].value == 39.0
    # facility-level reading
    assert data.out_temp is not None
    assert data.out_temp.value == 20.0


async def test_overview_parameters_unknown_to_schema_are_ignored(hass, load_fixture):
    client = make_client(load_fixture)
    coordinator = make_coordinator(hass, client)
    await coordinator.async_setup()

    data = await coordinator._async_update_data()

    # the overview fixture carries mode2/boilerOn/... that the schema lacks
    assert "mode2" not in data.components["1_100"].schema.parameters
    assert "mode2" not in data.components["1_100"].display_values


#
# 4.2 — per-component polling fallback
#
async def test_component_polling_fallback_fetches_every_component(hass, load_fixture):
    client = make_client(load_fixture)
    coordinator = make_coordinator(hass, client)
    await coordinator.async_setup()
    coordinator.enable_component_polling()
    client.get_component.reset_mock()

    data = await coordinator._async_update_data()

    client.get_overview.assert_not_awaited()
    assert [call.args[1] for call in client.get_component.await_args_list] == [
        "1_100",
        "300_3100",
    ]
    # values come from the component responses themselves
    assert data.components["1_100"].schema.parameters["boilerTemp"].value == 78.0
    assert data.components["300_3100"].schema.parameters["actualFlowTemp"].value == 35.0


#
# 4.3 — sequential pacing
#
async def test_component_polling_paces_between_sequential_requests(
    hass, load_fixture, monkeypatch
):
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(coordinator_module.asyncio, "sleep", fake_sleep)
    client = make_client(load_fixture)
    coordinator = make_coordinator(hass, client)
    await coordinator.async_setup()
    sleeps.clear()
    # pretend notifications were just fetched so this cycle measures only
    # the component-polling pacing (notifications have their own test)
    coordinator._cycles_since_notifications = 0
    coordinator.enable_component_polling()

    await coordinator._async_update_data()

    # exactly one paced pause, between the two component requests
    assert len(sleeps) == 1


#
# 4.4 — rate limiting: doubling, Retry-After, cap, single warning, restore
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

    caplog.clear()
    client.get_overview = AsyncMock(side_effect=RateLimitError(None))
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()
    assert len([r for r in caplog.records if r.levelname == "WARNING"]) == 1


#
# 4.5 — transient failures: backoff, availability, recovery, reauth
#
async def test_transient_failures_back_off_and_recover(hass, load_fixture):
    client = make_client(load_fixture)
    coordinator = make_coordinator(hass, client)
    await coordinator.async_setup()
    client.get_overview = AsyncMock(side_effect=NetworkError("down"))

    for expected in (120, 240, 480):
        with pytest.raises(UpdateFailed):
            await coordinator._async_update_data()
        assert coordinator.update_interval == timedelta(seconds=expected)

    # availability driver: a failed refresh marks the coordinator unsuccessful
    await coordinator.async_refresh()
    assert coordinator.last_update_success is False

    client.get_overview = AsyncMock(
        return_value=FacilityOverview.from_dict(load_fixture("overview.json"))
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
