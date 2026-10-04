"""Tests for the config, reauthentication, and options flows.

The FrölingClient used by the flows is replaced by a scripted mock; no
network is involved.
"""

from unittest.mock import AsyncMock, MagicMock, patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.froling_connect.const import (
    CONF_FACILITY_ID,
    CONF_UPDATE_INTERVAL,
    DOMAIN,
)
from custom_components.froling_connect.exceptions import AuthenticationError, NetworkError
from custom_components.froling_connect.models import Component, FacilityOverview, Facility

EMAIL = "user@example.com"
PASSWORD = "secret"
FACILITY_ID = 12345
OTHER_FACILITY_ID = 54321

FLOW_CLIENT = "custom_components.froling_connect.config_flow.FroelingClient"
INIT_CLIENT = "custom_components.froling_connect.FroelingClient"


def one_facility() -> list[Facility]:
    return [
        Facility(
            facility_id=FACILITY_ID, name="My heating", product_type="Pellet PE1"
        )
    ]


def facilities_from(load_fixture) -> list[Facility]:
    return [f for f in map(Facility.from_dict, load_fixture("facility.json"))]


def client_class_mock(
    facilities: list[Facility], login_error: Exception | None = None
) -> MagicMock:
    """Build a FroelingClient class mock whose instances are scripted."""
    mock_cls = MagicMock()
    instance = mock_cls.return_value
    instance.login = AsyncMock(side_effect=login_error) if login_error else AsyncMock()
    instance.get_facilities = AsyncMock(return_value=facilities)
    # used by the coordinator during entry setup (schema discovery + 1st refresh)
    test_component = Component(
        component_id="t_1", display_name="Test boiler", component_number=1, type="BOILER"
    )
    instance.get_component_list = AsyncMock(return_value=[test_component])
    instance.get_component = AsyncMock(return_value=test_component)
    instance.get_overview = AsyncMock(return_value=FacilityOverview())
    instance.get_notifications = AsyncMock(return_value=[])
    return mock_cls


def make_entry(
    unique_id: str = str(FACILITY_ID), options: dict | None = None
) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=unique_id,
        data={
            CONF_EMAIL: "old@example.com",
            CONF_PASSWORD: "old",
            CONF_FACILITY_ID: FACILITY_ID,
        },
        options=options or {},
    )
    return entry


#
# 3.1 — config flow
#
async def test_user_flow_single_facility_creates_entry(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"

    with (
        patch(FLOW_CLIENT, client_class_mock(one_facility())),
        patch(INIT_CLIENT, client_class_mock(one_facility())),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_EMAIL: EMAIL, CONF_PASSWORD: PASSWORD}
        )
    await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == str(FACILITY_ID)
    assert result["data"] == {
        CONF_EMAIL: EMAIL,
        CONF_PASSWORD: PASSWORD,
        CONF_FACILITY_ID: FACILITY_ID,
    }
    assert result["result"].state is ConfigEntryState.LOADED


async def test_user_flow_multiple_facilities_asks_for_choice(hass, load_fixture):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )

    with (
        patch(FLOW_CLIENT, client_class_mock(facilities_from(load_fixture))),
        patch(INIT_CLIENT, client_class_mock(facilities_from(load_fixture))),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_EMAIL: EMAIL, CONF_PASSWORD: PASSWORD}
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "facility"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_FACILITY_ID: OTHER_FACILITY_ID}
        )
    await hass.async_block_till_done()

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_FACILITY_ID] == OTHER_FACILITY_ID
    assert result["result"].unique_id == str(OTHER_FACILITY_ID)


async def test_user_flow_invalid_credentials_shows_error(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )

    with patch(
        FLOW_CLIENT,
        client_class_mock([], login_error=AuthenticationError("bad credentials")),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_EMAIL: EMAIL, CONF_PASSWORD: PASSWORD}
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "invalid_auth"}


async def test_user_flow_connection_problem_shows_error(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )

    with patch(
        FLOW_CLIENT, client_class_mock([], login_error=NetworkError("unreachable"))
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_EMAIL: EMAIL, CONF_PASSWORD: PASSWORD}
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_without_facilities_aborts(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )

    with patch(FLOW_CLIENT, client_class_mock([])):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_EMAIL: EMAIL, CONF_PASSWORD: PASSWORD}
        )

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "no_facilities"


async def test_user_flow_aborts_when_facility_already_configured(hass, load_fixture):
    make_entry(unique_id=str(OTHER_FACILITY_ID)).add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )

    with (
        patch(FLOW_CLIENT, client_class_mock(facilities_from(load_fixture))),
        patch(INIT_CLIENT, client_class_mock(facilities_from(load_fixture))),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_EMAIL: EMAIL, CONF_PASSWORD: PASSWORD}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_FACILITY_ID: OTHER_FACILITY_ID}
        )
    await hass.async_block_till_done()

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "already_configured"


#
# 3.1 — setup entry behavior
#
async def test_setup_entry_loaded(hass):
    entry = make_entry()
    entry.add_to_hass(hass)

    with patch(INIT_CLIENT, client_class_mock(one_facility())):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED


async def test_setup_entry_auth_failure_raises_reauth(hass):
    entry = make_entry()
    entry.add_to_hass(hass)

    with patch(
        INIT_CLIENT,
        client_class_mock([], login_error=AuthenticationError("expired")),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_ERROR


async def test_setup_entry_network_failure_retries(hass):
    entry = make_entry()
    entry.add_to_hass(hass)

    with patch(INIT_CLIENT, client_class_mock([], login_error=NetworkError("down"))):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_RETRY


#
# 3.2 — reauthentication flow
#
async def test_reauth_flow_updates_credentials(hass):
    entry = make_entry()
    entry.add_to_hass(hass)

    with (
        patch(FLOW_CLIENT, client_class_mock(one_facility())),
        patch("custom_components.froling_connect.async_setup_entry", AsyncMock(return_value=True)),
        patch("custom_components.froling_connect.async_unload_entry", AsyncMock(return_value=True)),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "reauth", "entry_id": entry.entry_id},
            data=entry.data,
        )
        assert result["type"] == FlowResultType.FORM
        assert result["step_id"] == "reauth_confirm"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_EMAIL: EMAIL, CONF_PASSWORD: PASSWORD}
        )
        await hass.async_block_till_done()

    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_EMAIL] == EMAIL
    assert entry.data[CONF_PASSWORD] == PASSWORD
    assert entry.data[CONF_FACILITY_ID] == FACILITY_ID


async def test_reauth_flow_invalid_credentials_keeps_form(hass):
    entry = make_entry()
    entry.add_to_hass(hass)

    with patch(
        FLOW_CLIENT,
        client_class_mock([], login_error=AuthenticationError("bad")),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "reauth", "entry_id": entry.entry_id},
            data=entry.data,
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_EMAIL: EMAIL, CONF_PASSWORD: PASSWORD}
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}
    assert entry.data[CONF_EMAIL] == "old@example.com"


async def test_reauth_flow_unknown_facility_shows_error(hass, load_fixture):
    entry = make_entry()
    entry.add_to_hass(hass)
    # the account's facilities no longer include the configured one
    other = [f for f in facilities_from(load_fixture) if f.facility_id == OTHER_FACILITY_ID]

    with patch(FLOW_CLIENT, client_class_mock(other)):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "reauth", "entry_id": entry.entry_id},
            data=entry.data,
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_EMAIL: EMAIL, CONF_PASSWORD: PASSWORD}
        )

    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "unknown_facility"}


#
# 3.3 — options flow with the 30-second floor
#
async def test_options_flow_stores_configured_interval(hass):
    entry = make_entry(options={})
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_UPDATE_INTERVAL: 120}
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_UPDATE_INTERVAL] == 120


async def test_options_flow_clamps_interval_to_floor(hass):
    entry = make_entry(options={})
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_UPDATE_INTERVAL: 10}
    )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_UPDATE_INTERVAL] == 30
