"""Config and options flows for the Fröling Connect integration."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .client import FroelingClient
from .const import (
    CONF_EMAIL,
    CONF_FACILITY_ID,
    CONF_PASSWORD,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    MIN_UPDATE_INTERVAL,
)
from .exceptions import (
    AuthenticationError,
    NetworkError,
    ParsingError,
    RateLimitError,
)
from .models import Facility


def _facility_options(facilities: list[Facility]) -> dict[int, str]:
    """Map facility ids to their display labels for the selection form."""
    return {
        facility.facility_id: (
            f"{facility.name} ({facility.product_type})"
            if facility.product_type
            else facility.name
        )
        for facility in facilities
    }


async def _validate_credentials(
    hass, email: str, password: str
) -> list[Facility]:
    """Log in with the given credentials and list the managed facilities.

    Raises the client's own exceptions on failure; the flow steps map them
    to form errors.
    """
    client = FroelingClient(email, password, async_get_clientsession(hass))
    await client.login()
    return await client.get_facilities()


def _credential_errors(error: Exception) -> str:
    """Map a client exception from the login/list phase to a form error key."""
    if isinstance(error, AuthenticationError):
        return "invalid_auth"
    if isinstance(error, (NetworkError, ParsingError, RateLimitError)):
        return "cannot_connect"
    return "cannot_connect"


class FroelingConnectConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the config flow: credentials, facility choice, reauthentication."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the flow state."""
        self._facilities: list[Facility] = []
        self._credentials: dict[str, Any] = {}
        self._reauth_entry: config_entries.ConfigEntry | None = None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Ask for credentials, then create an entry or offer facility choice."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                facilities = await _validate_credentials(
                    self.hass, user_input[CONF_EMAIL], user_input[CONF_PASSWORD]
                )
            except Exception as err:  # mapped below; the flow must not crash
                errors["base"] = _credential_errors(err)
            else:
                if not facilities:
                    return self.async_abort(reason="no_facilities")
                self._credentials = user_input
                if len(facilities) == 1:
                    return await self._async_create_entry(facilities[0])
                self._facilities = facilities
                return await self.async_step_facility()

        schema = vol.Schema(
            {
                vol.Required(CONF_EMAIL): cv.string,
                vol.Required(CONF_PASSWORD): cv.string,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_facility(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Let the user pick which installation to monitor."""
        errors: dict[str, str] = {}
        if user_input is not None:
            selected = next(
                (
                    facility
                    for facility in self._facilities
                    if facility.facility_id == user_input[CONF_FACILITY_ID]
                ),
                None,
            )
            if selected is not None:
                return await self._async_create_entry(selected)
            errors["base"] = "unknown_facility"

        return self.async_show_form(
            step_id="facility",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_FACILITY_ID): vol.In(
                        _facility_options(self._facilities)
                    )
                }
            ),
            errors=errors,
        )

    async def _async_create_entry(self, facility: Facility) -> FlowResult:
        """Create the entry for the selected installation."""
        await self.async_set_unique_id(str(facility.facility_id))
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=facility.name or DOMAIN,
            data={**self._credentials, CONF_FACILITY_ID: facility.facility_id},
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        """Start a reauthentication for an existing entry."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Ask for fresh credentials and update the entry on success."""
        errors: dict[str, str] = {}
        assert self._reauth_entry is not None
        if user_input is not None:
            try:
                facilities = await _validate_credentials(
                    self.hass, user_input[CONF_EMAIL], user_input[CONF_PASSWORD]
                )
            except Exception as err:
                errors["base"] = _credential_errors(err)
            else:
                facility_id = self._reauth_entry.data[CONF_FACILITY_ID]
                if not any(
                    facility.facility_id == facility_id for facility in facilities
                ):
                    errors["base"] = "unknown_facility"
                else:
                    self.hass.config_entries.async_update_entry(
                        self._reauth_entry,
                        data={**self._reauth_entry.data, **user_input},
                    )
                    await self.hass.config_entries.async_reload(
                        self._reauth_entry.entry_id
                    )
                    return self.async_abort(reason="reauth_successful")

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_EMAIL,
                    default=self._reauth_entry.data.get(CONF_EMAIL, ""),
                ): cv.string,
                vol.Required(CONF_PASSWORD): cv.string,
            }
        )
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=schema, errors=errors
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> FroelingConnectOptionsFlow:
        """Create the options flow handler."""
        return FroelingConnectOptionsFlow(config_entry)


class FroelingConnectOptionsFlow(config_entries.OptionsFlow):
    """Options flow: polling interval, clamped to the 30-second floor."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Store the entry this flow configures."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Show and store the polling interval option."""
        if user_input is not None:
            interval = max(MIN_UPDATE_INTERVAL, int(user_input[CONF_UPDATE_INTERVAL]))
            return self.async_create_entry(
                title="", data={CONF_UPDATE_INTERVAL: interval}
            )

        current = self.config_entry.options.get(
            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
        )
        schema = vol.Schema(
            {vol.Required(CONF_UPDATE_INTERVAL, default=current): cv.positive_int}
        )
        return self.async_show_form(step_id="init", data_schema=schema)
