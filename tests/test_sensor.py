"""Integration tests for Variable sensor restore and service behavior."""

from datetime import date

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_FRIENDLY_NAME,
    ATTR_UNIT_OF_MEASUREMENT,
    CONF_DEVICE,
    CONF_DEVICE_CLASS,
    CONF_DEVICE_ID,
    CONF_NAME,
    CONF_UNIT_OF_MEASUREMENT,
    Platform,
    UnitOfPower,
)
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity_platform import async_get_platforms
import pytest
from pytest_homeassistant.common import mock_restore_cache_with_extra_data

from custom_components.variable.const import (
    ATTR_ATTRIBUTES,
    ATTR_NATIVE_UNIT_OF_MEASUREMENT,
    ATTR_REPLACE_ATTRIBUTES,
    ATTR_SUGGESTED_UNIT_OF_MEASUREMENT,
    ATTR_VALUE_DELTA,
    CONF_ATTRIBUTES,
    CONF_ENTITY_PLATFORM,
    CONF_FORCE_UPDATE,
    CONF_RESTORE,
    CONF_UPDATED,
    CONF_VALUE,
    CONF_VALUE_TYPE,
    CONF_VARIABLE_ID,
    CONF_YAML_VARIABLE,
    DOMAIN,
    SERVICE_DECREMENT_SENSOR,
    SERVICE_INCREMENT_SENSOR,
    SERVICE_UPDATE_SENSOR,
)
from custom_components.variable.device import _get_device_for_entry
from custom_components.variable.sensor import Variable
from tests.types import ConfigEntryFactory

NATIVE_UNIT_NONE_WARNING = "native unit of measurement 'None'"


def _loaded_sensor(hass: HomeAssistant, entity_id: str) -> Variable:
    """Return the loaded Variable sensor entity for an entity ID.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
        entity_id (str): Entity identifier to look up.

    Returns:
        Variable: The loaded sensor entity.

    Raises:
        AssertionError: If the entity is not registered on the sensor platform.
    """
    for platform in async_get_platforms(hass, DOMAIN):
        entity = platform.entities.get(entity_id)
        if isinstance(entity, Variable):
            return entity
    raise AssertionError(f"Variable sensor {entity_id} was not loaded")


@pytest.mark.parametrize(
    ("method_name", "operation"),
    [
        pytest.param("async_increment_variable", "increment", id="increment"),
        pytest.param("async_decrement_variable", "decrement", id="decrement"),
    ],
)
@pytest.mark.parametrize(
    "current_value",
    [
        pytest.param(date(2026, 8, 8), id="date"),
        pytest.param(True, id="true"),
        pytest.param(False, id="false"),
    ],
)
async def test_numeric_services_reject_non_numeric_native_value(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
    method_name: str,
    operation: str,
    current_value: date | bool,
) -> None:
    """Reject non-numeric values before attempting numeric arithmetic.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
        config_entry_factory (ConfigEntryFactory): Factory for test configuration entries.
        method_name (str): Numeric entity method to invoke.
        operation (str): Operation name expected in the user-facing error.
        current_value (date | bool): Native value that arithmetic must reject.
    """
    entry = config_entry_factory(
        {
            CONF_VARIABLE_ID: "temporal_value",
            CONF_VALUE: 1,
            "value_type": "number",
        }
    )
    sensor = Variable(hass, dict(entry.data), entry, entry.entry_id)
    sensor._attr_native_value = current_value

    with pytest.raises(TypeError) as exc_info:
        await getattr(sensor, method_name)()

    assert str(exc_info.value) == (
        f"Cannot {operation} non-numeric value. Current value: {current_value}"
    )


async def test_sensor_restore_cache_is_applied_during_config_entry_setup(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
) -> None:
    """Restore a sensor's public state and custom attributes on startup.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
        config_entry_factory (ConfigEntryFactory): Factory for test configuration entries.
    """
    entity_id = "sensor.restored_sensor"
    restored_state = "42.5"
    restored_attributes = {"source": "sensor-cache"}
    cached_state = State(entity_id, restored_state, restored_attributes)
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                cached_state,
                {
                    "native_value": restored_state,
                    "native_unit_of_measurement": None,
                },
            )
        ],
    )
    entry = config_entry_factory(
        {
            CONF_ENTITY_PLATFORM: Platform.SENSOR,
            CONF_VARIABLE_ID: "restored_sensor",
            CONF_VALUE: 1,
            "value_type": "number",
            CONF_YAML_VARIABLE: False,
            CONF_RESTORE: True,
            CONF_FORCE_UPDATE: False,
            CONF_ATTRIBUTES: {"source": "config"},
        }
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == restored_state
    assert state.attributes["source"] == restored_attributes["source"]


async def test_sensor_empty_restore_uses_config_attributes(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
) -> None:
    """Apply configured attributes when the restore cache has none.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
        config_entry_factory (ConfigEntryFactory): Factory for test configuration entries.
    """
    entity_id = "sensor.empty_restored_sensor"
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State(entity_id, "unknown", {}),
                {
                    "native_value": None,
                    "native_unit_of_measurement": None,
                },
            )
        ],
    )
    configured_attributes = {"source": "config-fallback"}
    entry = config_entry_factory(
        {
            CONF_ENTITY_PLATFORM: Platform.SENSOR,
            CONF_VARIABLE_ID: "empty_restored_sensor",
            CONF_VALUE: 1,
            CONF_VALUE_TYPE: "number",
            CONF_YAML_VARIABLE: False,
            CONF_RESTORE: True,
            CONF_FORCE_UPDATE: False,
            CONF_ATTRIBUTES: configured_attributes,
        }
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.attributes["source"] == "config-fallback"


async def test_device_linked_sensor_name_is_not_prefixed_again_after_reload(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
) -> None:
    """Keep a device-linked sensor's friendly name stable across reload.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
        config_entry_factory (ConfigEntryFactory): Factory for test configuration entries.
    """
    entity_id = "sensor.linked_temperature"
    restored_state = "23"
    entity_name = "Linked Temperature"
    device_entry = config_entry_factory(
        {
            CONF_ENTITY_PLATFORM: CONF_DEVICE,
            CONF_NAME: "Virtual Hub",
            CONF_YAML_VARIABLE: False,
        }
    )
    assert await hass.config_entries.async_setup(device_entry.entry_id)
    await hass.async_block_till_done()
    device = _get_device_for_entry(dr.async_get(hass), device_entry)
    assert device is not None

    friendly_name = f"Virtual Hub {entity_name}"
    cached_state = State(
        entity_id,
        restored_state,
        {
            ATTR_FRIENDLY_NAME: friendly_name,
            "source": "restore-cache",
        },
    )
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                cached_state,
                {
                    "native_value": restored_state,
                    "native_unit_of_measurement": None,
                },
            )
        ],
    )
    entity_entry = config_entry_factory(
        {
            CONF_ENTITY_PLATFORM: Platform.SENSOR,
            CONF_VARIABLE_ID: "linked_temperature",
            CONF_NAME: entity_name,
            CONF_DEVICE_ID: device.id,
            CONF_VALUE: 0,
            "value_type": "number",
            CONF_YAML_VARIABLE: False,
            CONF_RESTORE: True,
            CONF_FORCE_UPDATE: False,
        }
    )

    assert await hass.config_entries.async_setup(entity_entry.entry_id)
    await hass.async_block_till_done()
    initial = hass.states.get(entity_id)
    assert initial is not None
    assert initial.attributes[ATTR_FRIENDLY_NAME] == friendly_name

    assert await hass.config_entries.async_reload(entity_entry.entry_id)
    await hass.async_block_till_done()
    reloaded = hass.states.get(entity_id)
    assert reloaded is not None
    assert reloaded.attributes[ATTR_FRIENDLY_NAME] == friendly_name


async def test_sensor_increment_and_decrement_services(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
) -> None:
    """Apply explicit and default deltas through registered sensor services.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
        config_entry_factory (ConfigEntryFactory): Factory for test configuration entries.
    """
    entry = config_entry_factory(
        {
            CONF_ENTITY_PLATFORM: Platform.SENSOR,
            CONF_VARIABLE_ID: "service_counter",
            CONF_VALUE: 10,
            "value_type": "number",
            CONF_YAML_VARIABLE: False,
            CONF_RESTORE: False,
            CONF_FORCE_UPDATE: False,
        }
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_INCREMENT_SENSOR,
        {"entity_id": ["sensor.service_counter"], ATTR_VALUE_DELTA: 2.5},
        blocking=True,
    )
    incremented = hass.states.get("sensor.service_counter")
    assert incremented is not None
    assert incremented.state == "12.5"

    await hass.services.async_call(
        DOMAIN,
        SERVICE_DECREMENT_SENSOR,
        {"entity_id": ["sensor.service_counter"]},
        blocking=True,
    )
    decremented = hass.states.get("sensor.service_counter")
    assert decremented is not None
    assert decremented.state == "11.5"


@pytest.mark.parametrize(
    "service",
    [SERVICE_INCREMENT_SENSOR, SERVICE_DECREMENT_SENSOR],
)
async def test_numeric_services_reject_string_sensor(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
    service: str,
) -> None:
    """Reject numeric services for string sensors without changing their state.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
        config_entry_factory (ConfigEntryFactory): Factory for test configuration entries.
        service (str): Numeric service expected to reject the string sensor.
    """
    entity_id = "sensor.string_value"
    entry = config_entry_factory(
        {
            CONF_ENTITY_PLATFORM: Platform.SENSOR,
            CONF_VARIABLE_ID: "string_value",
            CONF_VALUE: "unchanged",
            "value_type": "string",
            CONF_YAML_VARIABLE: False,
            CONF_RESTORE: False,
            CONF_FORCE_UPDATE: False,
        }
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    with pytest.raises(ValueError, match=r"Cannot .* non-numeric variable"):
        await hass.services.async_call(
            DOMAIN,
            service,
            {"entity_id": [entity_id]},
            blocking=True,
        )

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "unchanged"


async def test_sensor_entity_service_updates_state_and_attributes(
    hass: HomeAssistant,
    sensor_entry: ConfigEntry,
) -> None:
    """Mutate a loaded sensor through Home Assistant's registered entity service.

    Args:
        hass (HomeAssistant): Home Assistant instance that hosts the integration.
        sensor_entry (ConfigEntry): Loaded sensor config entry to update.
    """
    assert await hass.config_entries.async_setup(sensor_entry.entry_id)
    await hass.async_block_till_done()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_UPDATE_SENSOR,
        {
            "entity_id": ["sensor.office_temperature"],
            CONF_VALUE: 19,
            ATTR_ATTRIBUTES: {"service_marker": True},
            ATTR_REPLACE_ATTRIBUTES: True,
        },
        blocking=True,
    )

    state = hass.states.get("sensor.office_temperature")
    assert state is not None
    assert state.state == "19"
    assert state.attributes["service_marker"] is True
    assert "source" not in state.attributes


async def test_update_sensor_merges_nested_attributes_by_default(
    hass: HomeAssistant,
    sensor_entry: ConfigEntry,
) -> None:
    """Merge nested attribute paths without replacing existing attributes.

    Args:
        hass (HomeAssistant): Home Assistant instance that hosts the integration.
        sensor_entry (ConfigEntry): Loaded sensor config entry to update.
    """
    assert await hass.config_entries.async_setup(sensor_entry.entry_id)
    await hass.async_block_till_done()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_UPDATE_SENSOR,
        {
            "entity_id": ["sensor.office_temperature"],
            CONF_VALUE: 22,
            ATTR_ATTRIBUTES: {
                "marker": "merged",
                "items[0].name": "nested",
            },
        },
        blocking=True,
    )

    state = hass.states.get("sensor.office_temperature")
    assert state is not None
    assert state.state == "22"
    assert state.attributes["source"] == "test"
    assert state.attributes["marker"] == "merged"
    assert state.attributes["items"] == [{"name": "nested"}]


async def test_update_sensor_swallows_invalid_attribute_paths(
    hass: HomeAssistant,
    sensor_entry: ConfigEntry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Keep prior attributes and still update value when a nested path is invalid.

    Args:
        hass (HomeAssistant): Home Assistant instance that hosts the integration.
        sensor_entry (ConfigEntry): Loaded sensor config entry to update.
        caplog (pytest.LogCaptureFixture): Pytest fixture capturing log output.
    """
    assert await hass.config_entries.async_setup(sensor_entry.entry_id)
    await hass.async_block_till_done()

    with caplog.at_level("ERROR"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_UPDATE_SENSOR,
            {
                "entity_id": ["sensor.office_temperature"],
                CONF_VALUE: 18,
                ATTR_ATTRIBUTES: {"broken[path": "ignored"},
            },
            blocking=True,
        )

    state = hass.states.get("sensor.office_temperature")
    assert state is not None
    assert state.state == "18"
    assert state.attributes["source"] == "test"
    assert "broken[path" not in state.attributes
    assert "AttributeError: Invalid attribute path" in caplog.text


async def test_update_sensor_rejects_incompatible_typed_value(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
) -> None:
    """Reject typed sensor updates that cannot convert to the configured type.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
        config_entry_factory (ConfigEntryFactory): Factory for test configuration entries.
    """
    entity_id = "sensor.date_guard"
    entry = config_entry_factory(
        {
            CONF_ENTITY_PLATFORM: Platform.SENSOR,
            CONF_VARIABLE_ID: "date_guard",
            CONF_VALUE: "2026-08-10",
            CONF_VALUE_TYPE: "date",
            CONF_YAML_VARIABLE: False,
            CONF_RESTORE: False,
            CONF_FORCE_UPDATE: False,
        }
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    with pytest.raises(ValueError, match="not compatible with the selected device_class"):
        await hass.services.async_call(
            DOMAIN,
            SERVICE_UPDATE_SENSOR,
            {
                "entity_id": [entity_id],
                CONF_VALUE: "not-a-date",
            },
            blocking=True,
        )

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "2026-08-10"


@pytest.mark.parametrize(
    ("value_type", "entity_id", "variable_id", "quoted_value"),
    [
        pytest.param("string", "sensor.quoted_string", "quoted_string", "'87'", id="string"),
        pytest.param("number", "sensor.quoted_number", "quoted_number", "'87'", id="number"),
        pytest.param(
            "string", "sensor.quoted_double", "quoted_double", '"87.5"', id="double-quoted"
        ),
    ],
)
async def test_update_sensor_unwraps_quoted_numeric_value(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
    value_type: str,
    entity_id: str,
    variable_id: str,
    quoted_value: str,
) -> None:
    """Store quoted numeric service values as plain numbers for numeric_state.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
        config_entry_factory (ConfigEntryFactory): Factory for test configuration entries.
        value_type (str): Configured Variable value type.
        entity_id (str): Entity ID created from the variable id.
        variable_id (str): Variable ID used to create the config entry.
        quoted_value (str): Quoted numeric payload as supplied from the UI or YAML.
    """
    entry = config_entry_factory(
        {
            CONF_ENTITY_PLATFORM: Platform.SENSOR,
            CONF_VARIABLE_ID: variable_id,
            CONF_VALUE: None,
            CONF_VALUE_TYPE: value_type,
            CONF_YAML_VARIABLE: False,
            CONF_RESTORE: False,
            CONF_FORCE_UPDATE: False,
        }
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_UPDATE_SENSOR,
        {
            "entity_id": [entity_id],
            CONF_VALUE: quoted_value,
        },
        blocking=True,
    )

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == quoted_value.strip("\"'")
    assert "'" not in state.state
    assert '"' not in state.state


async def test_increment_from_none_uses_zero_baseline(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
) -> None:
    """Treat a missing native value as zero before incrementing.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
        config_entry_factory (ConfigEntryFactory): Factory for test configuration entries.
    """
    entry = config_entry_factory(
        {
            CONF_ENTITY_PLATFORM: Platform.SENSOR,
            CONF_VARIABLE_ID: "none_counter",
            CONF_VALUE: None,
            CONF_VALUE_TYPE: "number",
            CONF_YAML_VARIABLE: False,
            CONF_RESTORE: False,
            CONF_FORCE_UPDATE: False,
        }
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_INCREMENT_SENSOR,
        {"entity_id": ["sensor.none_counter"], ATTR_VALUE_DELTA: 2},
        blocking=True,
    )
    state = hass.states.get("sensor.none_counter")
    assert state is not None
    assert state.state == "2"


async def test_increment_converts_numeric_string_native_value(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Convert a numeric string native value before applying an increment.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
        config_entry_factory (ConfigEntryFactory): Factory for test configuration entries.
        monkeypatch (pytest.MonkeyPatch): Pytest fixture for replacing the state writer.
    """
    entry = config_entry_factory(
        {
            CONF_VARIABLE_ID: "string_counter",
            CONF_VALUE: 1,
            CONF_VALUE_TYPE: "number",
        }
    )
    sensor = Variable(hass, dict(entry.data), entry, entry.entry_id)
    sensor._attr_native_value = "3.5"
    monkeypatch.setattr(Variable, "async_write_ha_state", lambda self: None)

    await sensor.async_increment_variable(**{ATTR_VALUE_DELTA: 1.25})

    native_value = sensor._attr_native_value
    assert isinstance(native_value, float)
    assert native_value == 4.75


async def test_attribute_unit_of_measurement_is_native_unit(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Promote YAML-style unit_of_measurement attributes to the native unit.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
        config_entry_factory (ConfigEntryFactory): Factory for test configuration entries.
        caplog (pytest.LogCaptureFixture): Pytest fixture capturing log output.
    """
    entity_id = "sensor.variable_test_del_15m"
    entry = config_entry_factory(
        {
            CONF_ENTITY_PLATFORM: Platform.SENSOR,
            CONF_VARIABLE_ID: "variable_test_del_15m",
            CONF_VALUE: 1,
            CONF_VALUE_TYPE: "number",
            CONF_YAML_VARIABLE: False,
            CONF_RESTORE: False,
            CONF_FORCE_UPDATE: False,
            CONF_ATTRIBUTES: {
                "state_class": SensorStateClass.MEASUREMENT,
                CONF_DEVICE_CLASS: SensorDeviceClass.POWER,
                CONF_UNIT_OF_MEASUREMENT: UnitOfPower.KILO_WATT,
            },
        }
    )

    with caplog.at_level("WARNING"):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == "1"
    assert state.attributes[CONF_DEVICE_CLASS] == SensorDeviceClass.POWER
    assert state.attributes["state_class"] == SensorStateClass.MEASUREMENT
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == UnitOfPower.KILO_WATT

    sensor = _loaded_sensor(hass, entity_id)
    assert sensor.native_unit_of_measurement == UnitOfPower.KILO_WATT
    assert sensor.device_class == SensorDeviceClass.POWER
    assert sensor.state_class == SensorStateClass.MEASUREMENT
    extra_attributes = sensor._attr_extra_state_attributes
    assert extra_attributes is not None
    assert CONF_UNIT_OF_MEASUREMENT not in extra_attributes
    assert NATIVE_UNIT_NONE_WARNING not in caplog.text


async def test_restore_keeps_native_unit_when_display_unit_differs(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
) -> None:
    """Keep RestoreSensor native units when last state has a converted display unit.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
        config_entry_factory (ConfigEntryFactory): Factory for test configuration entries.
    """
    entity_id = "sensor.restored_power"
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State(
                    entity_id,
                    "1",
                    {
                        CONF_DEVICE_CLASS: SensorDeviceClass.POWER,
                        "state_class": SensorStateClass.MEASUREMENT,
                        ATTR_UNIT_OF_MEASUREMENT: UnitOfPower.WATT,
                    },
                ),
                {
                    "native_value": "1",
                    "native_unit_of_measurement": UnitOfPower.KILO_WATT,
                },
            )
        ],
    )
    entry = config_entry_factory(
        {
            CONF_ENTITY_PLATFORM: Platform.SENSOR,
            CONF_VARIABLE_ID: "restored_power",
            CONF_VALUE: 0,
            CONF_VALUE_TYPE: "number",
            CONF_YAML_VARIABLE: False,
            CONF_RESTORE: True,
            CONF_UPDATED: False,
            CONF_FORCE_UPDATE: False,
            CONF_ATTRIBUTES: {
                "state_class": SensorStateClass.MEASUREMENT,
                CONF_DEVICE_CLASS: SensorDeviceClass.POWER,
                CONF_UNIT_OF_MEASUREMENT: UnitOfPower.KILO_WATT,
            },
        }
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    sensor = _loaded_sensor(hass, entity_id)
    assert sensor.native_unit_of_measurement == UnitOfPower.KILO_WATT
    extra_attributes = sensor._attr_extra_state_attributes
    assert extra_attributes is not None
    assert CONF_UNIT_OF_MEASUREMENT not in extra_attributes
    assert ATTR_UNIT_OF_MEASUREMENT not in extra_attributes


async def test_restore_replaces_missing_native_unit_from_config_attributes(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Recover a YAML unit when RestoreSensor extra data stored native unit as None.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
        config_entry_factory (ConfigEntryFactory): Factory for test configuration entries.
        caplog (pytest.LogCaptureFixture): Pytest fixture capturing log output.
    """
    entity_id = "sensor.legacy_power"
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State(
                    entity_id,
                    "1",
                    {
                        CONF_DEVICE_CLASS: SensorDeviceClass.POWER,
                        "state_class": SensorStateClass.MEASUREMENT,
                        ATTR_UNIT_OF_MEASUREMENT: UnitOfPower.KILO_WATT,
                    },
                ),
                {
                    "native_value": "1",
                    "native_unit_of_measurement": None,
                },
            )
        ],
    )
    entry = config_entry_factory(
        {
            CONF_ENTITY_PLATFORM: Platform.SENSOR,
            CONF_VARIABLE_ID: "legacy_power",
            CONF_VALUE: 1,
            CONF_VALUE_TYPE: "number",
            CONF_YAML_VARIABLE: False,
            CONF_RESTORE: True,
            CONF_UPDATED: False,
            CONF_FORCE_UPDATE: False,
            CONF_ATTRIBUTES: {
                "state_class": SensorStateClass.MEASUREMENT,
                CONF_DEVICE_CLASS: SensorDeviceClass.POWER,
                CONF_UNIT_OF_MEASUREMENT: UnitOfPower.KILO_WATT,
            },
        }
    )

    with caplog.at_level("WARNING"):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    sensor = _loaded_sensor(hass, entity_id)
    assert sensor.native_unit_of_measurement == UnitOfPower.KILO_WATT
    extra_attributes = sensor._attr_extra_state_attributes
    assert extra_attributes is not None
    assert CONF_UNIT_OF_MEASUREMENT not in extra_attributes
    assert NATIVE_UNIT_NONE_WARNING not in caplog.text


async def test_restore_prefers_stored_native_unit_over_config(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
) -> None:
    """Keep a restored native unit when configuration specifies a different unit.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
        config_entry_factory (ConfigEntryFactory): Factory for test configuration entries.
    """
    entity_id = "sensor.restored_unit_precedence"
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State(
                    entity_id,
                    "1",
                    {
                        CONF_DEVICE_CLASS: SensorDeviceClass.POWER,
                        "state_class": SensorStateClass.MEASUREMENT,
                        ATTR_UNIT_OF_MEASUREMENT: UnitOfPower.WATT,
                    },
                ),
                {
                    "native_value": "1",
                    "native_unit_of_measurement": UnitOfPower.WATT,
                },
            )
        ],
    )
    entry = config_entry_factory(
        {
            CONF_ENTITY_PLATFORM: Platform.SENSOR,
            CONF_VARIABLE_ID: "restored_unit_precedence",
            CONF_VALUE: 0,
            CONF_VALUE_TYPE: "number",
            CONF_YAML_VARIABLE: False,
            CONF_RESTORE: True,
            CONF_UPDATED: False,
            CONF_FORCE_UPDATE: False,
            CONF_ATTRIBUTES: {
                "state_class": SensorStateClass.MEASUREMENT,
                CONF_DEVICE_CLASS: SensorDeviceClass.POWER,
                CONF_UNIT_OF_MEASUREMENT: UnitOfPower.KILO_WATT,
            },
        }
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    sensor = _loaded_sensor(hass, entity_id)
    assert sensor.native_unit_of_measurement == UnitOfPower.WATT
    extra_attributes = sensor._attr_extra_state_attributes
    assert extra_attributes is not None
    assert CONF_UNIT_OF_MEASUREMENT not in extra_attributes
    assert ATTR_UNIT_OF_MEASUREMENT not in extra_attributes


async def test_update_sensor_promotes_unit_of_measurement_attribute(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
) -> None:
    """Apply unit_of_measurement from an update-service attribute payload.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
        config_entry_factory (ConfigEntryFactory): Factory for test configuration entries.
    """
    entity_id = "sensor.service_power"
    entry = config_entry_factory(
        {
            CONF_ENTITY_PLATFORM: Platform.SENSOR,
            CONF_VARIABLE_ID: "service_power",
            CONF_VALUE: 2,
            CONF_VALUE_TYPE: "number",
            CONF_YAML_VARIABLE: False,
            CONF_RESTORE: False,
            CONF_FORCE_UPDATE: False,
        }
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_UPDATE_SENSOR,
        {
            "entity_id": [entity_id],
            ATTR_ATTRIBUTES: {
                CONF_DEVICE_CLASS: SensorDeviceClass.POWER,
                "state_class": SensorStateClass.MEASUREMENT,
                CONF_UNIT_OF_MEASUREMENT: UnitOfPower.KILO_WATT,
            },
        },
        blocking=True,
    )

    sensor = _loaded_sensor(hass, entity_id)
    assert sensor.native_unit_of_measurement == UnitOfPower.KILO_WATT
    assert sensor.device_class == SensorDeviceClass.POWER
    extra_attributes = sensor._attr_extra_state_attributes
    assert extra_attributes is not None
    assert CONF_UNIT_OF_MEASUREMENT not in extra_attributes
    state = hass.states.get(entity_id)
    assert state is not None
    assert state.attributes[ATTR_UNIT_OF_MEASUREMENT] == UnitOfPower.KILO_WATT


@pytest.mark.parametrize(
    ("config", "initial_native", "extra_attributes", "expected_native"),
    [
        pytest.param(
            {
                CONF_VARIABLE_ID: "unit_fill",
                CONF_VALUE: 1,
                CONF_DEVICE_CLASS: SensorDeviceClass.POWER,
                CONF_ATTRIBUTES: {CONF_UNIT_OF_MEASUREMENT: UnitOfPower.KILO_WATT},
            },
            None,
            {CONF_UNIT_OF_MEASUREMENT: UnitOfPower.KILO_WATT},
            UnitOfPower.KILO_WATT,
            id="attributes-unit",
        ),
        pytest.param(
            {
                CONF_VARIABLE_ID: "unit_fill",
                CONF_VALUE: 1,
                CONF_ATTRIBUTES: {ATTR_NATIVE_UNIT_OF_MEASUREMENT: UnitOfPower.WATT},
            },
            None,
            {},
            UnitOfPower.WATT,
            id="attributes-native-unit",
        ),
        pytest.param(
            {
                CONF_VARIABLE_ID: "unit_fill",
                CONF_VALUE: 1,
                CONF_UNIT_OF_MEASUREMENT: UnitOfPower.KILO_WATT,
            },
            None,
            {},
            UnitOfPower.KILO_WATT,
            id="config-unit",
        ),
        pytest.param(
            {
                CONF_VARIABLE_ID: "unit_fill",
                CONF_VALUE: 1,
                CONF_ATTRIBUTES: {CONF_UNIT_OF_MEASUREMENT: "none"},
            },
            None,
            {},
            None,
            id="none-string",
        ),
        pytest.param(
            {
                CONF_VARIABLE_ID: "unit_fill",
                CONF_VALUE: 1,
                CONF_ATTRIBUTES: {CONF_UNIT_OF_MEASUREMENT: "unknown"},
            },
            None,
            {},
            None,
            id="unknown-string",
        ),
        pytest.param(
            {
                CONF_VARIABLE_ID: "unit_fill",
                CONF_VALUE: 1,
                CONF_ATTRIBUTES: {CONF_UNIT_OF_MEASUREMENT: "unavailable"},
            },
            None,
            {},
            None,
            id="unavailable-string",
        ),
        pytest.param(
            {
                CONF_VARIABLE_ID: "unit_fill",
                CONF_VALUE: 1,
                CONF_ATTRIBUTES: {CONF_UNIT_OF_MEASUREMENT: UnitOfPower.WATT},
            },
            UnitOfPower.KILO_WATT,
            {CONF_UNIT_OF_MEASUREMENT: UnitOfPower.WATT},
            UnitOfPower.KILO_WATT,
            id="keep-existing-native",
        ),
    ],
)
def test_apply_missing_native_unit_from_config(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
    config: dict[str, object],
    initial_native: str | None,
    extra_attributes: dict[str, str],
    expected_native: str | None,
) -> None:
    """Fill or preserve native units from configured sensor unit attributes.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
        config_entry_factory (ConfigEntryFactory): Factory for test configuration entries.
        config (dict[str, object]): Variable configuration used to construct the entity.
        initial_native (str | None): Native unit present before the helper runs.
        extra_attributes (dict[str, str]): Extra state attributes present before the helper runs.
        expected_native (str | None): Native unit expected after the helper runs.
    """
    entry = config_entry_factory(config)
    sensor = Variable(hass, dict(entry.data), entry, entry.entry_id)
    sensor._attr_native_unit_of_measurement = initial_native
    sensor._attr_extra_state_attributes = dict(extra_attributes)

    sensor._apply_missing_native_unit_from_config()

    assert sensor._attr_native_unit_of_measurement == expected_native
    extra_state_attributes = sensor._attr_extra_state_attributes
    assert extra_state_attributes is not None
    assert CONF_UNIT_OF_MEASUREMENT not in extra_state_attributes
    if expected_native == UnitOfPower.KILO_WATT and config.get(CONF_DEVICE_CLASS):
        assert sensor._attr_suggested_unit_of_measurement == UnitOfPower.KILO_WATT


@pytest.mark.parametrize(
    ("unit_payload", "expected_native", "expected_suggested"),
    [
        pytest.param(
            {CONF_UNIT_OF_MEASUREMENT: "unknown"},
            None,
            None,
            id="unknown",
        ),
        pytest.param(
            {CONF_UNIT_OF_MEASUREMENT: "unavailable"},
            None,
            None,
            id="unavailable",
        ),
        pytest.param(
            {CONF_UNIT_OF_MEASUREMENT: "None"},
            None,
            None,
            id="none-selector",
        ),
        pytest.param(
            {ATTR_SUGGESTED_UNIT_OF_MEASUREMENT: "unknown"},
            None,
            None,
            id="suggested-unknown",
        ),
        pytest.param(
            {CONF_UNIT_OF_MEASUREMENT: UnitOfPower.KILO_WATT},
            UnitOfPower.KILO_WATT,
            None,
            id="valid-unit",
        ),
    ],
)
def test_update_attr_settings_normalizes_unit_sentinels(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
    unit_payload: dict[str, str],
    expected_native: str | None,
    expected_suggested: str | None,
) -> None:
    """Reject missing unit sentinels from attribute payloads.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
        config_entry_factory (ConfigEntryFactory): Factory for test configuration entries.
        unit_payload (dict[str, str]): Special unit attributes to apply.
        expected_native (str | None): Native unit expected after normalization.
        expected_suggested (str | None): Suggested unit expected after normalization.
    """
    entry = config_entry_factory({CONF_VARIABLE_ID: "unit_sentinels", CONF_VALUE: 1})
    sensor = Variable(hass, dict(entry.data), entry, entry.entry_id)

    remaining = sensor._update_attr_settings({**unit_payload, "source": "kept"})

    assert remaining is not None
    assert remaining["source"] == "kept"
    assert sensor._attr_native_unit_of_measurement == expected_native
    assert sensor._attr_suggested_unit_of_measurement == expected_suggested


def test_init_normalizes_configured_unit_sentinel(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
) -> None:
    """Treat the UI None unit selector as a missing native unit.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
        config_entry_factory (ConfigEntryFactory): Factory for test configuration entries.
    """
    entry = config_entry_factory(
        {
            CONF_VARIABLE_ID: "ui_none_unit",
            CONF_VALUE: 1,
            CONF_UNIT_OF_MEASUREMENT: "None",
        }
    )
    sensor = Variable(hass, dict(entry.data), entry, entry.entry_id)

    assert sensor._attr_native_unit_of_measurement is None
    assert sensor._attr_suggested_unit_of_measurement is None
