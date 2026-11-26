"""Sensor entity implementation for Variable config entries."""

from collections.abc import MutableMapping
import copy
import logging
from typing import Any

from homeassistant.components.sensor import CONF_STATE_CLASS, RestoreSensor
from homeassistant.components.sensor.const import UNIT_CONVERTERS
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_FRIENDLY_NAME,
    ATTR_ICON,
    CONF_DEVICE_CLASS,
    CONF_DEVICE_ID,
    CONF_ICON,
    CONF_NAME,
    CONF_UNIT_OF_MEASUREMENT,
    MATCH_ALL,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, device_registry as dr, entity_platform
from homeassistant.helpers.entity import generate_entity_id
from homeassistant.helpers.entity_platform import AddEntitiesCallback
import homeassistant.helpers.entity_registry as er
from homeassistant.util import slugify
import voluptuous as vol
import yaml

from .const import (
    ATTR_ATTRIBUTES,
    ATTR_NATIVE_UNIT_OF_MEASUREMENT,
    ATTR_REPLACE_ATTRIBUTES,
    ATTR_SUGGESTED_UNIT_OF_MEASUREMENT,
    ATTR_VALUE,
    ATTR_VALUE_DELTA,
    CONF_ATTRIBUTES,
    CONF_EXCLUDE_FROM_RECORDER,
    CONF_FORCE_UPDATE,
    CONF_RESTORE,
    CONF_UPDATED,
    CONF_VALUE,
    CONF_VALUE_TYPE,
    CONF_VARIABLE_ID,
    CONF_YAML_VARIABLE,
    DEFAULT_EXCLUDE_FROM_RECORDER,
    DEFAULT_REPLACE_ATTRIBUTES,
    DOMAIN,
    SERVICE_DECREMENT_SENSOR,
    SERVICE_INCREMENT_SENSOR,
)
from .helpers import merge_attribute_dict, value_to_type

_LOGGER = logging.getLogger(__name__)

PLATFORM = Platform.SENSOR
ENTITY_ID_FORMAT = PLATFORM + ".{}"

SERVICE_UPDATE_VARIABLE = "update_" + PLATFORM

VARIABLE_ATTR_SETTINGS = {
    ATTR_FRIENDLY_NAME: "_attr_name",
    ATTR_ICON: "_attr_icon",
    CONF_DEVICE_CLASS: "_attr_device_class",
    CONF_STATE_CLASS: "_attr_state_class",
    ATTR_NATIVE_UNIT_OF_MEASUREMENT: "_attr_native_unit_of_measurement",
    # YAML and update-service payloads use the public sensor attribute name.
    CONF_UNIT_OF_MEASUREMENT: "_attr_native_unit_of_measurement",
    ATTR_SUGGESTED_UNIT_OF_MEASUREMENT: "_attr_suggested_unit_of_measurement",
}

_MISSING_SENSOR_SENTINELS = frozenset({"", "none", "unknown", "unavailable"})
_UNIT_SETTINGS = frozenset(
    {
        "_attr_native_unit_of_measurement",
        "_attr_suggested_unit_of_measurement",
    }
)


def _is_missing_sensor_value(value: object) -> bool:
    """Return whether a restored or configured value represents absence.

    Args:
        value (object): Native value or unit to inspect.

    Returns:
        bool: True when the value is missing or a Home Assistant unavailable sentinel.
    """
    return value is None or (isinstance(value, str) and value.lower() in _MISSING_SENSOR_SENTINELS)


def _normalize_sensor_unit(value: object) -> str | None:
    """Return a unit string, or None for missing sentinels.

    Args:
        value (object): Configured, restored, or service-provided unit.

    Returns:
        str | None: The unit string, or ``None`` when the value is missing.
    """
    if _is_missing_sensor_value(value) or not isinstance(value, str):
        return None
    return value


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Instantiate and register a sensor entity for a config entry.

    Args:
        hass (HomeAssistant): Home Assistant instance hosting the integration.
        config_entry (ConfigEntry): Config entry that defines the variable.
        async_add_entities (AddEntitiesCallback): Callback that adds the created entity.
    """
    platform = entity_platform.async_get_current_platform()

    # HA aliases Voluptuous to Probatio at runtime, which mypy cannot see.
    platform.async_register_entity_service(
        SERVICE_UPDATE_VARIABLE,
        {
            vol.Optional(ATTR_VALUE): cv.match_all,  # type: ignore[dict-item, unused-ignore]
            vol.Optional(ATTR_ATTRIBUTES): dict,  # type: ignore[dict-item, unused-ignore]
            vol.Optional(ATTR_REPLACE_ATTRIBUTES, default=DEFAULT_REPLACE_ATTRIBUTES): cv.boolean,  # type: ignore[dict-item, unused-ignore]
        },
        "async_update_variable",
    )

    platform.async_register_entity_service(
        SERVICE_INCREMENT_SENSOR,
        {
            vol.Optional(ATTR_VALUE_DELTA, default=1): vol.Any(int, float),  # type: ignore[dict-item, unused-ignore]
        },
        "async_increment_variable",
    )

    platform.async_register_entity_service(
        SERVICE_DECREMENT_SENSOR,
        {
            vol.Optional(ATTR_VALUE_DELTA, default=1): vol.Any(int, float),  # type: ignore[dict-item, unused-ignore]
        },
        "async_decrement_variable",
    )

    config = hass.data.get(DOMAIN, {}).get(config_entry.entry_id, {})
    unique_id = config_entry.entry_id

    if config.get(CONF_EXCLUDE_FROM_RECORDER, DEFAULT_EXCLUDE_FROM_RECORDER):
        _LOGGER.debug(
            "(%s) Excluding from Recorder",
            config.get(CONF_NAME, config.get(CONF_VARIABLE_ID)),
        )
        async_add_entities([VariableNoRecorder(hass, config, config_entry, unique_id)])
    else:
        async_add_entities([Variable(hass, config, config_entry, unique_id)])


class Variable(RestoreSensor):
    """Home Assistant sensor entity backed by Variable configuration."""

    def __init__(
        self,
        hass: HomeAssistant,
        config: dict[str, Any],
        config_entry: ConfigEntry,
        unique_id: str,
    ) -> None:
        """Initialize sensor state and entity metadata from a config entry.

        Args:
            hass (HomeAssistant): Home Assistant instance hosting the entity.
            config (dict[str, Any]): Variable configuration fields.
            config_entry (ConfigEntry): Config entry that owns the entity.
            unique_id (str): Stable entity unique identifier.
        """
        self._hass = hass
        self._config = config
        self._config_entry = config_entry
        self._attr_has_entity_name = True
        self._variable_id = slugify(str(config.get(CONF_VARIABLE_ID, "")).lower())
        self._attr_unique_id = unique_id
        self._attr_name = config.get(CONF_NAME, config.get(CONF_VARIABLE_ID, ""))
        registry = er.async_get(self._hass)
        current_entity_id = registry.async_get_entity_id(DOMAIN, PLATFORM, self._attr_unique_id)
        if current_entity_id is not None:
            self.entity_id = current_entity_id
        else:
            self.entity_id = generate_entity_id(
                ENTITY_ID_FORMAT, self._variable_id, hass=self._hass
            )
        _LOGGER.debug("(%s) [init] entity_id: %s", self._attr_name, self.entity_id)

        self._attr_icon = config.get(CONF_ICON)
        self._restore = config.get(CONF_RESTORE)
        self._force_update = config.get(CONF_FORCE_UPDATE)
        self._yaml_variable = config.get(CONF_YAML_VARIABLE)
        self._exclude_from_recorder = config.get(CONF_EXCLUDE_FROM_RECORDER)
        self._value_type = config.get(CONF_VALUE_TYPE)
        self._attr_device_class = config.get(CONF_DEVICE_CLASS)
        self._attr_native_unit_of_measurement = _normalize_sensor_unit(
            config.get(CONF_UNIT_OF_MEASUREMENT)
        )
        self._attr_suggested_unit_of_measurement = None
        self._attr_state_class = config.get(CONF_STATE_CLASS)
        if (device_id := config.get(CONF_DEVICE_ID)) is not None:
            self.device_entry = dr.async_get(hass).async_get(device_id)
        if (
            config.get(CONF_ATTRIBUTES) is not None
            and config.get(CONF_ATTRIBUTES)
            and isinstance(config.get(CONF_ATTRIBUTES), MutableMapping)
        ):
            self._attr_extra_state_attributes = self._update_attr_settings(
                config.get(CONF_ATTRIBUTES)
            )
        else:
            self._attr_extra_state_attributes = {}
        configured_value = config.get(CONF_VALUE)
        if configured_value is None or (
            isinstance(configured_value, str)
            and configured_value.lower() in ["", "none", "unknown", "unavailable"]
        ):
            self._attr_native_value = None
        else:
            try:
                self._attr_native_value = value_to_type(configured_value, self._value_type)
            except ValueError:
                self._attr_native_value = None
        if self._attr_device_class in UNIT_CONVERTERS:
            self._attr_suggested_unit_of_measurement = self._attr_native_unit_of_measurement

    async def async_added_to_hass(self) -> None:
        """Restore saved sensor state and attributes when configured."""
        await super().async_added_to_hass()
        if self._restore is True:
            _LOGGER.info("(%s) Restoring after Reboot", self._attr_name)
            sensor = await self.async_get_last_sensor_data()
            if sensor and hasattr(sensor, "native_value"):
                restored_unit = _normalize_sensor_unit(
                    getattr(sensor, "native_unit_of_measurement", None)
                )
                self._attr_native_unit_of_measurement = restored_unit
                if restored_unit is not None and self._attr_device_class in UNIT_CONVERTERS:
                    self._attr_suggested_unit_of_measurement = restored_unit
                if _is_missing_sensor_value(sensor.native_value):
                    self._attr_native_value = None
                else:
                    try:
                        self._attr_native_value = value_to_type(
                            sensor.native_value, self._value_type
                        )
                    except ValueError:
                        self._attr_native_value = None

            state = await self.async_get_last_state()
            if (
                state
                and hasattr(state, CONF_ATTRIBUTES)
                and state.attributes
                and isinstance(state.attributes, MutableMapping)
            ):
                # Don't restore Home Assistant's computed friendly_name into
                # _attr_name. When linked to a device, friendly_name may already
                # be prefixed with the device name, which would otherwise lead to
                # name duplication across reboots.
                restored_attributes = dict(state.attributes)
                restored_attributes.pop(ATTR_FRIENDLY_NAME, None)
                # Last state exposes the display unit. Native unit is restored
                # separately from RestoreSensor extra data and must not be
                # overwritten by a converted unit_of_measurement.
                restored_attributes.pop(CONF_UNIT_OF_MEASUREMENT, None)
                self._attr_extra_state_attributes = self._update_attr_settings(
                    restored_attributes,
                    just_pop=self._config.get(CONF_UPDATED, False),
                )
                if self._config.get(CONF_UPDATED, True):
                    self._attr_extra_state_attributes.pop(CONF_UNIT_OF_MEASUREMENT, None)
                if (device := self.device_entry) is not None:
                    # Ensure static checker and runtime know _attr_name is a string.
                    # Avoid `assert` (flagged by bandit) and coerce to empty
                    # string if it's unexpectedly None or not a str.
                    if not isinstance(self._attr_name, str):
                        self._attr_name = ""
                    # Safely access device name(s) to satisfy type checks
                    device_name = getattr(device, "name", None)
                    device_name_by_user = getattr(device, "name_by_user", None)
                    if (
                        isinstance(device_name, str)
                        and isinstance(self._attr_name, str)
                        and self._attr_name.lower().strip() != device_name.lower().strip()
                        and self._attr_name.lower().startswith(device_name.lower())
                    ):
                        old_name = self._attr_name
                        self._attr_name = self._attr_name.replace(device_name, "", 1).strip()
                        _LOGGER.debug("(%s) [restored] Truncated: %s", self._attr_name, old_name)
                    elif (
                        isinstance(device_name_by_user, str)
                        and isinstance(self._attr_name, str)
                        and self._attr_name.lower().strip() != device_name_by_user.lower().strip()
                        and self._attr_name.lower().startswith(device_name_by_user.lower())
                    ):
                        old_name = self._attr_name
                        self._attr_name = self._attr_name.replace(
                            device_name_by_user, "", 1
                        ).strip()
                        _LOGGER.debug("(%s) [restored] Truncated: %s", self._attr_name, old_name)
            _LOGGER.debug(
                "(%s) [restored] _attr_native_value: %s",
                self._attr_name,
                self._attr_native_value,
            )
            _LOGGER.debug(
                "(%s) [restored] attributes: %s",
                self._attr_name,
                getattr(self, "_attr_extra_state_attributes", {}),
            )
            # If there were no attributes restored from state, apply attributes from config
            if (
                not getattr(self, "_attr_extra_state_attributes", None)
                or self._attr_extra_state_attributes == {}
            ) and self._config.get(CONF_ATTRIBUTES):
                # Last sensor extra data already restored native unit. Re-applying
                # configured special attributes would overwrite that restored unit.
                self._attr_extra_state_attributes = self._update_attr_settings(
                    self._config.get(CONF_ATTRIBUTES),
                    just_pop=sensor is not None,
                )
                _LOGGER.debug(
                    "(%s) [restored] applied config attributes: %s",
                    self._attr_name,
                    self._attr_extra_state_attributes,
                )
                try:
                    self.async_write_ha_state()
                except RuntimeError as err:
                    _LOGGER.debug(
                        "(%s) async_write_ha_state failed during restore: %s",
                        self._attr_name,
                        err,
                    )
        self._apply_missing_native_unit_from_config()
        if self._config.get(CONF_UPDATED, True):
            self._config.update({CONF_UPDATED: False})
            self._hass.config_entries.async_update_entry(
                self._config_entry,
                data=self._config,
                options={},
            )
            _LOGGER.debug(
                "(%s) Updated config_updated: %s",
                self._attr_name,
                self._config_entry.data.get(CONF_UPDATED),
            )

    def _apply_missing_native_unit_from_config(self) -> None:
        """Fill a missing native unit from configured sensor unit attributes.

        RestoreSensor extra data can restore ``None`` for YAML variables that
        previously stored ``unit_of_measurement`` only as a custom attribute.
        """
        extra_attributes = self._attr_extra_state_attributes
        if not _is_missing_sensor_value(self._attr_native_unit_of_measurement):
            if isinstance(extra_attributes, MutableMapping):
                extra_attributes.pop(CONF_UNIT_OF_MEASUREMENT, None)
            return

        attributes = self._config.get(CONF_ATTRIBUTES)
        unit = None
        if isinstance(attributes, MutableMapping):
            unit = attributes.get(CONF_UNIT_OF_MEASUREMENT)
            if unit is None:
                unit = attributes.get(ATTR_NATIVE_UNIT_OF_MEASUREMENT)
        if unit is None:
            unit = self._config.get(CONF_UNIT_OF_MEASUREMENT)
        if _is_missing_sensor_value(unit):
            self._attr_native_unit_of_measurement = None
            return

        self._attr_native_unit_of_measurement = _normalize_sensor_unit(unit)
        if isinstance(extra_attributes, MutableMapping):
            extra_attributes.pop(CONF_UNIT_OF_MEASUREMENT, None)
        if self._attr_device_class in UNIT_CONVERTERS:
            self._attr_suggested_unit_of_measurement = self._attr_native_unit_of_measurement

    @property
    def should_poll(self) -> bool:
        """Disable polling because services and reloads push updates.

        Returns:
            bool: False because updates are pushed by services and config entry reloads.
        """
        return False

    @property
    def force_update(self) -> bool:
        """Report whether state writes should fire force-update events.

        Returns:
            bool: Whether the configured force-update option is enabled.
        """
        return bool(self._force_update)

    def _update_attr_settings(self, new_attributes: Any = None, just_pop: bool = False) -> Any:
        """Apply special entity settings and return unconsumed attributes.

        Args:
            new_attributes (Any): Dynamic attribute payload to process.
            just_pop (bool): Remove special attributes without applying their values.

        Returns:
            Any: A copy of the remaining attributes, the unsupported input unchanged,
            or ``None`` when no attributes were provided.
        """
        if new_attributes is not None:
            _LOGGER.debug(
                "(%s) [update_attr_settings] Updating Special Attributes", self._attr_name
            )
            if isinstance(new_attributes, MutableMapping):
                attributes = copy.deepcopy(new_attributes)
                for attrib, setting in VARIABLE_ATTR_SETTINGS.items():
                    if attrib in attributes:
                        if just_pop:
                            attributes.pop(attrib, None)
                        else:
                            value = attributes.pop(attrib, None)
                            if setting in _UNIT_SETTINGS:
                                value = _normalize_sensor_unit(value)
                            setattr(self, setting, value)
                return copy.deepcopy(attributes)
            _LOGGER.error(
                "(%s) AttributeError: Attributes must be a dictionary: %s",
                self._attr_name,
                new_attributes,
            )
            return new_attributes
        return None

    async def async_update_variable(self, **kwargs: Any) -> None:
        """Apply an update service payload to sensor state and attributes.

        Args:
            kwargs (Any): Payload containing the new value, attributes, and update flags.

        Raises:
            ValueError: If the supplied value is incompatible with the variable type.
        """
        _LOGGER.debug("(%s) [async_update_variable] kwargs: %s", self._attr_name, kwargs)

        updated_attributes = None

        replace_attributes = kwargs.get(ATTR_REPLACE_ATTRIBUTES, False)
        _LOGGER.debug(
            "(%s) [async_update_variable] Replace Attributes: %s",
            self._attr_name,
            replace_attributes,
        )

        if (
            not replace_attributes
            and hasattr(self, "_attr_extra_state_attributes")
            and self._attr_extra_state_attributes is not None
        ):
            updated_attributes = copy.deepcopy(self._attr_extra_state_attributes)

        attributes = kwargs.get(ATTR_ATTRIBUTES)
        if attributes is not None:
            if isinstance(attributes, str):
                try:
                    attributes = yaml.safe_load(attributes)
                except yaml.YAMLError as err:
                    _LOGGER.error(
                        "(%s) Failed to parse attributes string: %s", self._attr_name, err
                    )
                    attributes = None
            if isinstance(attributes, MutableMapping):
                _LOGGER.debug(
                    "(%s) [async_update_variable] New Attributes: %s",
                    self._attr_name,
                    attributes,
                )
                extra_attributes = self._update_attr_settings(attributes)
                if extra_attributes is not None:
                    try:
                        updated_attributes = merge_attribute_dict(
                            updated_attributes, extra_attributes
                        )
                    except ValueError as err:
                        _LOGGER.error(
                            "(%s) AttributeError: %s",
                            self._attr_name,
                            err,
                        )
            else:
                _LOGGER.error(
                    "(%s) AttributeError: Attributes must be a dictionary: %s",
                    self._attr_name,
                    attributes,
                )

        if ATTR_VALUE in kwargs:
            try:
                newval = value_to_type(kwargs.get(ATTR_VALUE), self._value_type)
            except ValueError as err:
                error = (
                    "The value entered is not compatible with the selected device_class: "
                    f"{self._attr_device_class}. Expected: {self._value_type}. "
                    f"Value: {kwargs.get(ATTR_VALUE)}"
                )
                raise ValueError(error) from err
            else:
                _LOGGER.debug("(%s) [async_update_variable] New Value: %s", self._attr_name, newval)
                self._attr_native_value = newval

        if updated_attributes is not None:
            self._attr_extra_state_attributes = copy.deepcopy(updated_attributes)
            _LOGGER.debug(
                "(%s) [async_update_variable] Final Attributes: %s",
                self._attr_name,
                updated_attributes,
            )
        else:
            self._attr_extra_state_attributes = {}

        _LOGGER.debug(
            "(%s) [updated] _attr_native_value: %s",
            self._attr_name,
            self._attr_native_value,
        )
        _LOGGER.debug(
            "(%s) [updated] attributes: %s",
            self._attr_name,
            self._attr_extra_state_attributes,
        )
        self.async_write_ha_state()

    async def async_increment_variable(self, **kwargs: Any) -> None:
        """Increase the numeric sensor value by the service delta.

        Args:
            kwargs (Any): Payload containing an optional increment amount.

        Raises:
            TypeError: If the current value is not numeric.
            ValueError: If the variable type or current string value is invalid.
        """
        value_delta = kwargs.get(ATTR_VALUE_DELTA, 1)
        _LOGGER.debug(
            "(%s) [async_increment_variable] Incrementing by: %s",
            self._attr_name,
            value_delta,
        )

        # Only allow increment for numeric types
        if self._value_type not in ["number", None]:
            _LOGGER.error(
                "(%s) Cannot increment non-numeric variable. Current type: %s",
                self._attr_name,
                self._value_type,
            )
            raise ValueError(
                f"Cannot increment non-numeric variable. Current type: {self._value_type}"
            )

        current_value = self._attr_native_value
        if current_value is None:
            current_value = 0

        try:
            # Convert current value to numeric if it's a string
            if isinstance(current_value, str):
                try:
                    current_value = float(current_value)
                except ValueError, TypeError:
                    _LOGGER.error(
                        "(%s) Cannot convert current value to number: %s",
                        self._attr_name,
                        current_value,
                    )
                    raise ValueError(
                        f"Cannot convert current value to number: {current_value}"
                    ) from None

            if isinstance(current_value, bool) or not isinstance(current_value, int | float):
                raise TypeError(
                    f"Cannot increment non-numeric value. Current value: {current_value}"
                )

            new_value = current_value + value_delta

            # Convert back to the appropriate type
            if isinstance(new_value, float) and new_value.is_integer():
                new_value = int(new_value)

            _LOGGER.debug(
                "(%s) [async_increment_variable] New Value: %s", self._attr_name, new_value
            )
            self._attr_native_value = new_value
            self.async_write_ha_state()

        except (ValueError, TypeError) as err:
            _LOGGER.error("(%s) Increment error: %s", self._attr_name, err)
            raise

    async def async_decrement_variable(self, **kwargs: Any) -> None:
        """Decrease the numeric sensor value by the service delta.

        Args:
            kwargs (Any): Payload containing an optional decrement amount.

        Raises:
            TypeError: If the current value is not numeric.
            ValueError: If the variable type or current string value is invalid.
        """
        value_delta = kwargs.get(ATTR_VALUE_DELTA, 1)
        _LOGGER.debug(
            "(%s) [async_decrement_variable] Decrementing by: %s",
            self._attr_name,
            value_delta,
        )

        # Only allow decrement for numeric types
        if self._value_type not in ["number", None]:
            _LOGGER.error(
                "(%s) Cannot decrement non-numeric variable. Current type: %s",
                self._attr_name,
                self._value_type,
            )
            raise ValueError(
                f"Cannot decrement non-numeric variable. Current type: {self._value_type}"
            )

        current_value = self._attr_native_value
        if current_value is None:
            current_value = 0

        try:
            # Convert current value to numeric if it's a string
            if isinstance(current_value, str):
                try:
                    current_value = float(current_value)
                except ValueError, TypeError:
                    _LOGGER.error(
                        "(%s) Cannot convert current value to number: %s",
                        self._attr_name,
                        current_value,
                    )
                    raise ValueError(
                        f"Cannot convert current value to number: {current_value}"
                    ) from None

            if isinstance(current_value, bool) or not isinstance(current_value, int | float):
                raise TypeError(
                    f"Cannot decrement non-numeric value. Current value: {current_value}"
                )

            new_value = current_value - value_delta

            # Convert back to the appropriate type
            if isinstance(new_value, float) and new_value.is_integer():
                new_value = int(new_value)

            _LOGGER.debug(
                "(%s) [async_decrement_variable] New Value: %s", self._attr_name, new_value
            )
            self._attr_native_value = new_value
            self.async_write_ha_state()

        except (ValueError, TypeError) as err:
            _LOGGER.error("(%s) Decrement error: %s", self._attr_name, err)
            raise


class VariableNoRecorder(Variable):
    """Sensor variable whose state attributes are not stored by Recorder."""

    _unrecorded_attributes = frozenset({MATCH_ALL})
