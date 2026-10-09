"""Entity base classes for the Fröling Connect integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ComponentSnapshot, FroelingConnectCoordinator
from .mapping import device_name


class FroelingEntity(CoordinatorEntity[FroelingConnectCoordinator]):
    """Base entity: read-only, device-grouped, driven by the shared coordinator."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: FroelingConnectCoordinator,
        entry: ConfigEntry,
        component_snapshot: ComponentSnapshot | None,
    ) -> None:
        """Initialize against the shared coordinator and its device."""
        super().__init__(coordinator)
        facility_id = int(entry.data["facility_id"])
        if component_snapshot is None:
            # facility device: one device representing the installation itself
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, str(facility_id))},
                name=entry.title,
                manufacturer="Fröling",
            )
        else:
            schema = component_snapshot.schema
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, f"{facility_id}_{schema.component_id}")},
                via_device=(DOMAIN, str(facility_id)),
                name=device_name(schema.type, schema.component_number),
                manufacturer="Fröling",
                model=schema.sub_type or None,
            )
