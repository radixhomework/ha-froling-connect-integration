"""Alarm surface tests: boiler fault states (6.1) and notification cadence (6.2)."""

from unittest.mock import AsyncMock

import pytest

from custom_components.froling_connect import coordinator as coordinator_module
from custom_components.froling_connect.coordinator import (
    NOTIFICATIONS_EVERY_CYCLES,
)
from custom_components.froling_connect.exceptions import NetworkError
from custom_components.froling_connect.models import (
    FacilityOverview,
    Notification,
    OverviewValue,
)
from test_coordinator import make_client, make_coordinator
from test_platforms import FACILITY_ID, setup_integration, state_of


@pytest.fixture(autouse=True)
def no_pace(monkeypatch):
    monkeypatch.setattr(coordinator_module, "REQUEST_PAUSE", 0)


def with_fault_state(load_fixture, raw: str, display: str):
    """Fixture variants where the boiler reports a fault raw value.

    The state parameter appears in several response views (topView sections
    and stateView); every occurrence must change or the merge order picks
    the unmodified one.
    """
    component = load_fixture("component.json")

    def fault(parameters):
        for parameter in parameters:
            if parameter.get("name") == "state":
                parameter["value"] = raw

    fault(component.get("stateView", []))
    fault(component.get("setupView", []))
    top_view = component.get("topView", {})
    for section in ("pictureParams", "infoParams", "configParams"):
        fault(list(top_view.get(section, {}).values()))

    overview = FacilityOverview.from_dict(load_fixture("overview.json"))
    overview.components["1_100"].values["state"] = OverviewValue(
        raw_value=raw, display_value=display, unit=""
    )
    return component, overview


#
# 6.1 — the boiler state sensor reflects fault entries of its enumeration
#
async def test_boiler_state_shows_fault_meaning(hass, load_fixture):
    component, overview = with_fault_state(
        load_fixture, "25", "Error: flue gas temperature too high"
    )

    await setup_integration(hass, load_fixture, overview=overview, component=component)

    state = state_of(hass, f"{FACILITY_ID}_1_100_77_457")
    assert state.state == "Error: flue gas temperature too high"


async def test_untranslated_fault_falls_back_to_raw_value(hass, load_fixture):
    component, overview = with_fault_state(load_fixture, "88", "")

    await setup_integration(hass, load_fixture, overview=overview, component=component)

    state = state_of(hass, f"{FACILITY_ID}_1_100_77_457")
    assert state.state == "88"


#
# 6.2 — notifications ride the same coordinator on a slower sub-cadence
#
async def test_notifications_fetch_on_first_cycle_then_every_nth(hass, load_fixture):
    client = make_client(load_fixture)
    coordinator = make_coordinator(hass, client)
    await coordinator.async_setup()

    # cycle 1: forced fetch (first refresh surfaces the alarm state immediately)
    await coordinator._async_update_data()
    assert client.get_notifications.await_count == 1

    # cycles 2..N: values refresh, notifications are NOT requested
    for _ in range(NOTIFICATIONS_EVERY_CYCLES - 1):
        await coordinator._async_update_data()
    assert client.get_notifications.await_count == 1
    assert client.get_overview.await_count == 1  # same sub-cadence as notifications

    # next cycle: notifications requested again
    await coordinator._async_update_data()
    assert client.get_notifications.await_count == 2


async def test_notifications_are_facility_filtered_and_counted(hass, load_fixture):
    client = make_client(load_fixture)
    client.get_notifications = AsyncMock(
        return_value=[
            notification
            for notification in map(
                Notification.from_dict, load_fixture("notification_list.json")
            )
        ]
    )
    coordinator = make_coordinator(hass, client)
    await coordinator.async_setup()

    await coordinator._async_update_data()

    # fixture: 2 notifications for facility 12345 (one unread ALARM) + 1
    # facility-less entry; unread count covers the surfaced set
    assert coordinator.data.unread_notification_count == 1
    assert [n.subject for n in coordinator.data.notifications] == [
        "Subject 1",
        "Subject 2",
        "Subject 3",
    ]
    assert coordinator.data.notifications[1].notification_type == "ALARM"


async def test_notification_failure_does_not_kill_value_refresh(
    hass, load_fixture, caplog
):
    client = make_client(load_fixture)
    coordinator = make_coordinator(hass, client)
    await coordinator.async_setup()
    client.get_notifications = AsyncMock(side_effect=NetworkError("backend hiccup"))

    data = await coordinator._async_update_data()

    # values survive a notifications outage; the problem is logged
    assert data.components["1_100"].schema.parameters["boilerTemp"].value == 78.0
    assert any("notifications" in r.message.lower() for r in caplog.records)
