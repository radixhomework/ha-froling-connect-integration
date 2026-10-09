"""The Fröling Connect integration: read-only monitoring of Fröling installations."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import UpdateFailed

from .client import FroelingClient
from .const import (
    CONF_EMAIL,
    CONF_FACILITY_ID,
    CONF_PASSWORD,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
)
from .coordinator import FroelingConnectCoordinator
from .exceptions import (
    AuthenticationError,
    NetworkError,
    ParsingError,
    RateLimitError,
)

# Read-only monitoring: sensors and binary sensors (alarms group next).
PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the integration; YAML configuration is not supported."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a config entry: verify credentials, discover schemas, start polling.

    A re-login that fails raises ConfigEntryAuthFailed so Home Assistant
    offers reauthentication; transient problems raise ConfigEntryNotReady
    so setup is retried with backoff.
    """
    client = FroelingClient(
        entry.data[CONF_EMAIL],
        entry.data[CONF_PASSWORD],
        async_get_clientsession(hass),
    )
    coordinator = FroelingConnectCoordinator(
        hass,
        entry,
        client,
        facility_id=int(entry.data[CONF_FACILITY_ID]),
        update_interval=int(
            entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
        ),
    )
    try:
        await client.login()
        await coordinator.async_setup()
        await coordinator.async_config_entry_first_refresh()
    except AuthenticationError as err:
        raise ConfigEntryAuthFailed(err) from err
    except (NetworkError, ParsingError, RateLimitError, UpdateFailed) as err:
        raise ConfigEntryNotReady(err) from err

    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)
