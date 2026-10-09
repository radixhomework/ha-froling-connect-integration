"""Sensor platform for the Fröling Connect integration."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import ComponentSnapshot
from .entity import FroelingEntity
from .mapping import (
    EntityMapping,
    build_facility_unique_id,
    build_parameter_unique_id,
    classify_parameter,
    enum_state_label,
    humanize_parameter_name,
)
from .models import Parameter


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Create the sensor entities of a config entry from the cached schemas."""
    coordinator = entry.runtime_data
    facility_id = int(entry.data["facility_id"])

    entities: list[SensorEntity] = []
    for component_snapshot in coordinator.data.components.values():
        for parameter in component_snapshot.schema.parameters.values():
            mapping = classify_parameter(parameter)
            if mapping.platform == Platform.SENSOR:
                entities.append(
                    FroelingSensor(
                        coordinator,
                        entry,
                        component_snapshot,
                        parameter,
                        mapping,
                        facility_id,
                    )
                )
    if coordinator.data.out_temp is not None:
        entities.append(
            OutsideTemperatureSensor(coordinator, entry, facility_id)
        )
    entities.append(NotificationsSensor(coordinator, entry, facility_id))
    async_add_entities(entities)


class FroelingSensor(FroelingEntity, SensorEntity):
    """A component parameter exposed as a (read-only) sensor."""

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        component_snapshot: ComponentSnapshot,
        parameter: Parameter,
        mapping: EntityMapping,
        facility_id: int,
    ) -> None:
        """Initialize the sensor from its mapping."""
        super().__init__(coordinator, entry, component_snapshot)
        self._parameter = parameter
        self._mapping = mapping
        self._snapshot = component_snapshot
        self._attr_unique_id = build_parameter_unique_id(
            facility_id, component_snapshot.schema.component_id, parameter.id
        )
        self._attr_translation_key = mapping.translation_key
        if mapping.translation_key is None:
            self._attr_name = humanize_parameter_name(parameter.name)
        if mapping.device_class is not None:
            self._attr_device_class = mapping.device_class
        if mapping.state_class is not None:
            self._attr_state_class = mapping.state_class
        if mapping.diagnostic:
            self._attr_entity_category = EntityCategory.DIAGNOSTIC
        if parameter.unit:
            self._attr_native_unit_of_measurement = parameter.unit

    @property
    def native_value(self) -> float | str | None:
        """The current value: numbers for readings, labels for enum states."""
        if self._mapping.diagnostic:
            return enum_state_label(
                self._mapping,
                self._parameter,
                self._snapshot.display_values.get(self._parameter.name),
            )
        return self._parameter.value


class OutsideTemperatureSensor(FroelingEntity, SensorEntity):
    """Facility-level outside air temperature."""

    _attr_translation_key = "outTemp"
    _attr_native_unit_of_measurement = "°C"

    def __init__(self, coordinator, entry: ConfigEntry, facility_id: int) -> None:
        """Initialize on the facility device."""
        super().__init__(coordinator, entry, component_snapshot=None)
        self._attr_unique_id = build_facility_unique_id(facility_id, "outTemp")

    @property
    def native_value(self) -> float | str | None:
        """The outside temperature from the latest overview."""
        overview_value = self.coordinator.data.out_temp
        return overview_value.value if overview_value else None


class NotificationsSensor(FroelingEntity, SensorEntity):
    """Alarm surface: unread notification count and the recent notifications."""

    _attr_translation_key = "notifications"
    _attr_icon = "mdi:bell-alert"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, entry: ConfigEntry, facility_id: int) -> None:
        """Initialize on the facility device."""
        super().__init__(coordinator, entry, component_snapshot=None)
        self._attr_unique_id = build_facility_unique_id(facility_id, "notifications")

    @property
    def native_value(self) -> int | None:
        """The number of unread notifications (None until the first fetch)."""
        return self.coordinator.data.unread_notification_count

    @property
    def extra_state_attributes(self) -> dict:
        """The most recent notifications with their subjects and types."""
        return {
            "notifications": [
                {
                    "id": notification.notification_id,
                    "subject": notification.subject,
                    "type": notification.notification_type,
                    "date": notification.notification_date,
                    "unread": notification.unread,
                }
                for notification in self.coordinator.data.notifications[:10]
            ]
        }
