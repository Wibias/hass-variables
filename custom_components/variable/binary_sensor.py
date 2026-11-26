"""Binary-sensor entity implementation for Variable config entries."""

from collections.abc import MutableMapping
import copy
import logging
from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_FRIENDLY_NAME,
    ATTR_ICON,
    CONF_DEVICE_CLASS,
    CONF_DEVICE_ID,
    CONF_ICON,
    CONF_NAME,
    MATCH_ALL,
    STATE_OFF,
    STATE_ON,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
    entity_platform,
    selector,
)
from homeassistant.helpers.entity import generate_entity_id
from homeassistant.helpers.entity_platform import AddEntitiesCallback
import homeassistant.helpers.entity_registry as er
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import slugify
import voluptuous as vol
import yaml

from .const import (
    ATTR_ATTRIBUTES,
    ATTR_REPLACE_ATTRIBUTES,
    ATTR_VALUE,
    CONF_ATTRIBUTES,
    CONF_EXCLUDE_FROM_RECORDER,
    CONF_FORCE_UPDATE,
    CONF_RESTORE,
    CONF_UPDATED,
    CONF_VALUE,
    CONF_VARIABLE_ID,
    CONF_YAML_VARIABLE,
    DEFAULT_EXCLUDE_FROM_RECORDER,
    DEFAULT_REPLACE_ATTRIBUTES,
    DOMAIN,
)
from .helpers import merge_attribute_dict

_LOGGER = logging.getLogger(__name__)

PLATFORM = Platform.BINARY_SENSOR
ENTITY_ID_FORMAT = PLATFORM + ".{}"

SERVICE_UPDATE_VARIABLE = "update_" + PLATFORM
SERVICE_TOGGLE_VARIABLE = "toggle_" + PLATFORM

VARIABLE_ATTR_SETTINGS = {
    ATTR_FRIENDLY_NAME: "_attr_name",
    ATTR_ICON: "_attr_icon",
    CONF_DEVICE_CLASS: "_attr_device_class",
}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Instantiate and register a binary-sensor entity for a config entry.

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
            vol.Optional(CONF_VALUE): selector.SelectSelector(  # type: ignore[dict-item, unused-ignore]
                selector.SelectSelectorConfig(
                    options=["None", "true", "false"],
                    translation_key="boolean_options",
                    multiple=False,
                    custom_value=False,
                    mode=selector.SelectSelectorMode.LIST,
                )
            ),
            vol.Optional(ATTR_ATTRIBUTES): dict,  # type: ignore[dict-item, unused-ignore]
            vol.Optional(ATTR_REPLACE_ATTRIBUTES, default=DEFAULT_REPLACE_ATTRIBUTES): cv.boolean,  # type: ignore[dict-item, unused-ignore]
        },
        "async_update_variable",
    )

    platform.async_register_entity_service(
        SERVICE_TOGGLE_VARIABLE,
        {
            vol.Optional(ATTR_ATTRIBUTES): dict,  # type: ignore[dict-item, unused-ignore]
            vol.Optional(ATTR_REPLACE_ATTRIBUTES, default=DEFAULT_REPLACE_ATTRIBUTES): cv.boolean,  # type: ignore[dict-item, unused-ignore]
        },
        "async_toggle_variable",
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


class Variable(BinarySensorEntity, RestoreEntity):
    """Home Assistant binary-sensor entity backed by Variable configuration."""

    def __init__(
        self,
        hass: HomeAssistant,
        config: dict[str, Any],
        config_entry: ConfigEntry,
        unique_id: str,
    ) -> None:
        """Initialize binary state and entity metadata from a config entry.

        Args:
            hass (HomeAssistant): Home Assistant instance hosting the entity.
            config (dict[str, Any]): Variable configuration fields.
            config_entry (ConfigEntry): Config entry that owns the entity.
            unique_id (str): Stable entity unique identifier.
        """
        configured_value = config.get(CONF_VALUE)
        if configured_value is None or (
            isinstance(configured_value, str)
            and configured_value.lower() in ["", "none", "unknown", "unavailable"]
        ):
            self._attr_is_on = None
        elif isinstance(configured_value, str):
            if configured_value.lower() in ["true", "1", "t", "y", "yes", "on"]:
                self._attr_is_on = True
            else:
                self._attr_is_on = False
        else:
            self._attr_is_on = configured_value
        self._hass = hass
        self._config = config
        self._config_entry = config_entry
        self._attr_has_entity_name = True
        variable_id = str(config.get(CONF_VARIABLE_ID, ""))
        self._variable_id = slugify(variable_id.lower())
        self._attr_unique_id = unique_id
        self._attr_name = config.get(CONF_NAME, config.get(CONF_VARIABLE_ID, ""))
        self._attr_icon = config.get(CONF_ICON)
        self._attr_device_class = config.get(CONF_DEVICE_CLASS)
        self._restore = config.get(CONF_RESTORE)
        self._force_update = bool(config.get(CONF_FORCE_UPDATE))
        self._yaml_variable = config.get(CONF_YAML_VARIABLE)
        self._exclude_from_recorder = config.get(CONF_EXCLUDE_FROM_RECORDER)
        if (device_id := config.get(CONF_DEVICE_ID)) is not None:
            self.device_entry = dr.async_get(hass).async_get(device_id)
        if (
            config.get(CONF_ATTRIBUTES) is not None
            and config.get(CONF_ATTRIBUTES)
            and isinstance(config.get(CONF_ATTRIBUTES), MutableMapping)
        ):
            attributes = config.get(CONF_ATTRIBUTES)
            _LOGGER.debug(
                "(%s) [init] config attributes: %s (type: %s)",
                config.get(CONF_NAME, config.get(CONF_VARIABLE_ID)),
                attributes,
                type(attributes),
            )
            self._attr_extra_state_attributes = self._update_attr_settings(attributes) or {}
        else:
            self._attr_extra_state_attributes = {}
        registry = er.async_get(self._hass)
        current_entity_id = registry.async_get_entity_id(DOMAIN, PLATFORM, self._attr_unique_id)
        if current_entity_id is not None:
            self.entity_id = current_entity_id
        else:
            self.entity_id = generate_entity_id(
                ENTITY_ID_FORMAT, self._variable_id, hass=self._hass
            )
        _LOGGER.debug("(%s) [init] entity_id: %s", self._attr_name, self.entity_id)

    async def async_added_to_hass(self) -> None:
        """Restore saved binary state and attributes when configured."""
        await super().async_added_to_hass()
        _LOGGER.debug("(%s) [async_added_to_hass] config at add: %s", self._attr_name, self._config)
        if self._restore is True:
            _LOGGER.info("(%s) Restoring after Reboot", self._attr_name)
            state = await self.async_get_last_state()
            if state:
                if (
                    hasattr(state, "attributes")
                    and state.attributes
                    and isinstance(state.attributes, MutableMapping)
                ):
                    # Never restore Home Assistant's computed friendly_name back into
                    # _attr_name. When the entity is linked to a device and
                    # _attr_has_entity_name is True, Home Assistant prefixes the
                    # device name when generating friendly_name; restoring that value
                    # would cause the device name to be duplicated on every reboot.
                    restored_attributes = dict(state.attributes)
                    restored_attributes.pop(ATTR_FRIENDLY_NAME, None)
                    self._attr_extra_state_attributes = (
                        self._update_attr_settings(
                            restored_attributes,
                            just_pop=self._config.get(CONF_UPDATED, False),
                        )
                        or {}
                    )
                if hasattr(state, "state"):
                    if state.state is None or (
                        isinstance(state.state, str)
                        and state.state.lower() in ["", "none", "unknown", "unavailable"]
                    ):
                        self._attr_is_on = None
                    elif state.state == STATE_OFF:
                        self._attr_is_on = False
                    elif state.state == STATE_ON:
                        self._attr_is_on = True
                    elif isinstance(state.state, bool):
                        self._attr_is_on = state.state
                    else:
                        self._attr_is_on = None
                else:
                    self._attr_is_on = None
            _LOGGER.debug("(%s) [restored] _attr_is_on: %s", self._attr_name, self._attr_is_on)
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
                self._attr_extra_state_attributes = (
                    self._update_attr_settings(self._config.get(CONF_ATTRIBUTES)) or {}
                )
                _LOGGER.debug(
                    "(%s) [restored] applied config attributes: %s",
                    self._attr_name,
                    getattr(self, "_attr_extra_state_attributes", {}),
                )
            try:
                self.async_write_ha_state()
            except (RuntimeError, ValueError) as err:
                _LOGGER.debug(
                    "(%s) async_write_ha_state failed during restore: %s",
                    self._attr_name,
                    err,
                )
        else:
            # If not restoring from state, ensure config-provided attributes are applied
            if (
                not getattr(self, "_attr_extra_state_attributes", None)
                or self._attr_extra_state_attributes == {}
            ) and self._config.get(CONF_ATTRIBUTES):
                self._attr_extra_state_attributes = (
                    self._update_attr_settings(self._config.get(CONF_ATTRIBUTES)) or {}
                )
                _LOGGER.debug(
                    "(%s) [added] applied config attributes: %s",
                    self._attr_name,
                    getattr(self, "_attr_extra_state_attributes", {}),
                )
            try:
                self.async_write_ha_state()
            except (RuntimeError, ValueError) as err:
                _LOGGER.debug(
                    "(%s) async_write_ha_state failed during add: %s",
                    self._attr_name,
                    err,
                )
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
        return self._force_update

    def _update_attr_settings(
        self, new_attributes: Any = None, just_pop: bool = False
    ) -> dict[str, Any] | None:
        """Apply special entity settings and return unconsumed attributes.

        Args:
            new_attributes (Any): Dynamic attribute payload to process.
            just_pop (bool): Remove special attributes without applying their values.

        Returns:
            dict[str, Any] | None: A copy of the remaining attributes or ``None`` when no supported
            attributes were provided.
        """
        if new_attributes is not None:
            _LOGGER.debug(
                "(%s) [update_attr_settings] updating special attributes; incoming: %s (type: %s)",
                self._attr_name,
                new_attributes,
                type(new_attributes),
            )
            if isinstance(new_attributes, MutableMapping):
                attributes = dict(copy.deepcopy(new_attributes))
                _LOGGER.debug(
                    "(%s) [update_attr_settings] copied attributes: %s",
                    self._attr_name,
                    attributes,
                )
                for attrib, setting in VARIABLE_ATTR_SETTINGS.items():
                    if attrib in attributes:
                        if just_pop:
                            attributes.pop(attrib, None)
                        else:
                            setattr(self, setting, attributes.pop(attrib, None))
                _LOGGER.debug(
                    "(%s) [update_attr_settings] result attributes: %s",
                    self._attr_name,
                    attributes,
                )
                return copy.deepcopy(attributes)
            _LOGGER.error(
                "(%s) AttributeError: Attributes must be a dictionary: %s",
                self._attr_name,
                new_attributes,
            )
            return None
        return None

    async def async_update_variable(self, **kwargs: Any) -> None:
        """Apply an update service payload to binary state and attributes.

        Args:
            kwargs (Any): Payload containing the new value, attributes, and update flags.
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

        if updated_attributes is not None:
            self._attr_extra_state_attributes = copy.deepcopy(updated_attributes)
            _LOGGER.debug(
                "(%s) [async_update_variable] Final Attributes: %s",
                self._attr_name,
                updated_attributes,
            )
        else:
            self._attr_extra_state_attributes = {}

        if ATTR_VALUE in kwargs:
            val = kwargs.get(ATTR_VALUE)
            if val is None or (
                isinstance(val, str) and val.lower() in ["", "none", "unknown", "unavailable"]
            ):
                self._attr_is_on = None
            elif isinstance(val, str):
                if val.lower() in ["true", "1", "t", "y", "yes", "on"]:
                    self._attr_is_on = True
                else:
                    self._attr_is_on = False
            else:
                self._attr_is_on = val
            _LOGGER.debug(
                "(%s) [async_update_variable] New Value: %s",
                self._attr_name,
                self._attr_is_on,
            )

        self.async_write_ha_state()

    async def async_toggle_variable(self, **kwargs: Any) -> None:
        """Apply a toggle service payload to binary state and attributes.

        Args:
            kwargs (Any): Payload containing attributes and toggle-specific update flags.
        """
        _LOGGER.debug("(%s) [async_toggle_variable] kwargs: %s", self._attr_name, kwargs)

        updated_attributes = None

        replace_attributes = kwargs.get(ATTR_REPLACE_ATTRIBUTES, False)
        _LOGGER.debug(
            "(%s) [async_toggle_variable] Replace Attributes: %s",
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
                    "(%s) [async_toggle_variable] New Attributes: %s",
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

        if updated_attributes is not None:
            self._attr_extra_state_attributes = copy.deepcopy(updated_attributes)
            _LOGGER.debug(
                "(%s) [async_toggle_variable] Final Attributes: %s",
                self._attr_name,
                updated_attributes,
            )
        else:
            self._attr_extra_state_attributes = {}

        if self._attr_is_on is not None:
            self._attr_is_on = not self._attr_is_on
        _LOGGER.debug(
            "(%s) [async_toggle_variable] New Value: %s",
            self._attr_name,
            self._attr_is_on,
        )

        self.async_write_ha_state()


class VariableNoRecorder(Variable):
    """Binary sensor variable whose state attributes are not stored by Recorder."""

    _unrecorded_attributes = frozenset({MATCH_ALL})
