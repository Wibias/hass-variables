"""Integration tests for the Variable config flow."""

import datetime
from typing import Any
from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.device_tracker.const import ATTR_LOCATION_NAME
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.components.sensor.const import CONF_STATE_CLASS
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_BATTERY_LEVEL,
    ATTR_GPS_ACCURACY,
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
    CONF_DEVICE,
    CONF_DEVICE_CLASS,
    CONF_ICON,
    CONF_NAME,
    CONF_UNIT_OF_MEASUREMENT,
    MATCH_ALL,
    STATE_NOT_HOME,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, InvalidData
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.setup import async_setup_component
import pytest

from custom_components.variable.config_flow import VariableConfigFlow
from custom_components.variable.const import (
    ATTR_DELETE_IN_ZONES,
    ATTR_IN_ZONES,
    CONF_ATTRIBUTES,
    CONF_ENTITY_PLATFORM,
    CONF_EXCLUDE_FROM_RECORDER,
    CONF_FORCE_UPDATE,
    CONF_RESTORE,
    CONF_TZOFFSET,
    CONF_VALUE,
    CONF_VALUE_TYPE,
    CONF_VARIABLE_ID,
    CONF_YAML_VARIABLE,
    DOMAIN,
    SERVICE_UPDATE_DEVICE_TRACKER,
)
from custom_components.variable.device import _get_device_for_entry
from tests.types import ConfigEntryFactory


async def _start_sensor_flow(
    hass: HomeAssistant, page_1_input: dict[str, Any]
) -> config_entries.ConfigFlowResult:
    """Start a sensor flow and submit its first page.

    Args:
        hass (HomeAssistant): Home Assistant instance that owns the flow.
        page_1_input (dict[str, Any]): Data submitted to the sensor flow's first page.

    Returns:
        config_entries.ConfigFlowResult: The sensor flow result for its second page.
    """
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"next_step_id": "add_sensor"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "add_sensor"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=page_1_input
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "sensor_page_2"
    return result


async def test_user_flow_menu(hass: HomeAssistant) -> None:
    """Expose every supported config-entry workflow from the user menu.

    Args:
        hass (HomeAssistant): Home Assistant instance that owns the flow.
    """
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "user"
    assert result["menu_options"] == [
        "add_sensor",
        "add_binary_sensor",
        "add_device_tracker",
        "add_device",
    ]


async def test_sensor_flow_creates_typed_entry(hass: HomeAssistant) -> None:
    """Create a numeric sensor through both pages of the real flow API.

    Args:
        hass (HomeAssistant): Home Assistant instance that owns the flow.
    """
    result = await _start_sensor_flow(
        hass,
        {
            CONF_VARIABLE_ID: "outside_temperature",
            CONF_NAME: "Outside Temperature",
            CONF_ICON: "mdi:thermometer",
            CONF_DEVICE_CLASS: "temperature",
            CONF_RESTORE: True,
            CONF_FORCE_UPDATE: False,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "sensor_page_2"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_VALUE: "23.5",
            CONF_ATTRIBUTES: {"source": "flow"},
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Outside Temperature"
    assert result["data"] == {
        CONF_VARIABLE_ID: "outside_temperature",
        CONF_NAME: "Outside Temperature",
        CONF_ICON: "mdi:thermometer",
        CONF_DEVICE_CLASS: "temperature",
        CONF_RESTORE: True,
        CONF_FORCE_UPDATE: False,
        CONF_EXCLUDE_FROM_RECORDER: False,
        CONF_ENTITY_PLATFORM: Platform.SENSOR,
        CONF_YAML_VARIABLE: False,
        CONF_VALUE_TYPE: "number",
        CONF_VALUE: 23.5,
        CONF_ATTRIBUTES: {"source": "flow"},
    }
    await hass.async_block_till_done()
    state = hass.states.get("sensor.outside_temperature")
    assert state is not None
    assert state.state == "23.5"
    assert state.attributes["source"] == "flow"
    registry_entry = er.async_get(hass).async_get("sensor.outside_temperature")
    assert registry_entry is not None
    assert registry_entry.config_entry_id == result["result"].entry_id


@pytest.mark.parametrize(
    (
        "variable_id",
        "device_class",
        "page_2_input",
        "expected_value_type",
        "expected_value",
        "expected_state",
        "expected_attributes",
    ),
    [
        pytest.param(
            "typed_date",
            SensorDeviceClass.DATE,
            {CONF_VALUE: "2026-07-23", CONF_ATTRIBUTES: {"source": "flow"}},
            "date",
            datetime.date(2026, 7, 23),
            "2026-07-23",
            {"device_class": SensorDeviceClass.DATE, "source": "flow"},
            id="date",
        ),
        pytest.param(
            "typed_timestamp_positive",
            SensorDeviceClass.TIMESTAMP,
            {
                CONF_VALUE: "2026-07-23 10:15:00",
                CONF_TZOFFSET: "+0530",
                CONF_ATTRIBUTES: {"source": "flow"},
            },
            "datetime",
            datetime.datetime(
                2026,
                7,
                23,
                10,
                15,
                tzinfo=datetime.timezone(datetime.timedelta(hours=5, minutes=30)),
            ),
            "2026-07-23T04:45:00+00:00",
            {"device_class": SensorDeviceClass.TIMESTAMP, "source": "flow"},
            id="timestamp-positive-offset",
        ),
        pytest.param(
            "typed_timestamp_negative",
            SensorDeviceClass.TIMESTAMP,
            {
                CONF_VALUE: "2026-07-23 10:15:00",
                CONF_TZOFFSET: "-0400",
                CONF_ATTRIBUTES: {"source": "flow"},
            },
            "datetime",
            datetime.datetime(
                2026,
                7,
                23,
                10,
                15,
                tzinfo=datetime.timezone(datetime.timedelta(hours=-4)),
            ),
            "2026-07-23T14:15:00+00:00",
            {"device_class": SensorDeviceClass.TIMESTAMP, "source": "flow"},
            id="timestamp-negative-offset",
        ),
        pytest.param(
            "typed_temperature",
            SensorDeviceClass.TEMPERATURE,
            {
                CONF_VALUE: "21.5",
                CONF_STATE_CLASS: SensorStateClass.MEASUREMENT,
                CONF_UNIT_OF_MEASUREMENT: "°C",
                CONF_ATTRIBUTES: {"source": "flow"},
            },
            "number",
            21.5,
            "21.5",
            {
                "device_class": SensorDeviceClass.TEMPERATURE,
                "state_class": SensorStateClass.MEASUREMENT,
                "unit_of_measurement": "°C",
                "source": "flow",
            },
            id="measurement-temperature",
        ),
        pytest.param(
            "typed_money",
            SensorDeviceClass.MONETARY,
            {
                CONF_VALUE: "19.95",
                CONF_STATE_CLASS: SensorStateClass.TOTAL,
                CONF_UNIT_OF_MEASUREMENT: "USD",
                CONF_ATTRIBUTES: {"source": "flow"},
            },
            "number",
            19.95,
            "19.95",
            {
                "device_class": SensorDeviceClass.MONETARY,
                "state_class": SensorStateClass.TOTAL,
                "unit_of_measurement": "USD",
                "source": "flow",
            },
            id="monetary",
        ),
    ],
)
async def test_typed_sensor_flow_matrix(
    hass: HomeAssistant,
    variable_id: str,
    device_class: SensorDeviceClass,
    page_2_input: dict[str, Any],
    expected_value_type: str,
    expected_value: object,
    expected_state: str,
    expected_attributes: dict[str, Any],
) -> None:
    """Create typed sensors through the public flow and expose their live state.

    Args:
        hass (HomeAssistant): Home Assistant instance that owns the flow.
        variable_id (str): Unique identifier for the variable under test.
        device_class (SensorDeviceClass): Sensor device class that determines value validation.
        page_2_input (dict[str, Any]): Data submitted to the sensor flow's second page.
        expected_value_type (str): Expected stored variable value type.
        expected_value (object): Expected stored variable value.
        expected_state (str): Expected Home Assistant entity state.
        expected_attributes (dict[str, Any]): Expected attributes exposed by the entity.
    """
    result = await _start_sensor_flow(
        hass,
        {
            CONF_VARIABLE_ID: variable_id,
            CONF_NAME: variable_id.replace("_", " ").title(),
            CONF_DEVICE_CLASS: device_class,
        },
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=page_2_input
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_DEVICE_CLASS] == device_class
    assert result["data"][CONF_VALUE_TYPE] == expected_value_type
    assert result["data"][CONF_VALUE] == expected_value
    for key in (CONF_STATE_CLASS, CONF_UNIT_OF_MEASUREMENT, CONF_TZOFFSET):
        if key in page_2_input:
            assert result["data"][key] == page_2_input[key]

    await hass.async_block_till_done()
    entity_id = f"sensor.{variable_id}"
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == expected_state
    assert {key: state.attributes[key] for key in expected_attributes} == expected_attributes
    registry_entry = er.async_get(hass).async_get(entity_id)
    assert registry_entry is not None
    assert registry_entry.config_entry_id == result["result"].entry_id


@pytest.mark.parametrize(
    ("variable_id", "device_class", "invalid_value", "raises_invalid_data"),
    [
        pytest.param(
            "bad_date",
            SensorDeviceClass.DATE,
            "2026-02-30",
            True,
            id="date",
        ),
        pytest.param(
            "bad_timestamp",
            SensorDeviceClass.TIMESTAMP,
            "not-a-timestamp",
            True,
            id="timestamp",
        ),
        pytest.param(
            "bad_numeric",
            SensorDeviceClass.TEMPERATURE,
            "warm",
            False,
            id="numeric",
        ),
    ],
)
async def test_typed_sensor_flow_rejects_incompatible_values(
    hass: HomeAssistant,
    variable_id: str,
    device_class: SensorDeviceClass,
    invalid_value: str,
    raises_invalid_data: bool,
) -> None:
    """Keep typed sensor flows open and entry-free for incompatible values.

    Args:
        hass (HomeAssistant): Home Assistant instance that owns the flow.
        variable_id (str): Unique identifier for the variable under test.
        device_class (SensorDeviceClass): Sensor device class that determines value validation.
        invalid_value (str): Value that is incompatible with the device class.
        raises_invalid_data (bool): Whether the flow is expected to raise InvalidData.
    """
    result = await _start_sensor_flow(
        hass,
        {
            CONF_VARIABLE_ID: variable_id,
            CONF_DEVICE_CLASS: device_class,
        },
    )
    flow_id = result["flow_id"]
    if raises_invalid_data:
        with pytest.raises(InvalidData) as err:
            await hass.config_entries.flow.async_configure(
                flow_id, user_input={CONF_VALUE: invalid_value}
            )
        assert err.value.schema_errors[CONF_VALUE]
        result = await hass.config_entries.flow.async_configure(flow_id)
        assert result["errors"] == {}
    else:
        result = await hass.config_entries.flow.async_configure(
            flow_id, user_input={CONF_VALUE: invalid_value}
        )
        assert result["errors"] == {"base": "invalid_value_type"}

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "sensor_page_2"
    assert not hass.config_entries.async_entries(DOMAIN)
    assert hass.states.get(f"sensor.{variable_id}") is None


async def test_yaml_import_discards_incompatible_typed_value(hass: HomeAssistant) -> None:
    """Discard a YAML value that is incompatible with its sensor device class.

    Args:
        hass (HomeAssistant): Home Assistant instance that owns the flow.
    """
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_IMPORT},
        data={
            CONF_VARIABLE_ID: "bad_yaml_temperature",
            CONF_VALUE: "warm",
            CONF_ATTRIBUTES: {CONF_DEVICE_CLASS: SensorDeviceClass.TEMPERATURE},
        },
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_VALUE_TYPE] == "number"
    assert CONF_VALUE not in result["data"]


@pytest.mark.parametrize(
    ("invalid_input", "error_key"),
    [
        pytest.param(
            {CONF_STATE_CLASS: SensorStateClass.TOTAL},
            CONF_STATE_CLASS,
            id="state-class",
        ),
        pytest.param(
            {CONF_UNIT_OF_MEASUREMENT: "USD"},
            CONF_UNIT_OF_MEASUREMENT,
            id="unit",
        ),
    ],
)
async def test_temperature_flow_rejects_invalid_typed_selection(
    hass: HomeAssistant,
    invalid_input: dict[str, Any],
    error_key: str,
) -> None:
    """Reject state classes and units not offered by the typed sensor page.

    Args:
        hass (HomeAssistant): Home Assistant instance that owns the flow.
        invalid_input (dict[str, Any]): Invalid data submitted to the sensor flow's second page.
        error_key (str): Schema field expected to report the validation error.
    """
    result = await _start_sensor_flow(
        hass,
        {
            CONF_VARIABLE_ID: f"bad_temperature_{error_key}",
            CONF_DEVICE_CLASS: SensorDeviceClass.TEMPERATURE,
        },
    )
    flow_id = result["flow_id"]

    with pytest.raises(InvalidData) as err:
        await hass.config_entries.flow.async_configure(
            flow_id,
            user_input={CONF_VALUE: "21.5", **invalid_input},
        )

    assert error_key in err.value.schema_errors
    result = await hass.config_entries.flow.async_configure(flow_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "sensor_page_2"
    assert not hass.config_entries.async_entries(DOMAIN)


@pytest.mark.parametrize(
    ("step_id", "user_input", "expected_platform", "expected_entity_id", "expected_state"),
    [
        pytest.param(
            "add_binary_sensor",
            {
                CONF_VARIABLE_ID: "garage_open",
                CONF_NAME: "Garage Open",
                CONF_VALUE: "true",
                CONF_DEVICE_CLASS: BinarySensorDeviceClass.GARAGE_DOOR,
            },
            Platform.BINARY_SENSOR,
            "binary_sensor.garage_open",
            "on",
            id="binary-sensor",
        ),
        pytest.param(
            "add_device_tracker",
            {
                CONF_VARIABLE_ID: "test_tracker",
                CONF_NAME: "Test Tracker",
                ATTR_LATITUDE: 40.0,
                ATTR_LONGITUDE: -75.0,
                ATTR_GPS_ACCURACY: 12,
                ATTR_BATTERY_LEVEL: 87,
            },
            Platform.DEVICE_TRACKER,
            "device_tracker.test_tracker",
            "not_home",
            id="device-tracker",
        ),
        pytest.param(
            "add_device",
            {
                CONF_NAME: "Virtual Hub",
                "manufacturer": "Variables",
                "configuration_url": "https://example.com/device",
            },
            CONF_DEVICE,
            None,
            None,
            id="device",
        ),
    ],
)
async def test_single_page_flows_create_entries(
    hass: HomeAssistant,
    step_id: str,
    user_input: dict[str, Any],
    expected_platform: str,
    expected_entity_id: str | None,
    expected_state: str | None,
) -> None:
    """Create and fully set up each single-page config flow.

    Args:
        hass (HomeAssistant): Home Assistant instance that owns the flow.
        step_id (str): Menu option that selects the config-flow step.
        user_input (dict[str, Any]): Data submitted to the selected flow step.
        expected_platform (str): Expected platform stored in the config entry.
        expected_entity_id (str | None): Expected entity ID, if the flow creates an entity.
        expected_state (str | None): Expected entity state, if the flow creates an entity.
    """
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"next_step_id": step_id}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input=user_input
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_ENTITY_PLATFORM] == expected_platform
    assert result["data"][CONF_YAML_VARIABLE] is False
    await hass.async_block_till_done()

    entry = result["result"]
    if expected_entity_id is not None:
        state = hass.states.get(expected_entity_id)
        assert state is not None
        assert state.state == expected_state
        registry_entry = er.async_get(hass).async_get(expected_entity_id)
        assert registry_entry is not None
        assert registry_entry.config_entry_id == entry.entry_id
    else:
        device = _get_device_for_entry(dr.async_get(hass), entry)
        assert device is not None
        assert device.name == "Virtual Hub"
        assert device.manufacturer == "Variables"
        assert str(device.configuration_url) == "https://example.com/device"


async def test_device_flow_rejects_invalid_configuration_url(hass: HomeAssistant) -> None:
    """Report an invalid URL without creating a device config entry.

    Args:
        hass (HomeAssistant): Home Assistant instance that owns the flow.
    """
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input={"next_step_id": "add_device"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={
            CONF_NAME: "Invalid Device",
            "configuration_url": "not a URL",
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "add_device"
    assert result["errors"] == {"base": "invalid_url"}


async def test_add_sensor_normalizes_enum_name_device_class(hass: HomeAssistant) -> None:
    """Build typed state-class and unit choices from a device-class enum name.

    Args:
        hass (HomeAssistant): Home Assistant instance that owns the flow.
    """
    flow = VariableConfigFlow()
    flow.hass = hass
    flow.add_sensor_input = {
        CONF_VARIABLE_ID: "enum_name_temperature",
        CONF_DEVICE_CLASS: SensorDeviceClass.TEMPERATURE.name,
    }

    data_schema = flow.build_add_sensor_page_2()
    selectors = {getattr(key, "schema", key): value for key, value in data_schema.schema.items()}

    state_class_options = selectors[CONF_STATE_CLASS].config["options"]
    assert state_class_options[0] == {"label": "None", "value": "None"}
    assert {(option["label"], option["value"]) for option in state_class_options[1:]} == {
        ("MEASUREMENT", "measurement")
    }
    assert {
        option["value"] for option in selectors[CONF_UNIT_OF_MEASUREMENT].config["options"]
    } == {
        "None",
        "K",
        "°C",
        "°F",
    }


async def test_yaml_entry_aborts_options_flow(hass: HomeAssistant) -> None:
    """Reject options for a variable managed through YAML.

    Args:
        hass (HomeAssistant): Home Assistant instance that hosts the integration.
    """
    assert await async_setup_component(
        hass,
        DOMAIN,
        {DOMAIN: {"yaml_managed": {CONF_VALUE: "managed"}}},
    )
    await hass.async_block_till_done()
    entry = next(
        entry
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.data.get(CONF_VARIABLE_ID) == "yaml_managed"
    )

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "yaml_variable"


async def test_unsupported_platform_aborts_options_flow(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
) -> None:
    """Abort options cleanly when an entry has an unsupported platform.

    Args:
        hass (HomeAssistant): Home Assistant instance that hosts the integration.
        config_entry_factory (ConfigEntryFactory): Factory that creates the unsupported config entry.
    """
    entry = config_entry_factory(
        {
            CONF_ENTITY_PLATFORM: "unsupported",
            CONF_VARIABLE_ID: "unsupported_platform",
            CONF_YAML_VARIABLE: False,
        }
    )

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "unknown"


async def test_options_flow_changes_loaded_sensor_value(
    hass: HomeAssistant,
    sensor_entry: ConfigEntry,
) -> None:
    """Change a live entity through the options workflow and its entity service.

    Args:
        hass (HomeAssistant): Home Assistant instance that hosts the integration.
        sensor_entry (ConfigEntry): Loaded sensor config entry to update.
    """
    assert await hass.config_entries.async_setup(sensor_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(sensor_entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["change_sensor_value", "sensor_options"]

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={"next_step_id": "change_sensor_value"},
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_VALUE: "24.25", "attributes": {"source": "options"}},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "value_changed"
    state = hass.states.get("sensor.office_temperature")
    assert state is not None
    assert state.state == "24.25"
    assert state.attributes["source"] == "options"


async def test_options_flow_rejects_invalid_typed_sensor_value(
    hass: HomeAssistant,
    sensor_entry: ConfigEntry,
) -> None:
    """Redisplay the change-value form when typed conversion fails.

    Args:
        hass (HomeAssistant): Home Assistant instance that hosts the integration.
        sensor_entry (ConfigEntry): Loaded numeric sensor config entry to update.
    """
    assert await hass.config_entries.async_setup(sensor_entry.entry_id)
    await hass.async_block_till_done()
    original_state = hass.states.get("sensor.office_temperature")
    assert original_state is not None
    original_value = original_state.state

    result = await hass.config_entries.options.async_init(sensor_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={"next_step_id": "change_sensor_value"},
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_VALUE: "not-a-number", "attributes": {"source": "bad"}},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "change_sensor_value"
    assert result["errors"] == {"base": "invalid_value_type"}
    state = hass.states.get("sensor.office_temperature")
    assert state is not None
    assert state.state == original_value
    assert state.attributes["source"] == "test"


@pytest.mark.parametrize(
    ("tz_offset", "expected_state"),
    [
        pytest.param("+0530", "2026-08-11T06:30:00+00:00", id="explicit-offset"),
        pytest.param("bad", "2026-08-11T12:00:00+00:00", id="invalid-falls-back-utc"),
        pytest.param(None, "2026-08-11T12:00:00+00:00", id="missing-falls-back-utc"),
    ],
)
async def test_options_flow_change_sensor_value_applies_timezone_offset(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
    tz_offset: str | None,
    expected_state: str,
) -> None:
    """Append a valid timezone offset or default UTC when updating datetimes.

    Args:
        hass (HomeAssistant): Home Assistant instance that hosts the integration.
        config_entry_factory (ConfigEntryFactory): Factory that creates the config entry.
        tz_offset (str | None): Submitted timezone offset, or None when omitted.
        expected_state (str): Expected ISO datetime state after conversion.
    """
    entry = config_entry_factory(
        {
            CONF_ENTITY_PLATFORM: Platform.SENSOR,
            CONF_VARIABLE_ID: "timestamp_options",
            CONF_YAML_VARIABLE: False,
            CONF_NAME: "Timestamp Options",
            CONF_RESTORE: False,
            CONF_FORCE_UPDATE: False,
            CONF_VALUE: "2026-08-10 00:00:00+0000",
            CONF_VALUE_TYPE: "datetime",
            CONF_DEVICE_CLASS: SensorDeviceClass.TIMESTAMP,
            CONF_ATTRIBUTES: {"source": "initial"},
        }
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={"next_step_id": "change_sensor_value"},
    )
    assert result["type"] is FlowResultType.FORM

    user_input: dict[str, Any] = {
        CONF_VALUE: "2026-08-11 12:00:00",
        "attributes": {"source": "options"},
    }
    if tz_offset is not None:
        user_input[CONF_TZOFFSET] = tz_offset

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input=user_input,
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "value_changed"
    state = hass.states.get("sensor.timestamp_options")
    assert state is not None
    assert state.state == expected_state
    assert state.attributes["source"] == "options"


@pytest.mark.parametrize(
    ("entry_data", "entity_id", "step_id", "user_input"),
    [
        pytest.param(
            {
                CONF_ENTITY_PLATFORM: Platform.SENSOR,
                CONF_VARIABLE_ID: "missing_sensor",
                CONF_YAML_VARIABLE: False,
                CONF_VALUE: 21.5,
                CONF_VALUE_TYPE: "number",
            },
            "sensor.missing_sensor",
            "change_sensor_value",
            {CONF_VALUE: "24.25"},
            id="sensor",
        ),
        pytest.param(
            {
                CONF_ENTITY_PLATFORM: Platform.BINARY_SENSOR,
                CONF_VARIABLE_ID: "missing_binary_sensor",
                CONF_YAML_VARIABLE: False,
                CONF_VALUE: "true",
            },
            "binary_sensor.missing_binary_sensor",
            "change_binary_sensor_value",
            {CONF_VALUE: "false"},
            id="binary-sensor",
        ),
        pytest.param(
            {
                CONF_ENTITY_PLATFORM: Platform.DEVICE_TRACKER,
                CONF_VARIABLE_ID: "missing_device_tracker",
                CONF_YAML_VARIABLE: False,
                ATTR_LATITUDE: 40.0,
                ATTR_LONGITUDE: -75.0,
            },
            "device_tracker.missing_device_tracker",
            "change_device_tracker_value",
            {ATTR_LATITUDE: 41.5, ATTR_LONGITUDE: -74.5},
            id="device-tracker",
        ),
    ],
)
async def test_change_value_submission_aborts_when_runtime_entity_disappears(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
    entry_data: dict[str, Any],
    entity_id: str,
    step_id: str,
    user_input: dict[str, Any],
) -> None:
    """Abort submitted value changes when the runtime entity has disappeared.

    Args:
        hass (HomeAssistant): Home Assistant instance that hosts the integration.
        config_entry_factory (ConfigEntryFactory): Factory that creates the config entry.
        entry_data (dict[str, Any]): Platform-specific config-entry data.
        entity_id (str): Runtime entity to remove before submission.
        step_id (str): Platform-specific change-value options step.
        user_input (dict[str, Any]): Platform-specific submitted value data.
    """
    entry = config_entry_factory(entry_data)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input={"next_step_id": step_id}
    )
    assert result["type"] is FlowResultType.FORM

    hass.states.async_remove(entity_id)
    with patch.object(type(hass.services), "async_call", new_callable=AsyncMock) as async_call:
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], user_input=user_input
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "entity_not_found"
    async_call.assert_not_awaited()


async def test_sensor_options_flow_updates_entry_and_live_entity(
    hass: HomeAssistant,
    sensor_entry: ConfigEntry,
) -> None:
    """Persist both sensor option pages and reload the live entity.

    Args:
        hass (HomeAssistant): Home Assistant instance that hosts the integration.
        sensor_entry (ConfigEntry): Loaded sensor config entry to update.
    """
    assert await hass.config_entries.async_setup(sensor_entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(sensor_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={"next_step_id": "sensor_options"},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "sensor_options"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            "device_class": "None",
            CONF_RESTORE: False,
            CONF_FORCE_UPDATE: True,
            CONF_EXCLUDE_FROM_RECORDER: True,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "sensor_options_page_2"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_VALUE: "26.5",
            CONF_ATTRIBUTES: {"source": "sensor-options"},
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert sensor_entry.data[CONF_VALUE] == "26.5"
    assert sensor_entry.data[CONF_FORCE_UPDATE] is True
    assert sensor_entry.data[CONF_EXCLUDE_FROM_RECORDER] is True
    assert sensor_entry.data[CONF_ATTRIBUTES] == {"source": "sensor-options"}
    state = hass.states.get("sensor.office_temperature")
    assert state is not None
    assert state.state == "26.5"
    assert state.attributes["source"] == "sensor-options"
    assert state.state_info is not None
    assert MATCH_ALL in state.state_info["unrecorded_attributes"]


async def test_sensor_options_normalizes_string_device_class(
    hass: HomeAssistant,
    sensor_entry: ConfigEntry,
) -> None:
    """Expose state-class choices for a string-valued sensor device class.

    Args:
        hass (HomeAssistant): Home Assistant instance that hosts the integration.
        sensor_entry (ConfigEntry): Sensor config entry whose options flow is under test.
    """
    result = await hass.config_entries.options.async_init(sensor_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={"next_step_id": "sensor_options"},
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_DEVICE_CLASS: SensorDeviceClass.TEMPERATURE.value,
            CONF_RESTORE: False,
            CONF_FORCE_UPDATE: False,
            CONF_EXCLUDE_FROM_RECORDER: False,
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "sensor_options_page_2"
    data_schema = result["data_schema"]
    assert data_schema is not None
    state_class_selector = next(
        value
        for key, value in data_schema.schema.items()
        if getattr(key, "schema", key) == CONF_STATE_CLASS
    )
    state_class_options = state_class_selector.config["options"]
    assert state_class_options[0] == {"label": "None", "value": "None"}
    assert {(option["label"], option["value"]) for option in state_class_options[1:]} == {
        ("MEASUREMENT", "measurement")
    }


async def test_sensor_pages_use_identical_monetary_unit_options(
    hass: HomeAssistant,
    sensor_entry: ConfigEntry,
) -> None:
    """Expose the same labeled currency choices in add and options flows.

    Args:
        hass (HomeAssistant): Home Assistant instance that hosts the integration.
        sensor_entry (ConfigEntry): Sensor config entry whose options flow is under test.
    """
    add_flow = VariableConfigFlow()
    add_flow.hass = hass
    add_flow.add_sensor_input = {
        CONF_VARIABLE_ID: "monetary_parity",
        CONF_DEVICE_CLASS: SensorDeviceClass.MONETARY.name,
    }
    add_schema = add_flow.build_add_sensor_page_2()
    add_unit_selector = next(
        value
        for key, value in add_schema.schema.items()
        if getattr(key, "schema", key) == CONF_UNIT_OF_MEASUREMENT
    )

    result = await hass.config_entries.options.async_init(sensor_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={"next_step_id": "sensor_options"},
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_DEVICE_CLASS: SensorDeviceClass.MONETARY.value,
            CONF_RESTORE: False,
            CONF_FORCE_UPDATE: False,
            CONF_EXCLUDE_FROM_RECORDER: False,
        },
    )

    assert result["type"] is FlowResultType.FORM
    data_schema = result["data_schema"]
    assert data_schema is not None
    options_unit_selector = next(
        value
        for key, value in data_schema.schema.items()
        if getattr(key, "schema", key) == CONF_UNIT_OF_MEASUREMENT
    )
    assert options_unit_selector.config["options"] == add_unit_selector.config["options"]
    assert {"label": "US Dollar [USD]", "value": "USD"} in add_unit_selector.config["options"]


async def test_binary_sensor_options_update_entry_and_live_entity(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
) -> None:
    """Persist binary sensor options and reload its state and attributes.

    Args:
        hass (HomeAssistant): Home Assistant instance that hosts the integration.
        config_entry_factory (ConfigEntryFactory): Factory that creates the binary-sensor config entry.
    """
    entry = config_entry_factory(
        {
            CONF_ENTITY_PLATFORM: Platform.BINARY_SENSOR,
            CONF_VARIABLE_ID: "configured_binary",
            CONF_NAME: "Configured Binary",
            CONF_VALUE: "true",
            CONF_YAML_VARIABLE: False,
            CONF_RESTORE: False,
            CONF_FORCE_UPDATE: False,
        }
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={"next_step_id": "binary_sensor_options"},
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_VALUE: "false",
            CONF_ATTRIBUTES: {"source": "binary-options-form"},
            "device_class": "door",
            CONF_RESTORE: False,
            CONF_FORCE_UPDATE: True,
            CONF_EXCLUDE_FROM_RECORDER: False,
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_VALUE] == "false"
    assert entry.data["device_class"] == "door"
    assert entry.data[CONF_ATTRIBUTES] == {"source": "binary-options-form"}
    assert entry.data[CONF_RESTORE] is False
    assert entry.data[CONF_FORCE_UPDATE] is True
    assert entry.data[CONF_EXCLUDE_FROM_RECORDER] is False
    state = hass.states.get("binary_sensor.configured_binary")
    assert state is not None
    assert state.state == "off"
    assert state.attributes["source"] == "binary-options-form"


async def test_device_tracker_options_update_entry_and_live_entity(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
) -> None:
    """Persist tracker options and reload its coordinates and attributes.

    Args:
        hass (HomeAssistant): Home Assistant instance that hosts the integration.
        config_entry_factory (ConfigEntryFactory): Factory that creates the device-tracker config entry.
    """
    entry = config_entry_factory(
        {
            CONF_ENTITY_PLATFORM: Platform.DEVICE_TRACKER,
            CONF_VARIABLE_ID: "configured_tracker",
            CONF_NAME: "Configured Tracker",
            CONF_YAML_VARIABLE: False,
            ATTR_LATITUDE: 40.0,
            ATTR_LONGITUDE: -75.0,
            ATTR_GPS_ACCURACY: 10,
            ATTR_BATTERY_LEVEL: 80,
            CONF_RESTORE: False,
            CONF_FORCE_UPDATE: False,
        }
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={"next_step_id": "device_tracker_options"},
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            ATTR_LATITUDE: 41.25,
            ATTR_LONGITUDE: -74.75,
            ATTR_LOCATION_NAME: "Studio",
            ATTR_GPS_ACCURACY: 4,
            ATTR_BATTERY_LEVEL: 65,
            CONF_ATTRIBUTES: {"source": "tracker-options-form"},
            CONF_RESTORE: False,
            CONF_FORCE_UPDATE: True,
            CONF_EXCLUDE_FROM_RECORDER: False,
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.data[ATTR_LATITUDE] == 41.25
    assert entry.data[ATTR_LONGITUDE] == -74.75
    assert entry.data[ATTR_LOCATION_NAME] == "Studio"
    assert entry.data[CONF_ATTRIBUTES] == {"source": "tracker-options-form"}
    assert entry.data[CONF_RESTORE] is False
    assert entry.data[CONF_FORCE_UPDATE] is True
    assert entry.data[CONF_EXCLUDE_FROM_RECORDER] is False
    state = hass.states.get("device_tracker.configured_tracker")
    assert state is not None
    assert state.state == STATE_NOT_HOME
    assert state.attributes[ATTR_LOCATION_NAME] == "Studio"
    assert state.attributes[ATTR_LATITUDE] == 41.25
    assert state.attributes[ATTR_LONGITUDE] == -74.75
    assert state.attributes[ATTR_GPS_ACCURACY] == 4
    assert state.attributes[ATTR_BATTERY_LEVEL] == 65
    assert state.attributes["source"] == "tracker-options-form"


async def test_binary_sensor_options_flow_changes_live_entity(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
) -> None:
    """Change binary state and attributes through the options workflow.

    Args:
        hass (HomeAssistant): Home Assistant instance that hosts the integration.
        config_entry_factory (ConfigEntryFactory): Factory that creates the binary-sensor config entry.
    """
    entry = config_entry_factory(
        {
            CONF_ENTITY_PLATFORM: Platform.BINARY_SENSOR,
            CONF_VARIABLE_ID: "options_binary",
            CONF_NAME: "Options Binary",
            CONF_VALUE: "true",
            CONF_YAML_VARIABLE: False,
            "restore": False,
            "force_update": False,
        }
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={"next_step_id": "change_binary_sensor_value"},
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={CONF_VALUE: "false", "attributes": {"source": "binary-options"}},
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "value_changed"
    state = hass.states.get("binary_sensor.options_binary")
    assert state is not None
    assert state.state == "off"
    assert state.attributes["source"] == "binary-options"


async def test_device_tracker_options_flow_changes_live_entity(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
) -> None:
    """Change tracker coordinates and metadata through the options workflow.

    Args:
        hass (HomeAssistant): Home Assistant instance that hosts the integration.
        config_entry_factory (ConfigEntryFactory): Factory that creates the device-tracker config entry.
    """
    entry = config_entry_factory(
        {
            CONF_ENTITY_PLATFORM: Platform.DEVICE_TRACKER,
            CONF_VARIABLE_ID: "options_tracker",
            CONF_NAME: "Options Tracker",
            CONF_YAML_VARIABLE: False,
            ATTR_LATITUDE: 40.0,
            ATTR_LONGITUDE: -75.0,
            ATTR_GPS_ACCURACY: 10,
            ATTR_BATTERY_LEVEL: 80,
            "restore": False,
            "force_update": False,
        }
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={"next_step_id": "change_device_tracker_value"},
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            ATTR_LATITUDE: 41.5,
            ATTR_LONGITUDE: -74.5,
            ATTR_GPS_ACCURACY: 6,
            ATTR_BATTERY_LEVEL: 72,
            "attributes": {"source": "tracker-options"},
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "value_changed"
    state = hass.states.get("device_tracker.options_tracker")
    assert state is not None
    assert state.attributes[ATTR_LATITUDE] == 41.5
    assert state.attributes[ATTR_LONGITUDE] == -74.5
    assert state.attributes[ATTR_GPS_ACCURACY] == 6
    assert state.attributes[ATTR_BATTERY_LEVEL] == 72
    assert state.attributes["source"] == "tracker-options"


async def test_device_tracker_options_flow_sets_in_zones_state(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
) -> None:
    """Set tracker state from zone membership through the options workflow.

    Args:
        hass (HomeAssistant): Home Assistant instance that hosts the integration.
        config_entry_factory (ConfigEntryFactory): Factory that creates the device-tracker config entry.
    """
    entity_id = "device_tracker.options_zone_tracker"
    zone_id = "zone.workshop"
    hass.states.async_set(
        zone_id,
        "zoning",
        {
            "friendly_name": "Workshop Zone",
            "latitude": 41.5,
            "longitude": -74.5,
            "radius": 100,
            "passive": False,
        },
    )
    entry = config_entry_factory(
        {
            CONF_ENTITY_PLATFORM: Platform.DEVICE_TRACKER,
            CONF_VARIABLE_ID: "options_zone_tracker",
            CONF_NAME: "Options Zone Tracker",
            CONF_YAML_VARIABLE: False,
            ATTR_LATITUDE: 40.0,
            ATTR_LONGITUDE: -75.0,
            "restore": False,
            "force_update": False,
        }
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={"next_step_id": "change_device_tracker_value"},
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            ATTR_LATITUDE: 40.0,
            ATTR_LONGITUDE: -75.0,
            ATTR_IN_ZONES: [zone_id],
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "value_changed"
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "Workshop Zone"
    assert state.attributes[ATTR_IN_ZONES] == [zone_id]


async def test_device_tracker_options_flow_clears_in_zones(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
) -> None:
    """Clear explicit zone membership from the options workflow.

    Args:
        hass (HomeAssistant): Home Assistant instance that hosts the integration.
        config_entry_factory (ConfigEntryFactory): Factory that creates the device-tracker config entry.
    """
    entity_id = "device_tracker.options_clear_zones"
    zone_id = "zone.workshop"
    hass.states.async_set(
        zone_id,
        "zoning",
        {
            "friendly_name": "Workshop Zone",
            "latitude": 41.5,
            "longitude": -74.5,
            "radius": 100,
            "passive": False,
        },
    )
    entry = config_entry_factory(
        {
            CONF_ENTITY_PLATFORM: Platform.DEVICE_TRACKER,
            CONF_VARIABLE_ID: "options_clear_zones",
            CONF_YAML_VARIABLE: False,
            ATTR_LATITUDE: 40.0,
            ATTR_LONGITUDE: -75.0,
            "restore": False,
            "force_update": False,
        }
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_UPDATE_DEVICE_TRACKER,
        {"entity_id": [entity_id], ATTR_IN_ZONES: [zone_id]},
        blocking=True,
    )
    zoned = hass.states.get(entity_id)
    assert zoned is not None
    assert zoned.state == "Workshop Zone"

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={"next_step_id": "change_device_tracker_value"},
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            ATTR_LATITUDE: 40.0,
            ATTR_LONGITUDE: -75.0,
            ATTR_DELETE_IN_ZONES: True,
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "value_changed"
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state != "Workshop Zone"
    assert state.attributes.get(ATTR_IN_ZONES) == []


async def test_change_device_tracker_value_accepts_zero_coordinates(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
) -> None:
    """Preserve zero latitude/longitude and zero battery/accuracy from options.

    Args:
        hass (HomeAssistant): Home Assistant instance that hosts the integration.
        config_entry_factory (ConfigEntryFactory): Factory that creates the device-tracker config entry.
    """
    entry = config_entry_factory(
        {
            CONF_ENTITY_PLATFORM: Platform.DEVICE_TRACKER,
            CONF_VARIABLE_ID: "zero_tracker",
            CONF_NAME: "Zero Tracker",
            CONF_YAML_VARIABLE: False,
            ATTR_LATITUDE: 40.0,
            ATTR_LONGITUDE: -75.0,
            ATTR_GPS_ACCURACY: 10,
            ATTR_BATTERY_LEVEL: 80,
            "restore": False,
            "force_update": False,
        }
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={"next_step_id": "change_device_tracker_value"},
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            ATTR_LATITUDE: 0.0,
            ATTR_LONGITUDE: 0.0,
            ATTR_GPS_ACCURACY: 0,
            ATTR_BATTERY_LEVEL: 0,
            "attributes": {"source": "zero-options"},
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "value_changed"
    state = hass.states.get("device_tracker.zero_tracker")
    assert state is not None
    assert state.attributes[ATTR_LATITUDE] == 0.0
    assert state.attributes[ATTR_LONGITUDE] == 0.0
    assert state.attributes[ATTR_GPS_ACCURACY] == 0
    assert state.attributes[ATTR_BATTERY_LEVEL] == 0
    assert state.attributes["source"] == "zero-options"


async def test_device_options_flow_updates_registry_metadata(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
) -> None:
    """Persist device options and update the existing registry record.

    Args:
        hass (HomeAssistant): Home Assistant instance that hosts the integration.
        config_entry_factory (ConfigEntryFactory): Factory that creates the device config entry.
    """
    original_metadata = {
        "configuration_url": "https://example.com/original",
        "hw_version": "1",
        "manufacturer": "Original",
        "model": "Original Model",
        "model_id": "original-model",
        "serial_number": "original-serial",
        "sw_version": "1.0",
    }
    updated_metadata = {
        "configuration_url": "https://example.com/updated",
        "hw_version": "2",
        "manufacturer": "Updated",
        "model": "Updated Model",
        "model_id": "updated-model",
        "serial_number": "updated-serial",
        "sw_version": "2.0",
    }
    entry = config_entry_factory(
        {
            CONF_ENTITY_PLATFORM: CONF_DEVICE,
            CONF_NAME: "Options Hub",
            CONF_YAML_VARIABLE: False,
            **original_metadata,
        }
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = dr.async_get(hass)
    original_device = _get_device_for_entry(registry, entry)
    assert original_device is not None
    assert {
        key: str(getattr(original_device, key)) for key in original_metadata
    } == original_metadata

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "device_options"
    schema = result["data_schema"]
    assert schema is not None
    assert schema({}) == original_metadata
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input=dict(updated_metadata)
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert {key: entry.data[key] for key in updated_metadata} == updated_metadata
    device = _get_device_for_entry(registry, entry)
    assert device is not None
    assert device.id == original_device.id
    assert {key: str(getattr(device, key)) for key in updated_metadata} == updated_metadata


async def test_device_options_invalid_url_preserves_entry_and_registry(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
) -> None:
    """Keep device data unchanged when its options URL is invalid.

    Args:
        hass (HomeAssistant): Home Assistant instance that hosts the integration.
        config_entry_factory (ConfigEntryFactory): Factory that creates the device config entry.
    """
    entry = config_entry_factory(
        {
            CONF_ENTITY_PLATFORM: CONF_DEVICE,
            CONF_NAME: "Preserved Hub",
            CONF_YAML_VARIABLE: False,
            "manufacturer": "Original",
            "model": "Original Model",
            "configuration_url": "https://example.com/original",
        }
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    registry = dr.async_get(hass)
    original_device = _get_device_for_entry(registry, entry)
    assert original_device is not None
    original_data = dict(entry.data)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            "manufacturer": "Should Not Persist",
            "model": "Should Not Persist",
            "configuration_url": "not a URL",
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "device_options"
    assert result["errors"] == {"base": "invalid_url"}
    assert dict(entry.data) == original_data
    current_device = _get_device_for_entry(registry, entry)
    assert current_device is not None
    assert current_device.id == original_device.id
    assert current_device.manufacturer == "Original"
    assert current_device.model == "Original Model"
    assert str(current_device.configuration_url) == "https://example.com/original"
