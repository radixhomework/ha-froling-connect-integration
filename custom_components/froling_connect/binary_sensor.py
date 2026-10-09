"""Binary sensor platform for the Fröling Connect integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import ComponentSnapshot
from .entity import FroelingEntity
from .mapping import (
    EntityMapping,
    binary_is_on,
    build_parameter_unique_id,
    classify_parameter,
    humanize_parameter_name,
)
from .models import Parameter


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Create the binary sensor entities of a config entry from the cached schemas."""
    coordinator = entry.runtime_data
    facility_id = int(entry.data["facility_id"])

    entities: list[BinarySensorEntity] = []
    for component_snapshot in coordinator.data.components.values():
        for parameter in component_snapshot.schema.parameters.values():
            mapping = classify_parameter(parameter)
            if mapping.platform == Platform.BINARY_SENSOR:
                entities.append(
                    FroelingBinarySensor(
                        coordinator,
                        entry,
                        component_snapshot,
                        parameter,
                        mapping,
                        facility_id,
                    )
                )
    async_add_entities(entities)


class FroelingBinarySensor(FroelingEntity, BinarySensorEntity):
    """A parameter exposed as a read-only binary sensor (pumps, on/off states)."""

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        component_snapshot: ComponentSnapshot,
        parameter: Parameter,
        mapping: EntityMapping,
        facility_id: int,
    ) -> None:
        """Initialize the binary sensor from its mapping."""
        super().__init__(coordinator, entry, component_snapshot)
        self._parameter = parameter
        self._mapping = mapping
        self._attr_unique_id = build_parameter_unique_id(
            facility_id, component_snapshot.schema.component_id, parameter.id
        )
        self._attr_translation_key = mapping.translation_key
        if mapping.translation_key is None:
            self._attr_name = humanize_parameter_name(parameter.name)

    @property
    def is_on(self) -> bool | None:
        """Whether the signal is active, or None when unknown."""
        return binary_is_on(self._mapping, self._parameter)
