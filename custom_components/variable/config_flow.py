"""Menu-driven configuration and options flows for Variable entities."""

from __future__ import annotations

import datetime
import logging
import re
from typing import Any

from homeassistant.components import binary_sensor, sensor
from homeassistant.components.device_tracker.const import ATTR_LOCATION_NAME
from homeassistant.components.sensor.const import DEVICE_CLASS_UNITS
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import (
    ATTR_BATTERY_LEVEL,
    ATTR_GPS_ACCURACY,
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
    CONF_DEVICE,
    CONF_DEVICE_CLASS,
    CONF_DEVICE_ID,
    CONF_ENTITY_ID,
    CONF_ICON,
    CONF_NAME,
    CONF_UNIT_OF_MEASUREMENT,
    STATE_OFF,
    STATE_ON,
    Platform,
)
from homeassistant.core import HomeAssistant, State, callback
from homeassistant.helpers import config_validation as cv, entity_registry, selector
import homeassistant.util.dt as dt_util
from iso4217 import Currency
import voluptuous as vol

from .const import (
    ATTR_ATTRIBUTES,
    ATTR_DELETE_IN_ZONES,
    ATTR_DELETE_LOCATION_NAME,
    ATTR_IN_ZONES,
    ATTR_REPLACE_ATTRIBUTES,
    ATTR_VALUE,
    CONF_ATTRIBUTES,
    CONF_CLEAR_DEVICE_ID,
    CONF_CONFIGURATION_URL,
    CONF_ENTITY_PLATFORM,
    CONF_EXCLUDE_FROM_RECORDER,
    CONF_FORCE_UPDATE,
    CONF_HW_VERSION,
    CONF_MANUFACTURER,
    CONF_MODEL,
    CONF_MODEL_ID,
    CONF_RESTORE,
    CONF_SERIAL_NUMBER,
    CONF_SW_VERSION,
    CONF_TZOFFSET,
    CONF_UPDATED,
    CONF_VALUE,
    CONF_VALUE_TYPE,
    CONF_VARIABLE_ID,
    CONF_YAML_PRESENT,
    CONF_YAML_VARIABLE,
    DEFAULT_EXCLUDE_FROM_RECORDER,
    DEFAULT_FORCE_UPDATE,
    DEFAULT_ICON,
    DEFAULT_RESTORE,
    DOMAIN,
    PLATFORMS,
    SERVICE_UPDATE_BINARY_SENSOR,
    SERVICE_UPDATE_DEVICE_TRACKER,
    SERVICE_UPDATE_SENSOR,
)
from .device import update_device
from .helpers import value_to_type


def _normalize_sensor_device_class(
    device_class: sensor.SensorDeviceClass | str | None,
) -> sensor.SensorDeviceClass | None:
    """Normalize a sensor device class supplied as an enum, value, or name.

    Args:
        device_class (sensor.SensorDeviceClass | str | None): Device class enum or
            selector value to normalize.

    Returns:
        sensor.SensorDeviceClass | None: The matching sensor device class, or
            ``None`` when it is absent or invalid.
    """
    if isinstance(device_class, sensor.SensorDeviceClass):
        return device_class
    if not isinstance(device_class, str) or device_class.lower() == "none":
        return None
    return next(
        (
            member
            for member in sensor.SensorDeviceClass
            if device_class in (member.value, member.name)
        ),
        None,
    )


def _sensor_unit_options(
    device_class: sensor.SensorDeviceClass,
) -> list[selector.SelectOptionDict]:
    """Build unit selector options for a normalized sensor device class.

    Args:
        device_class (sensor.SensorDeviceClass): Normalized sensor device class that
            determines valid units.

    Returns:
        list[selector.SelectOptionDict]: Selector options for units supported by the device class.
    """
    if device_class == sensor.SensorDeviceClass.MONETARY:
        return [
            selector.SelectOptionDict(
                label=f"{currency.currency_name} [{currency.code}]",
                value=str(currency.code),
            )
            for currency in Currency
            if currency.code not in ["XTS", "XXX"]
        ]
    units = (
        unit
        for unit in DEVICE_CLASS_UNITS.get(device_class, set())
        if unit is not None and unit != "None"
    )
    return [
        selector.SelectOptionDict(label=str(unit), value=str(unit))
        for unit in sorted(units, key=str)
    ]


_LOGGER = logging.getLogger(__name__)

COMPONENT_CONFIG_URL = "https://github.com/Wibias/hass-variables"

# Note the input displayed to the user will be translated. See the
# translations/<lang>.json file. See here for further information:
# https://developers.home-assistant.io/docs/config_entries_config_flow_handler/#translations

SENSOR_DEVICE_CLASS_SELECT_LIST = []
SENSOR_DEVICE_CLASS_SELECT_LIST.append(selector.SelectOptionDict(label="None", value="None"))
SENSOR_DEVICE_CLASS_SELECT_LIST.extend(
    selector.SelectOptionDict(
        label=str(sensor_device_class.name), value=str(sensor_device_class.value)
    )
    for sensor_device_class in sensor.SensorDeviceClass
    if sensor_device_class != sensor.SensorDeviceClass.ENUM
)

BINARY_SENSOR_DEVICE_CLASS_SELECT_LIST = []
BINARY_SENSOR_DEVICE_CLASS_SELECT_LIST.append(selector.SelectOptionDict(label="None", value="None"))
BINARY_SENSOR_DEVICE_CLASS_SELECT_LIST.extend(
    selector.SelectOptionDict(
        label=str(binary_sensor_device_class.name),
        value=str(binary_sensor_device_class.value),
    )
    for binary_sensor_device_class in binary_sensor.BinarySensorDeviceClass
)

ADD_SENSOR_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_VARIABLE_ID): cv.string,
        vol.Optional(CONF_NAME): cv.string,
        vol.Optional(CONF_ICON, default=DEFAULT_ICON): selector.IconSelector(
            selector.IconSelectorConfig()
        ),
        vol.Optional(CONF_DEVICE_CLASS): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=SENSOR_DEVICE_CLASS_SELECT_LIST,
                multiple=False,
                custom_value=False,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Optional(CONF_DEVICE_ID): selector.DeviceSelector(selector.DeviceSelectorConfig()),
        vol.Optional(CONF_RESTORE, default=DEFAULT_RESTORE): selector.BooleanSelector(
            selector.BooleanSelectorConfig()
        ),
        vol.Optional(CONF_FORCE_UPDATE, default=DEFAULT_FORCE_UPDATE): selector.BooleanSelector(
            selector.BooleanSelectorConfig()
        ),
        vol.Optional(
            CONF_EXCLUDE_FROM_RECORDER, default=DEFAULT_EXCLUDE_FROM_RECORDER
        ): selector.BooleanSelector(selector.BooleanSelectorConfig()),
    }
)

ADD_BINARY_SENSOR_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_VARIABLE_ID): cv.string,
        vol.Optional(CONF_NAME): cv.string,
        vol.Optional(CONF_ICON, default=DEFAULT_ICON): selector.IconSelector(
            selector.IconSelectorConfig()
        ),
        vol.Optional(CONF_VALUE, default="None"): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=["None", "true", "false"],
                translation_key="boolean_options",
                multiple=False,
                custom_value=False,
                mode=selector.SelectSelectorMode.LIST,
            )
        ),
        vol.Optional(CONF_ATTRIBUTES): selector.ObjectSelector(selector.ObjectSelectorConfig()),
        vol.Optional(CONF_DEVICE_CLASS): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=BINARY_SENSOR_DEVICE_CLASS_SELECT_LIST,
                multiple=False,
                custom_value=False,
                mode=selector.SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Optional(CONF_DEVICE_ID): selector.DeviceSelector(selector.DeviceSelectorConfig()),
        vol.Optional(CONF_RESTORE, default=DEFAULT_RESTORE): selector.BooleanSelector(
            selector.BooleanSelectorConfig()
        ),
        vol.Optional(CONF_FORCE_UPDATE, default=DEFAULT_FORCE_UPDATE): selector.BooleanSelector(
            selector.BooleanSelectorConfig()
        ),
        vol.Optional(
            CONF_EXCLUDE_FROM_RECORDER, default=DEFAULT_EXCLUDE_FROM_RECORDER
        ): selector.BooleanSelector(selector.BooleanSelectorConfig()),
    }
)

ADD_DEVICE_TRACKER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_VARIABLE_ID): cv.string,
        vol.Optional(CONF_NAME): cv.string,
        vol.Optional(CONF_ICON, default=DEFAULT_ICON): selector.IconSelector(
            selector.IconSelectorConfig()
        ),
        vol.Required(ATTR_LATITUDE, default=""): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=-90,
                max=90,
                step="any",
                unit_of_measurement="°",
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
        vol.Required(ATTR_LONGITUDE, default=""): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=-180,
                max=180,
                step="any",
                unit_of_measurement="°",
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
        vol.Optional(ATTR_LOCATION_NAME): cv.string,
        vol.Optional(ATTR_GPS_ACCURACY): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0,
                max=1000000,
                step=1,
                unit_of_measurement="m",
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
        vol.Optional(ATTR_BATTERY_LEVEL): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0,
                max=100,
                step=1,
                unit_of_measurement="%",
                mode=selector.NumberSelectorMode.BOX,
            )
        ),
        vol.Optional(CONF_ATTRIBUTES): selector.ObjectSelector(selector.ObjectSelectorConfig()),
        vol.Optional(CONF_DEVICE_ID): selector.DeviceSelector(selector.DeviceSelectorConfig()),
        vol.Optional(CONF_RESTORE, default=DEFAULT_RESTORE): selector.BooleanSelector(
            selector.BooleanSelectorConfig()
        ),
        vol.Optional(CONF_FORCE_UPDATE, default=DEFAULT_FORCE_UPDATE): selector.BooleanSelector(
            selector.BooleanSelectorConfig()
        ),
        vol.Optional(
            CONF_EXCLUDE_FROM_RECORDER, default=DEFAULT_EXCLUDE_FROM_RECORDER
        ): selector.BooleanSelector(selector.BooleanSelectorConfig()),
    }
)

ADD_DEVICE_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_NAME): cv.string,
        vol.Optional(CONF_CONFIGURATION_URL): cv.string,
        vol.Optional(CONF_MANUFACTURER): cv.string,
        vol.Optional(CONF_HW_VERSION): cv.string,
        vol.Optional(CONF_MODEL): cv.string,
        vol.Optional(CONF_MODEL_ID): cv.string,
        vol.Optional(CONF_SERIAL_NUMBER): cv.string,
        vol.Optional(CONF_SW_VERSION): cv.string,
    }
)


async def validate_sensor_input(hass: HomeAssistant, data: dict) -> dict[str, str]:
    """Derive a config-entry title from submitted Variable fields.

    Args:
        hass (HomeAssistant): Home Assistant instance hosting the configuration flow.
        data (dict): Submitted sensor configuration fields.

    Returns:
        dict[str, str]: Config-entry metadata containing the derived title.
    """
    title = data.get(CONF_NAME) or data.get(CONF_VARIABLE_ID, "")
    return {"title": title if isinstance(title, str) else ""}


class VariableConfigFlow(ConfigFlow, domain=DOMAIN):
    """Create Variable config entries through menu-driven forms."""

    VERSION = 1
    # Connection classes in homeassistant/config_entries.py are now deprecated

    async def async_step_user(self, user_input: dict | None = None) -> ConfigFlowResult:
        """Show the initial configuration-flow menu.

        Args:
            user_input (dict | None): Submitted data for the initial step, if any.

        Returns:
            ConfigFlowResult: The menu result for selecting a Variable helper type.
        """
        platforms_w_device: list = [*PLATFORMS, CONF_DEVICE]
        return self.async_show_menu(
            step_id="user",
            menu_options=["add_" + p for p in platforms_w_device],
        )

    async def async_step_add_sensor(
        self,
        user_input: dict | None = None,
        errors: dict | None = None,
        yaml_variable: bool = False,
    ) -> ConfigFlowResult:
        """Collect initial sensor settings and advance to typed details.

        Args:
            user_input (dict | None): Submitted sensor configuration fields, if any.
            errors (dict | None): Validation errors keyed by form field.
            yaml_variable (bool): Whether this flow imports a YAML-defined variable.

        Returns:
            ConfigFlowResult: The second sensor page after submission, or the first-page form.
        """
        errors = {} if errors is None else errors
        if user_input is not None:
            user_input.update({CONF_ENTITY_PLATFORM: Platform.SENSOR})
            user_input.update({CONF_YAML_VARIABLE: yaml_variable})
            if yaml_variable:
                user_input.update({CONF_YAML_PRESENT: True})
            _LOGGER.debug("[New Sensor Variable] page_1_input: %s", user_input)
            self.add_sensor_input = user_input
            return await self.async_step_sensor_page_2()

        # Show the form again, including any errors found with the input.
        return self.async_show_form(
            step_id="add_sensor",
            data_schema=ADD_SENSOR_SCHEMA,
            errors=errors,
            description_placeholders={
                "component_config_url": COMPONENT_CONFIG_URL,
            },
        )

    async def async_step_sensor_page_2(
        self, user_input: dict | None = None, errors: dict | None = None
    ) -> ConfigFlowResult:
        """Validate typed sensor settings and create a config entry.

        Args:
            user_input (dict | None): Submitted value and attribute fields, if any.
            errors (dict | None): Validation errors keyed by form field.

        Returns:
            ConfigFlowResult: A created sensor entry or the second-page form.
        """
        errors = {} if errors is None else errors
        if user_input is not None or self.add_sensor_input.get(CONF_YAML_VARIABLE) is True:
            _LOGGER.debug("[New Sensor Page 2] page_1_input: %s", self.add_sensor_input)
            _LOGGER.debug("[New Sensor Page 2] page_2_input: %s", user_input)

            if self.add_sensor_input.get(CONF_YAML_VARIABLE) is True:
                user_input = {}
                user_input.update({CONF_VALUE: self.add_sensor_input.get(CONF_VALUE)})
                yaml_value_type = self.yaml_import_get_value_type()
                self.add_sensor_input.update({CONF_VALUE_TYPE: yaml_value_type})
            # normalize user_input to dict to make .get/.update safe for type checkers
            user_input = user_input or {}
            val: Any = user_input.get(CONF_VALUE)
            if (
                val is not None
                and isinstance(val, str)
                and self.add_sensor_input.get(CONF_VALUE_TYPE) == "datetime"
            ):
                if (
                    user_input.get(CONF_TZOFFSET) is not None
                    and re.match(r"^[+-]?\d\d\:?\d\d\s*$", str(user_input.get(CONF_TZOFFSET)))
                    is not None
                ):
                    val = val + str(user_input.get(CONF_TZOFFSET))
                else:
                    val += "+0000"
            _LOGGER.debug("[New Sensor Page 2] val: %s", val)
            try:
                newval = value_to_type(
                    val,
                    self.add_sensor_input.get(CONF_VALUE_TYPE),
                )
            except ValueError:
                errors["base"] = "invalid_value_type"
                if self.add_sensor_input.get(CONF_YAML_VARIABLE) is True:
                    _LOGGER.error(
                        "The value is incompatible with the selected device class; "
                        "setting it to None"
                    )
                    self.add_sensor_input[CONF_VALUE] = None
                    user_input.update({CONF_VALUE: None})
            else:
                user_input.update({CONF_VALUE: newval})

            if not errors or self.add_sensor_input.get(CONF_YAML_VARIABLE) is True:
                if self.add_sensor_input is not None and self.add_sensor_input:
                    user_input.update(self.add_sensor_input)
                if user_input is not None:
                    for k, v in list(user_input.items()):
                        if v is None or (isinstance(v, str) and v.lower() == "none"):
                            user_input.pop(k, None)
                _LOGGER.debug("[New Sensor Page 2] Final user_input: %s", user_input)
                info = await validate_sensor_input(self.hass, user_input)
                return self.async_create_entry(title=info.get("title", ""), data=user_input)

        sensor_page_2_schema = self.build_add_sensor_page_2()

        if self.add_sensor_input.get(CONF_NAME) is None or self.add_sensor_input.get(
            CONF_NAME
        ) == self.add_sensor_input.get(CONF_VARIABLE_ID):
            disp_name = self.add_sensor_input.get(CONF_VARIABLE_ID)
        else:
            disp_name = (
                f"{self.add_sensor_input.get(CONF_NAME)} "
                f"({self.add_sensor_input.get(CONF_VARIABLE_ID)})"
            )
        # Show the form again, including any errors found with the input.
        return self.async_show_form(
            step_id="sensor_page_2",
            data_schema=sensor_page_2_schema,
            errors=errors,
            description_placeholders={
                "device_class": str(self.add_sensor_input.get(CONF_DEVICE_CLASS, "None")),
                "disp_name": str(disp_name),
                "value_type": str(self.add_sensor_input.get(CONF_VALUE_TYPE, "None")),
            },
        )

    def yaml_import_get_value_type(self) -> str | None:
        """Return the value type inferred from imported YAML attributes.

        Returns:
            str | None: The matching Variable value type, or ``None`` without a device class.
        """
        if self.add_sensor_input.get(CONF_ATTRIBUTES, {}).get(CONF_DEVICE_CLASS) is None:
            return None
        if (
            self.add_sensor_input.get(CONF_ATTRIBUTES, {}).get(CONF_DEVICE_CLASS)
            == sensor.SensorDeviceClass.DATE
        ):
            return "date"
        if (
            self.add_sensor_input.get(CONF_ATTRIBUTES, {}).get(CONF_DEVICE_CLASS)
            == sensor.SensorDeviceClass.TIMESTAMP
        ):
            return "datetime"
        if self.add_sensor_input.get(CONF_ATTRIBUTES, {}).get(CONF_DEVICE_CLASS) in (
            sensor.SensorDeviceClass.MONETARY,
            sensor.SensorDeviceClass.ENUM,
        ):
            return "string"
        return "number"

    def build_add_sensor_page_2(self) -> vol.Schema:
        """Build the schema for the second sensor configuration page.

        Returns:
            vol.Schema: Schema containing the fields compatible with the selected device class.
        """
        sensor_state_class_select_list = []
        sensor_state_class_select_list.append(selector.SelectOptionDict(label="None", value="None"))
        sensor_units_select_list = []
        sensor_units_select_list.append(selector.SelectOptionDict(label="None", value="None"))

        sensor_page_2_schema = vol.Schema({})
        if (
            self.add_sensor_input.get(CONF_DEVICE_CLASS) is not None
            and str(self.add_sensor_input.get(CONF_DEVICE_CLASS)).lower() != "none"
        ):
            normalized_device_class = _normalize_sensor_device_class(
                self.add_sensor_input.get(CONF_DEVICE_CLASS)
            )

            if normalized_device_class is None:
                classes: set[sensor.SensorStateClass] = set()
            else:
                classes = sensor.DEVICE_CLASS_STATE_CLASSES.get(normalized_device_class, set())
            sensor_state_class_select_list.extend(
                selector.SelectOptionDict(label=str(el.name), value=str(el.value)) for el in classes
            )
            if normalized_device_class is not None:
                sensor_units_select_list.extend(_sensor_unit_options(normalized_device_class))
            if normalized_device_class == sensor.SensorDeviceClass.DATE:
                sensor_page_2_schema = sensor_page_2_schema.extend(
                    {vol.Optional(CONF_VALUE): selector.DateSelector(selector.DateSelectorConfig())}
                )
                value_type = "date"
            elif normalized_device_class == sensor.SensorDeviceClass.TIMESTAMP:
                default_tzoffset = datetime.datetime.now(
                    dt_util.get_time_zone(self.hass.config.time_zone)
                ).strftime("%z")
                if default_tzoffset is None:
                    default_tzoffset = "+0000"
                _LOGGER.debug("default_tzoffset: %s", default_tzoffset)
                sensor_page_2_schema = sensor_page_2_schema.extend(
                    {
                        vol.Optional(CONF_VALUE): selector.DateTimeSelector(
                            selector.DateTimeSelectorConfig()
                        ),
                        vol.Optional(
                            CONF_TZOFFSET,
                            default=default_tzoffset,
                        ): selector.TextSelector(selector.TextSelectorConfig()),
                    }
                )
                value_type = "datetime"
            else:
                sensor_page_2_schema = sensor_page_2_schema.extend(
                    {vol.Optional(CONF_VALUE): selector.TextSelector(selector.TextSelectorConfig())}
                )
                value_type = "number"
        else:
            sensor_state_class_select_list.extend(
                selector.SelectOptionDict(label=str(el.name), value=str(el.value))
                for el in sensor.SensorStateClass
            )

            sensor_page_2_schema = sensor_page_2_schema.extend(
                {vol.Optional(CONF_VALUE): selector.TextSelector(selector.TextSelectorConfig())}
            )
            value_type = "string"

        sensor_page_2_schema = sensor_page_2_schema.extend(
            {
                vol.Optional(CONF_ATTRIBUTES): selector.ObjectSelector(
                    selector.ObjectSelectorConfig()
                )
            }
        )
        if len(sensor_state_class_select_list) > 1:
            sensor_page_2_schema = sensor_page_2_schema.extend(
                {
                    vol.Optional(sensor.CONF_STATE_CLASS): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=sensor_state_class_select_list,
                            multiple=False,
                            custom_value=False,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            )

        if len(sensor_units_select_list) > 1:
            sensor_page_2_schema = sensor_page_2_schema.extend(
                {
                    vol.Optional(CONF_UNIT_OF_MEASUREMENT): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=sensor_units_select_list,
                            multiple=False,
                            custom_value=False,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            )

        self.add_sensor_input.update({CONF_VALUE_TYPE: value_type})
        return sensor_page_2_schema

    async def async_step_add_binary_sensor(
        self,
        user_input: dict | None = None,
        errors: dict | None = None,
        yaml_variable: bool = False,
    ) -> ConfigFlowResult:
        """Create a binary-sensor entry or display its configuration form.

        Args:
            user_input (dict | None): Submitted binary-sensor configuration fields, if any.
            errors (dict | None): Validation errors keyed by form field.
            yaml_variable (bool): Whether this flow imports a YAML-defined variable.

        Returns:
            ConfigFlowResult: A created binary-sensor entry, or its configuration form.
        """
        errors = {} if errors is None else errors
        if user_input is not None:
            user_input.update({CONF_ENTITY_PLATFORM: Platform.BINARY_SENSOR})
            user_input.update({CONF_YAML_VARIABLE: yaml_variable})
            if yaml_variable:
                user_input.update({CONF_YAML_PRESENT: True})
            info = await validate_sensor_input(self.hass, user_input)
            _LOGGER.debug("[New Binary Sensor] updated user_input: %s", user_input)
            return self.async_create_entry(title=info.get("title", ""), data=user_input)

        # Show the form again, including any errors found with the input.
        return self.async_show_form(
            step_id="add_binary_sensor",
            data_schema=ADD_BINARY_SENSOR_SCHEMA,
            errors=errors,
            description_placeholders={
                "component_config_url": COMPONENT_CONFIG_URL,
            },
        )

    async def async_step_add_device_tracker(
        self,
        user_input: dict | None = None,
        errors: dict | None = None,
        yaml_variable: bool = False,
    ) -> ConfigFlowResult:
        """Create a device-tracker entry or display its configuration form.

        Args:
            user_input (dict | None): Submitted device-tracker configuration fields, if any.
            errors (dict | None): Validation errors keyed by form field.
            yaml_variable (bool): Whether this flow imports a YAML-defined variable.

        Returns:
            ConfigFlowResult: A created device-tracker entry, or its configuration form.
        """
        errors = {} if errors is None else errors
        if user_input is not None:
            user_input.update({CONF_ENTITY_PLATFORM: Platform.DEVICE_TRACKER})
            user_input.update({CONF_YAML_VARIABLE: yaml_variable})
            if yaml_variable:
                user_input.update({CONF_YAML_PRESENT: True})
            info = await validate_sensor_input(self.hass, user_input)
            _LOGGER.debug("[New Device Tracker] updated user_input: %s", user_input)
            return self.async_create_entry(title=info.get("title", ""), data=user_input)

        # Show the form again, including any errors found with the input.
        return self.async_show_form(
            step_id="add_device_tracker",
            data_schema=ADD_DEVICE_TRACKER_SCHEMA,
            errors=errors,
            description_placeholders={
                "component_config_url": COMPONENT_CONFIG_URL,
            },
        )

    async def async_step_add_device(
        self,
        user_input: dict | None = None,
        errors: dict | None = None,
        yaml_variable: bool = False,
    ) -> ConfigFlowResult:
        """Create a virtual-device entry or display its configuration form.

        Args:
            user_input (dict | None): Submitted device configuration fields, if any.
            errors (dict | None): Validation errors keyed by form field.
            yaml_variable (bool): Whether this flow imports a YAML-defined variable.

        Returns:
            ConfigFlowResult: A created virtual-device entry or its configuration form.
        """
        errors = {} if errors is None else errors
        if user_input is not None:
            try:
                user_input.update({CONF_ENTITY_PLATFORM: CONF_DEVICE})
                user_input.update({CONF_YAML_VARIABLE: yaml_variable})

                # Cannot use cv.url validation in the schema itself so apply
                # extra validation here
                if user_input.get(CONF_CONFIGURATION_URL, None):
                    cv.url(user_input.get(CONF_CONFIGURATION_URL))
                info = await validate_sensor_input(self.hass, user_input)
                _LOGGER.debug("[New Device] updated user_input: %s", user_input)
                return self.async_create_entry(title=info.get("title", ""), data=user_input)
            except vol.Invalid:
                errors["base"] = "invalid_url"

        # Show the form again, including any errors found with the input.
        return self.async_show_form(
            step_id="add_device",
            data_schema=ADD_DEVICE_SCHEMA,
            errors=errors,
            description_placeholders={
                "component_config_url": COMPONENT_CONFIG_URL,
            },
        )

    # this is run to import the configuration.yaml parameters\
    async def async_step_import(self, import_config: dict | None = None) -> ConfigFlowResult:
        """Create a YAML-backed sensor config entry.

        Args:
            import_config (dict | None): YAML-derived configuration fields, if any.

        Returns:
            ConfigFlowResult: A sensor creation result populated from YAML fields.
        """
        return await self.async_step_add_sensor(user_input=import_config, yaml_variable=True)

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> OptionsFlow:
        """Create the handler for an existing Variable entry's options.

        Args:
            config_entry (ConfigEntry): Config entry whose options are being managed.

        Returns:
            OptionsFlow: Handler for the entry's value updates and configuration changes.
        """
        return VariableOptionsFlowHandler()


class VariableOptionsFlowHandler(OptionsFlow):
    """Manage value updates and configuration changes for a Variable entry."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Route an entry to its supported options flow.

        Args:
            user_input (dict[str, Any] | None): Submitted data for the initial options step, if any.

        Returns:
            ConfigFlowResult: An options menu, a device form, or a YAML/unsupported-entry abort.
        """
        if self.config_entry.data.get(CONF_YAML_VARIABLE):
            _LOGGER.debug("[YAML] No Options for YAML Created Variables")
            return self.async_abort(reason="yaml_variable")

        if self.config_entry.data.get(CONF_ENTITY_PLATFORM) in PLATFORMS:
            platform = str(self.config_entry.data.get(CONF_ENTITY_PLATFORM, ""))
            change_value = "change_" + platform + "_value"
            change_options = platform + "_options"
            return self.async_show_menu(
                step_id="init",
                menu_options=[change_value, change_options],
            )
        if self.config_entry.data.get(CONF_ENTITY_PLATFORM) == CONF_DEVICE:
            return await self.async_step_device_options()
        return self.async_abort(reason="unknown")

    async def async_step_change_sensor_value(
        self, user_input: dict | None = None, errors: dict | None = None
    ) -> ConfigFlowResult:
        """Apply sensor updates through its entity service or display its value form.

        Args:
            user_input (dict | None): Submitted sensor value and attributes, if any.
            errors (dict | None): Validation errors keyed by form field.

        Returns:
            ConfigFlowResult: An update-confirmation or missing-entity abort, or the value form.
        """
        # user_input can be None; normalize to an empty dict for safe .get()/.update()
        user_input = user_input or {}
        errors = {} if errors is None else errors
        ent = entity_registry.async_entries_for_config_entry(
            entity_registry.async_get(self.hass), self.config_entry.entry_id
        )
        entity_id = None
        state = None
        if len(ent) > 0:
            entity_id = ent[0].entity_id
            state = self.hass.states.get(entity_id)
        else:
            _LOGGER.error("Unable to load Variable to Change Value")
        _LOGGER.debug("[Change Sensor Value] entity_id: %s", entity_id)
        _LOGGER.debug("[Change Sensor Value] state: %s", state)
        if entity_id is None or state is None:
            return self.async_abort(reason="entity_not_found")
        if user_input:
            _LOGGER.debug("[Change Sensor Value] user_input: %s", user_input)
            val: Any = user_input.get(CONF_VALUE)
            if (
                val is not None
                and isinstance(val, str)
                and self.config_entry.data.get(CONF_VALUE_TYPE) == "datetime"
            ):
                if (
                    user_input.get(CONF_TZOFFSET) is not None
                    and re.match(r"^[+-]?\d\d\:?\d\d\s*$", str(user_input.get(CONF_TZOFFSET)))
                    is not None
                ):
                    val = val + str(user_input.get(CONF_TZOFFSET))
                else:
                    val += "+0000"
            _LOGGER.debug("[Change Sensor Value] val: %s", val)
            try:
                newval = value_to_type(
                    val,
                    self.config_entry.data.get(CONF_VALUE_TYPE),
                )
            except ValueError:
                errors["base"] = "invalid_value_type"
            else:
                user_input[CONF_VALUE] = newval

            if not errors:
                update_variable = {
                    CONF_ENTITY_ID: [entity_id],
                    ATTR_REPLACE_ATTRIBUTES: True,
                }
                update_variable.update({ATTR_VALUE: val})
                update_variable.update({ATTR_ATTRIBUTES: user_input.get(ATTR_ATTRIBUTES)})
                _LOGGER.debug("[Change Sensor Value] update_variable: %s", update_variable)
                await self.hass.services.async_call(
                    DOMAIN, SERVICE_UPDATE_SENSOR, service_data=update_variable
                )
                return self.async_abort(reason="value_changed")

        change_sensor_value_schema = self.build_change_sensor_value(state)

        if self.config_entry.data.get(CONF_NAME) is None or self.config_entry.data.get(
            CONF_NAME
        ) == self.config_entry.data.get(CONF_VARIABLE_ID):
            disp_name = self.config_entry.data.get(CONF_VARIABLE_ID)
        else:
            disp_name = (
                f"{self.config_entry.data.get(CONF_NAME)} "
                f"({self.config_entry.data.get(CONF_VARIABLE_ID)})"
            )

        return self.async_show_form(
            step_id="change_sensor_value",
            data_schema=change_sensor_value_schema,
            errors=errors,
            description_placeholders={"disp_name": str(disp_name)},
        )

    def build_change_sensor_value(self, state: State) -> vol.Schema:
        """Build the schema for changing a sensor value.

        Args:
            state (State): Current Home Assistant state for the sensor entity.

        Returns:
            vol.Schema: Schema with fields compatible with the sensor's current configuration.
        """
        change_variable_value_schema = vol.Schema({})
        if self.config_entry.data.get(CONF_DEVICE_CLASS) == sensor.SensorDeviceClass.DATE:
            if state.state:
                change_variable_value_schema = change_variable_value_schema.extend(
                    {
                        vol.Optional(
                            CONF_VALUE,
                            default=state.state,
                        ): selector.DateSelector(selector.DateSelectorConfig())
                    }
                )
            else:
                change_variable_value_schema = change_variable_value_schema.extend(
                    {
                        vol.Optional(
                            CONF_VALUE,
                        ): selector.DateSelector(selector.DateSelectorConfig())
                    }
                )

        elif self.config_entry.data.get(CONF_DEVICE_CLASS) == sensor.SensorDeviceClass.TIMESTAMP:
            if state.state:
                dt = value_to_type(state.state, self.config_entry.data.get(CONF_VALUE_TYPE))
                if dt is not None and isinstance(dt, datetime.datetime):
                    tz_offset = dt.strftime("%z")
                    if tz_offset is None:
                        tz_offset = "+0000"
                    ts_val = dt.strftime("%Y-%m-%d %H:%M:%S")
                else:
                    ts_val = None
                    tz_offset = "+0000"
                _LOGGER.debug("ts_val: %s", ts_val)
                _LOGGER.debug("tz_offset: %s", tz_offset)
                change_variable_value_schema = change_variable_value_schema.extend(
                    {
                        vol.Optional(
                            CONF_VALUE,
                            default=ts_val,
                        ): selector.DateTimeSelector(selector.DateTimeSelectorConfig()),
                        vol.Optional(
                            CONF_TZOFFSET,
                            default=tz_offset,
                        ): selector.TextSelector(selector.TextSelectorConfig()),
                    }
                )
            else:
                default_tzoffset = datetime.datetime.now(
                    dt_util.get_time_zone(self.hass.config.time_zone)
                ).strftime("%z")
                if default_tzoffset is None:
                    default_tzoffset = "+0000"
                _LOGGER.debug("default_tzoffset: %s", default_tzoffset)
                change_variable_value_schema = change_variable_value_schema.extend(
                    {
                        vol.Optional(
                            CONF_VALUE,
                        ): selector.DateTimeSelector(selector.DateTimeSelectorConfig()),
                        vol.Optional(
                            CONF_TZOFFSET,
                            default=default_tzoffset,
                        ): selector.TextSelector(selector.TextSelectorConfig()),
                    }
                )
        elif state.state:
            change_variable_value_schema = change_variable_value_schema.extend(
                {
                    vol.Optional(
                        CONF_VALUE,
                        default=str(state.state),
                    ): selector.TextSelector(selector.TextSelectorConfig())
                }
            )
        else:
            change_variable_value_schema = change_variable_value_schema.extend(
                {
                    vol.Optional(
                        CONF_VALUE,
                    ): selector.TextSelector(selector.TextSelectorConfig())
                }
            )
        if state.as_dict().get("attributes"):
            change_variable_value_schema = change_variable_value_schema.extend(
                {
                    vol.Optional(
                        CONF_ATTRIBUTES, default=state.as_dict().get("attributes")
                    ): selector.ObjectSelector(selector.ObjectSelectorConfig())
                }
            )
        else:
            change_variable_value_schema = change_variable_value_schema.extend(
                {
                    vol.Optional(CONF_ATTRIBUTES): selector.ObjectSelector(
                        selector.ObjectSelectorConfig()
                    )
                }
            )
        return change_variable_value_schema

    async def async_step_change_binary_sensor_value(
        self, user_input: dict | None = None, errors: dict | None = None
    ) -> ConfigFlowResult:
        """Apply binary-sensor updates through its entity service or display its value form.

        Args:
            user_input (dict | None): Submitted binary-sensor value and attributes, if any.
            errors (dict | None): Validation errors keyed by form field.

        Returns:
            ConfigFlowResult: An update-confirmation or missing-entity abort, or the value form.
        """
        user_input = user_input or {}
        errors = {} if errors is None else errors
        ent = entity_registry.async_entries_for_config_entry(
            entity_registry.async_get(self.hass), self.config_entry.entry_id
        )
        entity_id = None
        state = None
        if len(ent) > 0:
            entity_id = ent[0].entity_id
            state = self.hass.states.get(entity_id)
        else:
            _LOGGER.error("Unable to load Variable to Change Value")
        _LOGGER.debug("[Change Binary Sensor Value] entity_id: %s", entity_id)
        _LOGGER.debug("[Change Binary Sensor Value] state: %s", state)
        if entity_id is None or state is None:
            return self.async_abort(reason="entity_not_found")
        if user_input:
            _LOGGER.debug("[Change Binary Sensor Value] user_input: %s", user_input)

            if not errors:
                update_variable = {
                    CONF_ENTITY_ID: [entity_id],
                    ATTR_REPLACE_ATTRIBUTES: True,
                }
                update_variable.update({ATTR_VALUE: user_input.get(CONF_VALUE)})
                update_variable.update({ATTR_ATTRIBUTES: user_input.get(ATTR_ATTRIBUTES)})
                _LOGGER.debug("[Change Binary Sensor Value] update_variable: %s", update_variable)
                await self.hass.services.async_call(
                    DOMAIN, SERVICE_UPDATE_BINARY_SENSOR, service_data=update_variable
                )
                return self.async_abort(reason="value_changed")

        change_binary_sensor_value_schema = self.build_change_binary_sensor_value(state)

        if self.config_entry.data.get(CONF_NAME) is None or self.config_entry.data.get(
            CONF_NAME
        ) == self.config_entry.data.get(CONF_VARIABLE_ID):
            disp_name = self.config_entry.data.get(CONF_VARIABLE_ID)
        else:
            disp_name = (
                f"{self.config_entry.data.get(CONF_NAME)} "
                f"({self.config_entry.data.get(CONF_VARIABLE_ID)})"
            )

        return self.async_show_form(
            step_id="change_binary_sensor_value",
            data_schema=change_binary_sensor_value_schema,
            errors=errors,
            description_placeholders={"disp_name": str(disp_name)},
        )

    def build_change_binary_sensor_value(self, state: State) -> vol.Schema:
        """Build the schema for changing a binary-sensor value.

        Args:
            state (State): Current Home Assistant state for the binary-sensor entity.

        Returns:
            vol.Schema: Schema with fields compatible with the binary sensor configuration.
        """
        if state.state is None or (
            isinstance(state.state, str)
            and state.state.lower() in ["", "none", "unknown", "unavailable"]
        ):
            bistate = "None"
        elif state.state == STATE_OFF:
            bistate = "false"
        elif state.state == STATE_ON:
            bistate = "true"
        else:
            bistate = state.state
        change_variable_value_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_VALUE,
                    default=bistate,
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=["None", "true", "false"],
                        translation_key="boolean_options",
                        multiple=False,
                        custom_value=False,
                        mode=selector.SelectSelectorMode.LIST,
                    )
                )
            }
        )
        if state.as_dict().get("attributes"):
            change_variable_value_schema = change_variable_value_schema.extend(
                {
                    vol.Optional(
                        CONF_ATTRIBUTES, default=state.as_dict().get("attributes")
                    ): selector.ObjectSelector(selector.ObjectSelectorConfig())
                }
            )
        else:
            change_variable_value_schema = change_variable_value_schema.extend(
                {
                    vol.Optional(CONF_ATTRIBUTES): selector.ObjectSelector(
                        selector.ObjectSelectorConfig()
                    )
                }
            )
        return change_variable_value_schema

    async def async_step_change_device_tracker_value(
        self, user_input: dict | None = None, errors: dict | None = None
    ) -> ConfigFlowResult:
        """Apply tracker updates through its entity service or display its value form.

        Args:
            user_input (dict | None): Submitted device-tracker value and attributes, if any.
            errors (dict | None): Validation errors keyed by form field.

        Returns:
            ConfigFlowResult: An update-confirmation or missing-entity abort, or the value form.
        """
        user_input = user_input or {}
        errors = {} if errors is None else errors
        ent = entity_registry.async_entries_for_config_entry(
            entity_registry.async_get(self.hass), self.config_entry.entry_id
        )
        entity_id = None
        state = None
        if len(ent) > 0:
            entity_id = ent[0].entity_id
            state = self.hass.states.get(entity_id)
        else:
            _LOGGER.error("Unable to load Variable to Change Value")
        _LOGGER.debug("[Change Device Tracker Value] entity_id: %s", entity_id)
        _LOGGER.debug("[Change Device Tracker Value] state: %s", state)
        if entity_id is None or state is None:
            return self.async_abort(reason="entity_not_found")
        if user_input:
            _LOGGER.debug("[Change Device Tracker Value] user_input: %s", user_input)

            if not errors:
                update_variable = {
                    CONF_ENTITY_ID: [entity_id],
                    ATTR_REPLACE_ATTRIBUTES: True,
                }
                # Preserve zero coordinates/levels; truthy checks would drop them.
                if user_input.get(ATTR_LATITUDE) is not None:
                    update_variable.update({ATTR_LATITUDE: user_input.get(ATTR_LATITUDE)})
                if user_input.get(ATTR_LONGITUDE) is not None:
                    update_variable.update({ATTR_LONGITUDE: user_input.get(ATTR_LONGITUDE)})
                if user_input.get(ATTR_LOCATION_NAME):
                    update_variable.update({ATTR_LOCATION_NAME: user_input.get(ATTR_LOCATION_NAME)})
                if user_input.get(ATTR_DELETE_LOCATION_NAME):
                    update_variable.update(
                        {ATTR_DELETE_LOCATION_NAME: user_input.get(ATTR_DELETE_LOCATION_NAME)}
                    )
                if user_input.get(ATTR_IN_ZONES) is not None:
                    update_variable.update({ATTR_IN_ZONES: user_input.get(ATTR_IN_ZONES)})
                if user_input.get(ATTR_DELETE_IN_ZONES):
                    update_variable.update(
                        {ATTR_DELETE_IN_ZONES: user_input.get(ATTR_DELETE_IN_ZONES)}
                    )
                if user_input.get(ATTR_GPS_ACCURACY) is not None:
                    update_variable.update({ATTR_GPS_ACCURACY: user_input.get(ATTR_GPS_ACCURACY)})
                if user_input.get(ATTR_BATTERY_LEVEL) is not None:
                    update_variable.update({ATTR_BATTERY_LEVEL: user_input.get(ATTR_BATTERY_LEVEL)})
                update_variable.update({ATTR_ATTRIBUTES: user_input.get(ATTR_ATTRIBUTES)})
                _LOGGER.debug("[Change Device Tracker Value] update_variable: %s", update_variable)
                await self.hass.services.async_call(
                    DOMAIN, SERVICE_UPDATE_DEVICE_TRACKER, service_data=update_variable
                )
                return self.async_abort(reason="value_changed")

        change_device_tracker_value_schema = self.build_change_device_tracker_value(state)

        if self.config_entry.data.get(CONF_NAME) is None or self.config_entry.data.get(
            CONF_NAME
        ) == self.config_entry.data.get(CONF_VARIABLE_ID):
            disp_name = self.config_entry.data.get(CONF_VARIABLE_ID)
        else:
            disp_name = (
                f"{self.config_entry.data.get(CONF_NAME)} "
                f"({self.config_entry.data.get(CONF_VARIABLE_ID)})"
            )
        if state is not None and getattr(state, "state", None):
            dt_state = str(state.state)
        else:
            dt_state = "None"

        return self.async_show_form(
            step_id="change_device_tracker_value",
            data_schema=change_device_tracker_value_schema,
            errors=errors,
            description_placeholders={
                "disp_name": str(disp_name),
                "dt_state": str(dt_state),
            },
        )

    def build_change_device_tracker_value(self, state: State) -> vol.Schema:
        """Build the schema for changing a device-tracker value.

        Args:
            state (State): Current Home Assistant state for the device-tracker entity.

        Returns:
            vol.Schema: Schema with fields compatible with the device tracker configuration.
        """
        attr = dict(state.attributes)
        lat = attr.pop(ATTR_LATITUDE, None)
        long = attr.pop(ATTR_LONGITUDE, None)
        loc = attr.pop(ATTR_LOCATION_NAME, None)
        in_zones = attr.pop(ATTR_IN_ZONES, None)
        gpsacc = attr.pop(ATTR_GPS_ACCURACY, None)
        battlvl = attr.pop(ATTR_BATTERY_LEVEL, None)
        change_variable_value_schema = vol.Schema(
            {
                vol.Required(ATTR_LATITUDE, default=lat): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=-90,
                        max=90,
                        step="any",
                        unit_of_measurement="°",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(ATTR_LONGITUDE, default=long): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=-180,
                        max=180,
                        step="any",
                        unit_of_measurement="°",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        if loc is None:
            change_variable_value_schema = change_variable_value_schema.extend(
                {
                    vol.Optional(ATTR_LOCATION_NAME): cv.string,
                }
            )
        else:
            change_variable_value_schema = change_variable_value_schema.extend(
                {
                    vol.Optional(
                        ATTR_LOCATION_NAME,
                        default=loc,
                    ): cv.string,
                }
            )
        change_variable_value_schema = change_variable_value_schema.extend(
            {
                vol.Optional(
                    ATTR_DELETE_LOCATION_NAME,
                ): selector.BooleanSelector(selector.BooleanSelectorConfig())
            }
        )
        zone_selector = selector.EntitySelector(
            selector.EntitySelectorConfig(domain="zone", multiple=True)
        )
        if in_zones:
            change_variable_value_schema = change_variable_value_schema.extend(
                {vol.Optional(ATTR_IN_ZONES, default=in_zones): zone_selector}
            )
        else:
            change_variable_value_schema = change_variable_value_schema.extend(
                {vol.Optional(ATTR_IN_ZONES): zone_selector}
            )
        change_variable_value_schema = change_variable_value_schema.extend(
            {
                vol.Optional(ATTR_DELETE_IN_ZONES): selector.BooleanSelector(
                    selector.BooleanSelectorConfig()
                )
            }
        )
        if gpsacc is None:
            change_variable_value_schema = change_variable_value_schema.extend(
                {
                    vol.Optional(ATTR_GPS_ACCURACY): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0,
                            max=1000000,
                            step=1,
                            unit_of_measurement="m",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                }
            )
        else:
            change_variable_value_schema = change_variable_value_schema.extend(
                {
                    vol.Optional(
                        ATTR_GPS_ACCURACY,
                        default=gpsacc,
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0,
                            max=1000000,
                            step=1,
                            unit_of_measurement="m",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                }
            )
        if battlvl is None:
            change_variable_value_schema = change_variable_value_schema.extend(
                {
                    vol.Optional(
                        ATTR_BATTERY_LEVEL,
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0,
                            max=100,
                            step=1,
                            unit_of_measurement="%",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                }
            )
        else:
            change_variable_value_schema = change_variable_value_schema.extend(
                {
                    vol.Optional(
                        ATTR_BATTERY_LEVEL,
                        default=battlvl,
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0,
                            max=100,
                            step=1,
                            unit_of_measurement="%",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                }
            )
        if attr:
            change_variable_value_schema = change_variable_value_schema.extend(
                {
                    vol.Optional(CONF_ATTRIBUTES, default=attr): selector.ObjectSelector(
                        selector.ObjectSelectorConfig()
                    )
                }
            )
        else:
            change_variable_value_schema = change_variable_value_schema.extend(
                {
                    vol.Optional(CONF_ATTRIBUTES): selector.ObjectSelector(
                        selector.ObjectSelectorConfig()
                    )
                }
            )
        return change_variable_value_schema

    async def async_step_sensor_options(
        self,
        user_input: dict[str, Any] | None = None,
        errors: dict[str, str] | None = None,
    ) -> ConfigFlowResult:
        """Collect first-page sensor options and advance to typed details.

        Args:
            user_input (dict[str, Any] | None): Submitted sensor option fields, if any.
            errors (dict[str, str] | None): Validation errors keyed by form field.

        Returns:
            ConfigFlowResult: The second sensor options page, or the first-page selector form.
        """
        errors = {} if errors is None else errors
        if user_input is not None:
            _LOGGER.debug("[Sensor Options Page 1] page_1_input: %s", user_input)
            self.sensor_options_page_1 = user_input
            return await self.async_step_sensor_options_page_2()

        sensor_options_page_1_schema = self.build_sensor_options_page_1()

        if self.config_entry.data.get(CONF_NAME) is None or self.config_entry.data.get(
            CONF_NAME
        ) == self.config_entry.data.get(CONF_VARIABLE_ID):
            disp_name = self.config_entry.data.get(CONF_VARIABLE_ID)
        else:
            disp_name = (
                f"{self.config_entry.data.get(CONF_NAME)} "
                f"({self.config_entry.data.get(CONF_VARIABLE_ID)})"
            )

        return self.async_show_form(
            step_id="sensor_options",
            data_schema=sensor_options_page_1_schema,
            errors=errors,
            description_placeholders={
                "component_config_url": str(COMPONENT_CONFIG_URL),
                "disp_name": str(disp_name),
            },
        )

    def build_sensor_options_page_1(self) -> vol.Schema:
        """Build the schema for the first sensor options page.

        Returns:
            vol.Schema: Schema for selecting sensor options and device class.
        """
        sensor_options_page_1_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_DEVICE_CLASS,
                    default=self.config_entry.data.get(CONF_DEVICE_CLASS, "None"),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=SENSOR_DEVICE_CLASS_SELECT_LIST,
                        multiple=False,
                        custom_value=False,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        if self.config_entry.data.get(CONF_DEVICE_ID, None):
            sensor_options_page_1_schema = sensor_options_page_1_schema.extend(
                {
                    vol.Optional(
                        CONF_DEVICE_ID,
                        default=self.config_entry.data.get(CONF_DEVICE_ID, None),
                    ): selector.DeviceSelector(selector.DeviceSelectorConfig()),
                    vol.Optional(
                        CONF_CLEAR_DEVICE_ID,
                    ): selector.BooleanSelector(selector.BooleanSelectorConfig()),
                }
            )
        else:
            sensor_options_page_1_schema = sensor_options_page_1_schema.extend(
                {
                    vol.Optional(
                        CONF_DEVICE_ID,
                    ): selector.DeviceSelector(selector.DeviceSelectorConfig()),
                }
            )

        return sensor_options_page_1_schema.extend(
            {
                vol.Optional(
                    CONF_RESTORE,
                    default=self.config_entry.data.get(CONF_RESTORE, DEFAULT_RESTORE),
                ): selector.BooleanSelector(selector.BooleanSelectorConfig()),
                vol.Optional(
                    CONF_FORCE_UPDATE,
                    default=self.config_entry.data.get(CONF_FORCE_UPDATE, DEFAULT_FORCE_UPDATE),
                ): selector.BooleanSelector(selector.BooleanSelectorConfig()),
                vol.Optional(
                    CONF_EXCLUDE_FROM_RECORDER,
                    default=self.config_entry.data.get(
                        CONF_EXCLUDE_FROM_RECORDER, DEFAULT_EXCLUDE_FROM_RECORDER
                    ),
                ): selector.BooleanSelector(selector.BooleanSelectorConfig()),
            }
        )

    async def async_step_sensor_options_page_2(
        self,
        user_input: dict[str, Any] | None = None,
        errors: dict[str, str] | None = None,
    ) -> ConfigFlowResult:
        """Persist typed sensor options and reload the entity.

        Args:
            user_input (dict[str, Any] | None): Submitted sensor value and attribute fields, if any.
            errors (dict[str, str] | None): Validation errors keyed by form field.

        Returns:
            ConfigFlowResult: An updated config entry, or the second sensor options form.
        """
        errors = {} if errors is None else errors
        if user_input is not None:
            _LOGGER.debug("[Sensor Options Page 2] user_input: %s", user_input)
            val: Any
            if (
                user_input.get(CONF_VALUE) is not None
                and isinstance(user_input.get(CONF_VALUE), str)
                and self.sensor_options_page_1.get(CONF_VALUE_TYPE) == "datetime"
            ):
                tzoffset = str(user_input.get(CONF_TZOFFSET, ""))
                value = str(user_input.get(CONF_VALUE))
                if re.match(r"^[+-]?\d\d\:?\d\d\s*$", tzoffset) is not None:
                    val = value + tzoffset
                else:
                    val = value + "+0000"
            else:
                val = user_input.get(CONF_VALUE)
            _LOGGER.debug("[New Sensor Page 2] val: %s", val)
            try:
                newval = value_to_type(
                    val,
                    self.sensor_options_page_1.get(CONF_VALUE_TYPE),
                )
            except ValueError:
                errors["base"] = "invalid_value_type"
            else:
                user_input[CONF_VALUE] = newval

            if not errors:
                if self.sensor_options_page_1 is not None and self.sensor_options_page_1:
                    user_input.update(self.sensor_options_page_1)
                for m in dict(self.config_entry.data):
                    user_input.setdefault(m, self.config_entry.data[m])
                if user_input.get(CONF_CLEAR_DEVICE_ID, False):
                    user_input.pop(CONF_DEVICE_ID, None)
                user_input.pop(CONF_CLEAR_DEVICE_ID, None)
                if user_input is not None:
                    for k, v in list(user_input.items()):
                        if v is None or (isinstance(v, str) and v.lower() == "none"):
                            user_input.pop(k, None)
                user_input.update({CONF_UPDATED: True})
                _LOGGER.debug("[Sensor Options Page 2] Final user_input: %s", user_input)

                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data=user_input,
                    options={},
                )
                await self.hass.config_entries.async_reload(self.config_entry.entry_id)
                return self.async_create_entry(title="", data=user_input)

        sensor_options_page_2_schema = self.build_sensor_options_page_2()

        if self.config_entry.data.get(CONF_NAME) is None or self.config_entry.data.get(
            CONF_NAME
        ) == self.config_entry.data.get(CONF_VARIABLE_ID):
            disp_name = self.config_entry.data.get(CONF_VARIABLE_ID)
        else:
            disp_name = (
                f"{self.config_entry.data.get(CONF_NAME)} "
                f"({self.config_entry.data.get(CONF_VARIABLE_ID)})"
            )

        return self.async_show_form(
            step_id="sensor_options_page_2",
            data_schema=sensor_options_page_2_schema,
            errors=errors,
            description_placeholders={
                "disp_name": str(disp_name),
                "value_type": str(self.sensor_options_page_1.get(CONF_VALUE_TYPE, "None")),
                "device_class": str(self.sensor_options_page_1.get(CONF_DEVICE_CLASS, "None")),
            },
        )

    def check_value_default(
        self, new_device_class: sensor.SensorDeviceClass | str | None
    ) -> tuple[bool, object]:
        """Return whether the existing value remains a valid default.

        Args:
            new_device_class (sensor.SensorDeviceClass | str | None): Proposed sensor
                device class from the options form.

        Returns:
            tuple[bool, object]: Whether the current value is valid and the value to
                use as its default.
        """
        _LOGGER.debug(
            "[check_value_default] value: %s, current device_class: %s (%s), "
            "new_device_class: %s (%s)",
            self.config_entry.data.get(CONF_VALUE),
            self.config_entry.data.get(CONF_DEVICE_CLASS),
            type(self.config_entry.data.get(CONF_DEVICE_CLASS)),
            new_device_class,
            type(new_device_class),
        )
        val_default_value = None
        cfg_val = self.config_entry.data.get(CONF_VALUE)
        if (
            cfg_val is None
            or (isinstance(cfg_val, str) and cfg_val.lower() == "none")
            or self.config_entry.data.get(CONF_DEVICE_CLASS) != new_device_class
        ):
            val_default = False
        else:
            val_default = True
            val_default_value = self.config_entry.data.get(CONF_VALUE)
        return val_default, val_default_value

    def build_sensor_options_page_2(self) -> vol.Schema:
        """Build the schema for the second sensor options page.

        Returns:
            vol.Schema: Schema with values, attributes, and units for the selected class.
        """
        sensor_state_class_select_list = []
        sensor_state_class_select_list.append(selector.SelectOptionDict(label="None", value="None"))
        sensor_units_select_list = []
        sensor_units_select_list.append(selector.SelectOptionDict(label="None", value="None"))
        _LOGGER.debug(
            "[build_sensor_options_page_2] device_class: %s (%s)",
            self.sensor_options_page_1.get(CONF_DEVICE_CLASS),
            type(self.sensor_options_page_1.get(CONF_DEVICE_CLASS)),
        )
        device_class = _normalize_sensor_device_class(
            self.sensor_options_page_1.get(CONF_DEVICE_CLASS)
        )
        val_default, val_default_value = self.check_value_default(device_class)

        sensor_options_page_2_schema = vol.Schema({})
        if device_class is not None:
            state_classes = sensor.DEVICE_CLASS_STATE_CLASSES.get(device_class, set())
            sensor_state_class_select_list.extend(
                selector.SelectOptionDict(label=str(state_class.name), value=str(state_class.value))
                for state_class in state_classes
            )
            sensor_units_select_list.extend(_sensor_unit_options(device_class))

            if device_class == sensor.SensorDeviceClass.DATE:
                value_type = "date"
                if val_default:
                    sensor_options_page_2_schema = sensor_options_page_2_schema.extend(
                        {
                            vol.Optional(
                                CONF_VALUE,
                                default=val_default_value,
                            ): selector.DateSelector(selector.DateSelectorConfig())
                        }
                    )
                else:
                    sensor_options_page_2_schema = sensor_options_page_2_schema.extend(
                        {
                            vol.Optional(
                                CONF_VALUE,
                            ): selector.DateSelector(selector.DateSelectorConfig())
                        }
                    )

            elif device_class == sensor.SensorDeviceClass.TIMESTAMP:
                value_type = "datetime"
                if val_default:
                    _LOGGER.debug("val_default_value: %s", val_default_value)
                    dt = value_to_type(val_default_value, value_type)
                    if dt is not None and isinstance(dt, datetime.datetime):
                        tz_offset = dt.strftime("%z")
                        if tz_offset is None:
                            tz_offset = "+0000"
                        ts_val = dt.strftime("%Y-%m-%d %H:%M:%S")
                    else:
                        ts_val = None
                        tz_offset = "+0000"
                    _LOGGER.debug("ts_val: %s", ts_val)
                    _LOGGER.debug("tz_offset: %s", tz_offset)
                    sensor_options_page_2_schema = sensor_options_page_2_schema.extend(
                        {
                            vol.Optional(
                                CONF_VALUE,
                                default=ts_val,
                            ): selector.DateTimeSelector(selector.DateTimeSelectorConfig()),
                            vol.Optional(
                                CONF_TZOFFSET,
                                default=tz_offset,
                            ): selector.TextSelector(selector.TextSelectorConfig()),
                        }
                    )
                else:
                    default_tzoffset = datetime.datetime.now(
                        dt_util.get_time_zone(self.hass.config.time_zone)
                    ).strftime("%z")
                    if default_tzoffset is None:
                        default_tzoffset = "+0000"
                    _LOGGER.debug("default_tzoffset: %s", default_tzoffset)
                    sensor_options_page_2_schema = sensor_options_page_2_schema.extend(
                        {
                            vol.Optional(
                                CONF_VALUE,
                            ): selector.DateTimeSelector(selector.DateTimeSelectorConfig()),
                            vol.Optional(
                                CONF_TZOFFSET,
                                default=default_tzoffset,
                            ): selector.TextSelector(selector.TextSelectorConfig()),
                        }
                    )
            else:
                value_type = "number"
                if val_default:
                    sensor_options_page_2_schema = sensor_options_page_2_schema.extend(
                        {
                            vol.Optional(
                                CONF_VALUE,
                                default=str(val_default_value),
                            ): selector.TextSelector(selector.TextSelectorConfig())
                        }
                    )
                else:
                    sensor_options_page_2_schema = sensor_options_page_2_schema.extend(
                        {
                            vol.Optional(
                                CONF_VALUE,
                            ): selector.TextSelector(selector.TextSelectorConfig())
                        }
                    )
        else:
            sensor_state_class_select_list.extend(
                selector.SelectOptionDict(label=str(el.name), value=str(el.value))
                for el in sensor.SensorStateClass
            )
            value_type = "string"
            if val_default:
                sensor_options_page_2_schema = sensor_options_page_2_schema.extend(
                    {
                        vol.Optional(
                            CONF_VALUE,
                            default=val_default_value,
                        ): selector.TextSelector(selector.TextSelectorConfig())
                    }
                )
            else:
                sensor_options_page_2_schema = sensor_options_page_2_schema.extend(
                    {
                        vol.Optional(
                            CONF_VALUE,
                        ): selector.TextSelector(selector.TextSelectorConfig())
                    }
                )

        sensor_options_page_2_schema = sensor_options_page_2_schema.extend(
            {
                vol.Optional(
                    CONF_ATTRIBUTES, default=self.config_entry.data.get(CONF_ATTRIBUTES)
                ): selector.ObjectSelector(selector.ObjectSelectorConfig())
            }
        )
        if len(sensor_state_class_select_list) > 1:
            sensor_options_page_2_schema = sensor_options_page_2_schema.extend(
                {
                    vol.Optional(
                        sensor.CONF_STATE_CLASS,
                        default=(
                            self.config_entry.data.get(sensor.CONF_STATE_CLASS, "None")
                            if (
                                self.config_entry.data.get(CONF_DEVICE_CLASS)
                                == self.sensor_options_page_1.get(CONF_DEVICE_CLASS)
                            )
                            else "None"
                        ),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=sensor_state_class_select_list,
                            multiple=False,
                            custom_value=False,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            )
        else:
            self.sensor_options_page_1[sensor.CONF_STATE_CLASS] = None

        if len(sensor_units_select_list) > 1:
            sensor_options_page_2_schema = sensor_options_page_2_schema.extend(
                {
                    vol.Optional(
                        CONF_UNIT_OF_MEASUREMENT,
                        default=(
                            self.config_entry.data.get(CONF_UNIT_OF_MEASUREMENT, "None")
                            if (
                                self.config_entry.data.get(CONF_DEVICE_CLASS)
                                == self.sensor_options_page_1.get(CONF_DEVICE_CLASS)
                            )
                            else "None"
                        ),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=sensor_units_select_list,
                            multiple=False,
                            custom_value=False,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            )
        else:
            self.sensor_options_page_1[CONF_UNIT_OF_MEASUREMENT] = None

        self.sensor_options_page_1.update({CONF_VALUE_TYPE: value_type})
        return sensor_options_page_2_schema

    async def async_step_binary_sensor_options(
        self,
        user_input: dict[str, Any] | None = None,
        errors: dict[str, str] | None = None,
    ) -> ConfigFlowResult:
        """Persist binary-sensor options and reload the entity.

        Args:
            user_input (dict[str, Any] | None): Submitted binary-sensor option fields, if any.
            errors (dict[str, str] | None): Validation errors keyed by form field.

        Returns:
            ConfigFlowResult: An updated config entry, or the binary-sensor options form.
        """
        errors = {} if errors is None else errors
        if user_input is not None:
            _LOGGER.debug("[Binary Sensor Options] user_input: %s", user_input)
            for m in dict(self.config_entry.data):
                user_input.setdefault(m, self.config_entry.data[m])
            if user_input.get(CONF_CLEAR_DEVICE_ID, False):
                user_input.pop(CONF_DEVICE_ID, None)
            user_input.pop(CONF_CLEAR_DEVICE_ID, None)
            user_input.update({CONF_UPDATED: True})
            _LOGGER.debug("[Binary Sensor Options] updated user_input: %s", user_input)

            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data=user_input,
                options={},
            )
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            return self.async_create_entry(title="", data=user_input)

        binary_sensor_options_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_VALUE,
                    default=(
                        self.config_entry.data.get(CONF_VALUE)
                        if self.config_entry.data.get(CONF_VALUE) is not None
                        else "None"
                    ),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=["None", "true", "false"],
                        translation_key="boolean_options",
                        multiple=False,
                        custom_value=False,
                        mode=selector.SelectSelectorMode.LIST,
                    )
                ),
                vol.Optional(
                    CONF_ATTRIBUTES, default=self.config_entry.data.get(CONF_ATTRIBUTES)
                ): selector.ObjectSelector(selector.ObjectSelectorConfig()),
                vol.Optional(
                    CONF_DEVICE_CLASS,
                    default=self.config_entry.data.get(CONF_DEVICE_CLASS, "None"),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=BINARY_SENSOR_DEVICE_CLASS_SELECT_LIST,
                        multiple=False,
                        custom_value=False,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )

        if self.config_entry.data.get(CONF_DEVICE_ID, None):
            binary_sensor_options_schema = binary_sensor_options_schema.extend(
                {
                    vol.Optional(
                        CONF_DEVICE_ID,
                        default=self.config_entry.data.get(CONF_DEVICE_ID, None),
                    ): selector.DeviceSelector(selector.DeviceSelectorConfig()),
                    vol.Optional(
                        CONF_CLEAR_DEVICE_ID,
                    ): selector.BooleanSelector(selector.BooleanSelectorConfig()),
                }
            )
        else:
            binary_sensor_options_schema = binary_sensor_options_schema.extend(
                {
                    vol.Optional(
                        CONF_DEVICE_ID,
                    ): selector.DeviceSelector(selector.DeviceSelectorConfig()),
                }
            )

        binary_sensor_options_schema = binary_sensor_options_schema.extend(
            {
                vol.Optional(
                    CONF_RESTORE,
                    default=self.config_entry.data.get(CONF_RESTORE, DEFAULT_RESTORE),
                ): selector.BooleanSelector(selector.BooleanSelectorConfig()),
                vol.Optional(
                    CONF_FORCE_UPDATE,
                    default=self.config_entry.data.get(CONF_FORCE_UPDATE, DEFAULT_FORCE_UPDATE),
                ): selector.BooleanSelector(selector.BooleanSelectorConfig()),
                vol.Optional(
                    CONF_EXCLUDE_FROM_RECORDER,
                    default=self.config_entry.data.get(
                        CONF_EXCLUDE_FROM_RECORDER, DEFAULT_EXCLUDE_FROM_RECORDER
                    ),
                ): selector.BooleanSelector(selector.BooleanSelectorConfig()),
            }
        )

        if self.config_entry.data.get(CONF_NAME) is None or self.config_entry.data.get(
            CONF_NAME
        ) == self.config_entry.data.get(CONF_VARIABLE_ID):
            disp_name = self.config_entry.data.get(CONF_VARIABLE_ID)
        else:
            disp_name = (
                f"{self.config_entry.data.get(CONF_NAME)} "
                f"({self.config_entry.data.get(CONF_VARIABLE_ID)})"
            )

        return self.async_show_form(
            step_id="binary_sensor_options",
            data_schema=binary_sensor_options_schema,
            errors=errors,
            description_placeholders={
                "component_config_url": str(COMPONENT_CONFIG_URL),
                "disp_name": str(disp_name),
            },
        )

    async def async_step_device_tracker_options(
        self,
        user_input: dict[str, Any] | None = None,
        errors: dict[str, str] | None = None,
    ) -> ConfigFlowResult:
        """Persist device-tracker options and reload the entity.

        Args:
            user_input (dict[str, Any] | None): Submitted device-tracker option fields, if any.
            errors (dict[str, str] | None): Validation errors keyed by form field.

        Returns:
            ConfigFlowResult: An updated config entry, or the device-tracker options form.
        """
        errors = {} if errors is None else errors
        if user_input is not None:
            _LOGGER.debug("[Device Tracker Options] user_input: %s", user_input)
            for m in dict(self.config_entry.data):
                user_input.setdefault(m, self.config_entry.data[m])
            if user_input.get(CONF_CLEAR_DEVICE_ID, False):
                user_input.pop(CONF_DEVICE_ID, None)
            user_input.pop(CONF_CLEAR_DEVICE_ID, None)
            user_input.update({CONF_UPDATED: True})
            _LOGGER.debug("[Device Tracker Options] updated user_input: %s", user_input)

            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data=user_input,
                options={},
            )
            await self.hass.config_entries.async_reload(self.config_entry.entry_id)
            return self.async_create_entry(title="", data=user_input)

        device_tracker_options_schema = vol.Schema(
            {
                vol.Required(
                    ATTR_LATITUDE, default=self.config_entry.data.get(ATTR_LATITUDE)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=-90,
                        max=90,
                        step="any",
                        unit_of_measurement="°",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    ATTR_LONGITUDE, default=self.config_entry.data.get(ATTR_LONGITUDE)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=-180,
                        max=180,
                        step="any",
                        unit_of_measurement="°",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
            }
        )
        if self.config_entry.data.get(ATTR_LOCATION_NAME) is None:
            device_tracker_options_schema = device_tracker_options_schema.extend(
                {
                    vol.Optional(ATTR_LOCATION_NAME): cv.string,
                }
            )
        else:
            device_tracker_options_schema = device_tracker_options_schema.extend(
                {
                    vol.Optional(
                        ATTR_LOCATION_NAME,
                        default=self.config_entry.data.get(ATTR_LOCATION_NAME),
                    ): cv.string,
                }
            )
        if self.config_entry.data.get(ATTR_GPS_ACCURACY) is None:
            device_tracker_options_schema = device_tracker_options_schema.extend(
                {
                    vol.Optional(ATTR_GPS_ACCURACY): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0,
                            max=1000000,
                            step=1,
                            unit_of_measurement="m",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                }
            )
        else:
            device_tracker_options_schema = device_tracker_options_schema.extend(
                {
                    vol.Optional(
                        ATTR_GPS_ACCURACY,
                        default=self.config_entry.data.get(ATTR_GPS_ACCURACY),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0,
                            max=1000000,
                            step=1,
                            unit_of_measurement="m",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                }
            )
        if self.config_entry.data.get(ATTR_BATTERY_LEVEL) is None:
            device_tracker_options_schema = device_tracker_options_schema.extend(
                {
                    vol.Optional(
                        ATTR_BATTERY_LEVEL,
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0,
                            max=100,
                            step=1,
                            unit_of_measurement="%",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                }
            )
        else:
            device_tracker_options_schema = device_tracker_options_schema.extend(
                {
                    vol.Optional(
                        ATTR_BATTERY_LEVEL,
                        default=self.config_entry.data.get(ATTR_BATTERY_LEVEL),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0,
                            max=100,
                            step=1,
                            unit_of_measurement="%",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                }
            )

        device_tracker_options_schema = device_tracker_options_schema.extend(
            {
                vol.Optional(
                    CONF_ATTRIBUTES, default=self.config_entry.data.get(CONF_ATTRIBUTES)
                ): selector.ObjectSelector(selector.ObjectSelectorConfig()),
            }
        )

        if self.config_entry.data.get(CONF_DEVICE_ID, None):
            device_tracker_options_schema = device_tracker_options_schema.extend(
                {
                    vol.Optional(
                        CONF_DEVICE_ID,
                        default=self.config_entry.data.get(CONF_DEVICE_ID, None),
                    ): selector.DeviceSelector(selector.DeviceSelectorConfig()),
                    vol.Optional(
                        CONF_CLEAR_DEVICE_ID,
                    ): selector.BooleanSelector(selector.BooleanSelectorConfig()),
                }
            )
        else:
            device_tracker_options_schema = device_tracker_options_schema.extend(
                {
                    vol.Optional(
                        CONF_DEVICE_ID,
                    ): selector.DeviceSelector(selector.DeviceSelectorConfig()),
                }
            )

        device_tracker_options_schema = device_tracker_options_schema.extend(
            {
                vol.Optional(
                    CONF_RESTORE,
                    default=self.config_entry.data.get(CONF_RESTORE, DEFAULT_RESTORE),
                ): selector.BooleanSelector(selector.BooleanSelectorConfig()),
                vol.Optional(
                    CONF_FORCE_UPDATE,
                    default=self.config_entry.data.get(CONF_FORCE_UPDATE, DEFAULT_FORCE_UPDATE),
                ): selector.BooleanSelector(selector.BooleanSelectorConfig()),
                vol.Optional(
                    CONF_EXCLUDE_FROM_RECORDER,
                    default=self.config_entry.data.get(
                        CONF_EXCLUDE_FROM_RECORDER, DEFAULT_EXCLUDE_FROM_RECORDER
                    ),
                ): selector.BooleanSelector(selector.BooleanSelectorConfig()),
            }
        )

        if self.config_entry.data.get(CONF_NAME) is None or self.config_entry.data.get(
            CONF_NAME
        ) == self.config_entry.data.get(CONF_VARIABLE_ID):
            disp_name = self.config_entry.data.get(CONF_VARIABLE_ID)
        else:
            disp_name = (
                f"{self.config_entry.data.get(CONF_NAME)} "
                f"({self.config_entry.data.get(CONF_VARIABLE_ID)})"
            )

        return self.async_show_form(
            step_id="device_tracker_options",
            data_schema=device_tracker_options_schema,
            errors=errors,
            description_placeholders={
                "component_config_url": str(COMPONENT_CONFIG_URL),
                "disp_name": str(disp_name),
            },
        )

    async def async_step_device_options(
        self,
        user_input: dict[str, Any] | None = None,
        errors: dict[str, str] | None = None,
    ) -> ConfigFlowResult:
        """Persist virtual-device metadata options and reload linked entities.

        Args:
            user_input (dict[str, Any] | None): Submitted device option fields, if any.
            errors (dict[str, str] | None): Validation errors keyed by form field.

        Returns:
            ConfigFlowResult: An updated config entry or the virtual-device options form.
        """
        errors = {} if errors is None else errors
        if user_input is not None:
            try:
                # Cannot use cv.url validation in the schema itself so apply
                # extra validation here
                if user_input.get(CONF_CONFIGURATION_URL, None):
                    cv.url(user_input.get(CONF_CONFIGURATION_URL))
                for m in dict(self.config_entry.data):
                    user_input.setdefault(m, self.config_entry.data[m])
                _LOGGER.debug("[Device Options] updated user_input: %s", user_input)
            except vol.Invalid:
                errors["base"] = "invalid_url"
            else:
                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data=user_input,
                    options={},
                )
                await update_device(self.hass, self.config_entry, user_input)
                return self.async_create_entry(title="", data=user_input)

        device_options_schema = vol.Schema({})

        options = [
            CONF_CONFIGURATION_URL,
            CONF_MANUFACTURER,
            CONF_HW_VERSION,
            CONF_MODEL,
            CONF_MODEL_ID,
            CONF_SERIAL_NUMBER,
            CONF_SW_VERSION,
        ]
        for option in options:
            if self.config_entry.data.get(option, None):
                device_options_schema = device_options_schema.extend(
                    {vol.Optional(option, default=self.config_entry.data.get(option)): cv.string}
                )
            else:
                device_options_schema = device_options_schema.extend(
                    {vol.Optional(option): cv.string}
                )
        _LOGGER.debug("[Device Options] self.config_entry.data: %s", self.config_entry.data)
        return self.async_show_form(
            step_id="device_options",
            data_schema=device_options_schema,
            errors=errors,
            description_placeholders={
                "component_config_url": str(COMPONENT_CONFIG_URL),
                "disp_name": str(self.config_entry.data.get(CONF_NAME)),
            },
        )
