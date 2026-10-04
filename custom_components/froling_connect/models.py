"""Typed models for the Fröling Connect API responses.

The cloud service encodes every value (numeric or textual) as a JSON string
and attaches localized display labels. Models keep raw string values and
coerce on demand by declared parameter type. Parsing is tolerant: unexpected
shapes are logged at debug level and skipped, never raised.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

_LOGGER = logging.getLogger(__name__)

NUMERIC_PARAMETER_TYPE = "NumValueObject"
STRING_PARAMETER_TYPE = "StringValueObject"

# Overview responses mix component metadata with value objects; anything in
# this set is metadata, everything else that looks like a value object is one.
_RESERVED_OVERVIEW_KEYS = frozenset(
    {
        "displayName",
        "displayCategory",
        "componentNumber",
        "componentId",
        "type",
        "subType",
        "active",
        "svgUrl",
        "heatingPhase",
        "timeWindowsView",
    }
)


def _as_str(value: Any, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _as_int(value: Any, default: int | None = None) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


@dataclass
class Parameter:
    """A single component parameter from a component response.

    `raw_value` keeps the wire value (always a string); `value` coerces by
    the declared parameter type: a float for NumValueObject (None when not
    parseable), the raw string otherwise.
    """

    name: str
    raw_value: str
    id: str = ""
    display_name: str = ""
    editable: bool = False
    parameter_type: str = ""
    unit: str = ""
    min_val: float | None = None
    max_val: float | None = None
    string_list: dict[str, str] = field(default_factory=dict)

    @property
    def value(self) -> float | str | None:
        """The coerced value: float for numeric parameters, raw string otherwise."""
        if self.parameter_type == NUMERIC_PARAMETER_TYPE:
            coerced = _as_float(self.raw_value)
            if coerced is None:
                _LOGGER.debug(
                    "Unparseable numeric value %r for parameter %s", self.raw_value, self.name
                )
            return coerced
        return self.raw_value

    @classmethod
    def from_dict(cls, data: Any) -> Parameter | None:
        """Parse one parameter object; None when the shape is not usable."""
        if not isinstance(data, dict) or not data.get("name") or "value" not in data:
            _LOGGER.debug("Skipping malformed parameter object: %r", data)
            return None
        string_list = data.get("stringListKeyValues")
        return cls(
            name=str(data["name"]),
            raw_value=str(data["value"]),
            id=_as_str(data.get("id")),
            display_name=_as_str(data.get("displayName")),
            editable=bool(data.get("editable", False)),
            parameter_type=_as_str(data.get("parameterType")),
            unit=_as_str(data.get("unit")),
            min_val=_as_float(data.get("minVal")),
            max_val=_as_float(data.get("maxVal")),
            string_list=(
                {str(k): str(v) for k, v in string_list.items()}
                if isinstance(string_list, dict)
                else {}
            ),
        )


@dataclass
class Component:
    """An installation component: boiler, heating circuit, DHW tank, ...

    For listing responses (`componentList` endpoint) only the identity fields
    are populated. For detailed responses (`component` endpoint) `parameters`
    holds every known parameter keyed by its machine name, merged from all
    response views.
    """

    component_id: str
    display_name: str
    component_number: int
    type: str
    sub_type: str = ""
    standard_name: str = ""
    display_category: str = ""
    parameters: dict[str, Parameter] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Any, detailed: bool = False) -> Component | None:
        """Parse a component object; None when the shape is not usable."""
        if not isinstance(data, dict) or not data.get("componentId"):
            _LOGGER.debug("Skipping malformed component object: %r", data)
            return None
        component = cls(
            component_id=str(data["componentId"]),
            display_name=_as_str(data.get("displayName")),
            component_number=_as_int(data.get("componentNumber"), 0) or 0,
            type=_as_str(data.get("type")),
            sub_type=_as_str(data.get("subType")),
            standard_name=_as_str(data.get("standardName")),
            display_category=_as_str(data.get("displayCategory")),
        )
        if not detailed:
            return component
        top_view = data.get("topView")
        for section in ("pictureParams", "infoParams", "configParams"):
            params = top_view.get(section) if isinstance(top_view, dict) else None
            if not isinstance(params, dict):
                continue
            for raw in params.values():
                param = Parameter.from_dict(raw)
                if param is not None:
                    component.parameters[param.name] = param
        for view in ("stateView", "setupView"):
            params = data.get(view)
            if not isinstance(params, list):
                continue
            for raw in params:
                param = Parameter.from_dict(raw)
                if param is not None:
                    component.parameters[param.name] = param
        return component


@dataclass
class Facility:
    """A heating installation managed by the account."""

    facility_id: int
    name: str
    status: str = ""
    equipment_number: int | None = None
    owner: str = ""
    role: str = ""
    product_type: str = ""
    facility_generation: str = ""

    @classmethod
    def from_dict(cls, data: Any) -> Facility | None:
        """Parse one facility object; None when the shape is not usable."""
        facility_id = _as_int(data.get("facilityId")) if isinstance(data, dict) else None
        if facility_id is None:
            _LOGGER.debug("Skipping malformed facility object: %r", data)
            return None
        protocol_info = data.get("protocol3200Info")
        return cls(
            facility_id=facility_id,
            name=_as_str(data.get("name")),
            status=_as_str(data.get("status")),
            equipment_number=_as_int(data.get("equipmentNumber")),
            owner=_as_str(data.get("owner")),
            role=_as_str(data.get("role")),
            product_type=(
                _as_str(protocol_info.get("productType"))
                if isinstance(protocol_info, dict)
                else ""
            ),
            facility_generation=_as_str(data.get("facilityGeneration")),
        )


@dataclass
class UserProfile:
    """Account information from the login/user endpoints."""

    user_id: int | None
    email: str = ""
    firstname: str = ""
    surname: str = ""
    language: str = ""
    role: str = ""
    temperature_unit: str = ""

    @classmethod
    def from_dict(cls, data: Any) -> UserProfile | None:
        """Parse a login/user response; None when the shape is not usable."""
        if not isinstance(data, dict) or not isinstance(data.get("userData"), dict):
            _LOGGER.debug("Skipping malformed user response: %r", data)
            return None
        user_data = data["userData"]
        return cls(
            user_id=_as_int(user_data.get("userId")),
            email=_as_str(user_data.get("email")),
            firstname=_as_str(user_data.get("firstname")),
            surname=_as_str(user_data.get("surname")),
            language=_as_str(data.get("lang")),
            role=_as_str(data.get("role")),
            temperature_unit=_as_str(data.get("temperatureUnit")),
        )


@dataclass
class Notification:
    """One notification (alarm, info, error) of the account."""

    notification_id: int
    subject: str = ""
    notification_type: str = ""
    unread: bool = False
    notification_date: str = ""
    facility_id: int | None = None
    facility_name: str = ""
    body: str = ""

    @classmethod
    def from_dict(cls, data: Any) -> Notification | None:
        """Parse one notification object; None when the shape is not usable."""
        if not isinstance(data, dict):
            return None
        notification_id = _as_int(data.get("id"))
        if notification_id is None:
            _LOGGER.debug("Skipping malformed notification object: %r", data)
            return None
        return cls(
            notification_id=notification_id,
            subject=_as_str(data.get("subject")),
            notification_type=_as_str(data.get("notificationType")),
            unread=bool(data.get("unread", False)),
            notification_date=_as_str(data.get("notificationDate")),
            facility_id=_as_int(data.get("facilityId")),
            facility_name=_as_str(data.get("facilityName")),
            body=_as_str(data.get("body")),
        )


@dataclass
class OverviewValue:
    """One current value from an overview response, keyed by parameter name.

    Values stay raw (strings) here; the coordinator coerces them against the
    cached component schema.
    """

    raw_value: str
    display_name: str = ""
    unit: str = ""
    display_value: str = ""

    @classmethod
    def from_dict(cls, data: Any) -> OverviewValue | None:
        """Parse one value object; None when the shape is not usable."""
        if not isinstance(data, dict) or "value" not in data:
            return None
        return cls(
            raw_value=str(data["value"]),
            display_name=_as_str(data.get("displayName")),
            unit=_as_str(data.get("unit")),
            display_value=_as_str(data.get("displayValue")),
        )

    @property
    def value(self) -> float | str:
        """The value coerced numerically when possible, the raw string otherwise."""
        coerced = _as_float(self.raw_value)
        return self.raw_value if coerced is None else coerced


@dataclass
class OverviewComponent:
    """One component of an overview response with its current values."""

    component_id: str
    display_name: str
    component_number: int
    type: str
    sub_type: str = ""
    values: dict[str, OverviewValue] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Any) -> OverviewComponent | None:
        """Parse one overview component; None when the shape is not usable."""
        if not isinstance(data, dict) or not data.get("componentId"):
            _LOGGER.debug("Skipping malformed overview component: %r", data)
            return None
        overview_component = cls(
            component_id=str(data["componentId"]),
            display_name=_as_str(data.get("displayName")),
            component_number=_as_int(data.get("componentNumber"), 0) or 0,
            type=_as_str(data.get("type")),
            sub_type=_as_str(data.get("subType")),
        )
        for key, raw in data.items():
            if key in _RESERVED_OVERVIEW_KEYS:
                continue
            value = OverviewValue.from_dict(raw)
            if value is not None:
                overview_component.values[key] = value
            elif isinstance(raw, dict):
                _LOGGER.debug("Skipping unknown overview entry %r of %s", key, key)
        return overview_component


@dataclass
class FacilityOverview:
    """The whole-installation snapshot from the overview endpoint."""

    out_temp: OverviewValue | None = None
    components: dict[str, OverviewComponent] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Any) -> FacilityOverview | None:
        """Parse an overview response; None when the shape is not usable."""
        if not isinstance(data, dict):
            _LOGGER.debug("Skipping malformed overview response: %r", data)
            return None
        overview = cls(out_temp=OverviewValue.from_dict(data.get("outTemp")))
        components = data.get("components")
        if isinstance(components, list):
            for raw in components:
                component = OverviewComponent.from_dict(raw)
                if component is not None:
                    overview.components[component.component_id] = component
        return overview
