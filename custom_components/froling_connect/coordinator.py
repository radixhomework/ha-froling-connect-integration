"""Shared data update coordinator for the Fröling Connect integration.

One coordinator per config entry performs every request: it discovers the
component parameter schemas once at setup, then refreshes current values each
cycle by fetching every component (live evidence on the reference PE1 showed
the whole-facility overview does not cover every parameter — see design.md,
decision D3). The overview itself runs on a slower sub-cadence: it is the
only source of facility-level values (outside temperature) and of localized
display texts for enum states. Requests run sequentially with a short pause;
failures back off up to a 15-minute cap and restore the configured interval
on success.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import FroelingClient
from .const import DOMAIN, MIN_UPDATE_INTERVAL
from .exceptions import AuthenticationError, FroelingConnectError, RateLimitError
from .models import Component, FacilityOverview, Notification, OverviewValue

_LOGGER = logging.getLogger(__name__)

# Pause between consecutive requests within one setup/cycle (sequential pacing).
REQUEST_PAUSE = 0.5

# Backoff ceiling, per the data-refresh spec (15 minutes).
MAX_BACKOFF_INTERVAL = 900

# The overview is the only source of facility-level values and enum display
# texts; component values come from the component fetches every cycle.
OVERVIEW_EVERY_CYCLES = 5

# Notifications ride the same coordinator but on a slower sub-cadence
# (fetched on the first cycle, then every Nth cycle).
NOTIFICATIONS_EVERY_CYCLES = 5


@dataclass
class ComponentSnapshot:
    """A component's cached schema plus its known enum display texts."""

    schema: Component
    # parameter name -> raw value -> display text (from the overview); kept
    # per raw value so a changed state never shows a stale label
    display_texts: dict[str, dict[str, str]] = field(default_factory=dict)


@dataclass
class CoordinatorData:
    """What entities read: schemas with live values, facility readings, alarms."""

    components: dict[str, ComponentSnapshot] = field(default_factory=dict)
    out_temp: OverviewValue | None = None
    unread_notification_count: int | None = None
    notifications: list[Notification] = field(default_factory=list)


class FroelingConnectCoordinator(DataUpdateCoordinator[CoordinatorData]):
    """Coordinate all Fröling Connect requests for one installation."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry | None,
        client: FroelingClient,
        facility_id: int,
        update_interval: int,
    ) -> None:
        """Initialize with the client and the configured polling interval."""
        seconds = max(MIN_UPDATE_INTERVAL, int(update_interval))
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=seconds),
        )
        # this Home Assistant version has no config_entry constructor parameter
        self.config_entry = config_entry
        self._client = client
        self._facility_id = facility_id
        self._configured_interval = seconds
        self._backoff_interval: int | None = None
        self._consecutive_failures = 0
        self._rate_limit_warned = False
        # first cycle fetches overview and notifications, then every Nth cycle
        self._cycles_since_overview = OVERVIEW_EVERY_CYCLES
        self._cycles_since_notifications = NOTIFICATIONS_EVERY_CYCLES
        self.data = CoordinatorData()

    async def async_setup(self) -> None:
        """Discover the parameter schemas of every component (paced, sequential)."""
        components = await self._client.get_component_list(self._facility_id)
        for index, component in enumerate(components):
            detailed = await self._client.get_component(
                self._facility_id, component.component_id
            )
            self.data.components[detailed.component_id] = ComponentSnapshot(
                schema=detailed
            )
            if index < len(components) - 1:
                await asyncio.sleep(REQUEST_PAUSE)

    async def _async_update_data(self) -> CoordinatorData:
        """Fetch one cycle of values, updating the shared data in place."""
        try:
            await self._async_fetch_values()
        except RateLimitError as err:
            self._note_failure(rate_limit=True, retry_after=err.retry_after)
            raise UpdateFailed("Rate limited by the Fröling Connect service") from err
        except AuthenticationError as err:
            self._async_start_reauth()
            raise UpdateFailed("Stored credentials no longer work") from err
        except FroelingConnectError as err:
            self._note_failure()
            raise UpdateFailed(f"Error fetching Fröling Connect data: {err}") from err
        self._note_success()
        return self.data

    async def _async_fetch_values(self) -> None:
        """Refresh component values every cycle; overview on its sub-cadence."""
        await self._async_fetch_components()

        self._cycles_since_overview += 1
        if self._cycles_since_overview >= OVERVIEW_EVERY_CYCLES:
            await asyncio.sleep(REQUEST_PAUSE)
            try:
                await self._async_fetch_overview()
            except (RateLimitError, AuthenticationError):
                raise  # back off / re-authenticate: never degrade these
            except FroelingConnectError as err:
                # a missed overview only delays display texts, not values
                _LOGGER.warning("Failed to fetch the facility overview: %s", err)
            self._cycles_since_overview = 0

        self._cycles_since_notifications += 1
        if self._cycles_since_notifications >= NOTIFICATIONS_EVERY_CYCLES:
            await asyncio.sleep(REQUEST_PAUSE)
            try:
                await self._async_fetch_notifications()
            except (RateLimitError, AuthenticationError):
                raise  # back off / re-authenticate: never degrade these
            except FroelingConnectError as err:
                # stale alarm surface must not fail the value refresh
                _LOGGER.warning("Failed to fetch notifications: %s", err)
            self._cycles_since_notifications = 0

    async def _async_fetch_components(self) -> None:
        """Refresh current values by fetching every component (paced, sequential)."""
        snapshots = list(self.data.components.items())
        for index, (component_id, snapshot) in enumerate(snapshots):
            component = await self._client.get_component(
                self._facility_id, component_id
            )
            for name, parameter in component.parameters.items():
                cached = snapshot.schema.parameters.get(name)
                if cached is None:
                    snapshot.schema.parameters[name] = parameter
                else:
                    cached.raw_value = parameter.raw_value
            if index < len(snapshots) - 1:
                await asyncio.sleep(REQUEST_PAUSE)

    async def _async_fetch_overview(self) -> None:
        """Harvest what only the overview provides: outTemp and display texts."""
        overview = await self._client.get_overview(self._facility_id)
        self.data.out_temp = overview.out_temp
        for component_id, overview_component in overview.components.items():
            snapshot = self.data.components.get(component_id)
            if snapshot is None:
                _LOGGER.debug(
                    "Overview contains unknown component %s", component_id
                )
                continue
            for name, overview_value in overview_component.values.items():
                if not overview_value.display_value:
                    continue
                snapshot.display_texts.setdefault(name, {})[
                    overview_value.raw_value
                ] = overview_value.display_value

    async def _async_fetch_notifications(self) -> None:
        """Fetch the account notifications relevant to this installation."""
        notifications = await self._client.get_notifications()
        relevant = [
            notification
            for notification in notifications
            if notification.facility_id in (None, self._facility_id)
        ]
        self.data.notifications = relevant
        self.data.unread_notification_count = sum(
            1 for notification in relevant if notification.unread
        )

    def _note_success(self) -> None:
        """Restore the configured cadence and re-arm the rate-limit warning."""
        self._consecutive_failures = 0
        self._rate_limit_warned = False
        if self._backoff_interval is not None:
            self._backoff_interval = None
            self.update_interval = timedelta(seconds=self._configured_interval)

    def _note_failure(
        self, rate_limit: bool = False, retry_after: float | None = None
    ) -> None:
        """Double the refresh interval for the next cycle, up to the cap."""
        self._consecutive_failures += 1
        if rate_limit and not self._rate_limit_warned:
            _LOGGER.warning(
                "Fröling Connect is rate limiting requests; "
                "increasing the refresh interval"
            )
            self._rate_limit_warned = True
        doubled = (self._backoff_interval or self._configured_interval) * 2
        backoff = min(doubled, MAX_BACKOFF_INTERVAL)
        if retry_after:
            backoff = min(max(backoff, int(retry_after)), MAX_BACKOFF_INTERVAL)
        self._backoff_interval = backoff
        self.update_interval = timedelta(seconds=backoff)

    def _async_start_reauth(self) -> None:
        """Offer reauthentication when stored credentials stop working."""
        if self.config_entry is not None:
            self.config_entry.async_start_reauth(self.hass)
