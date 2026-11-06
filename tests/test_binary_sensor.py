"""Integration tests for Variable binary-sensor restore and services."""

from homeassistant.const import (
    ATTR_FRIENDLY_NAME,
    CONF_DEVICE,
    CONF_DEVICE_ID,
    CONF_NAME,
    STATE_OFF,
    STATE_ON,
    STATE_UNKNOWN,
    Platform,
)
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import device_registry as dr
import pytest
from pytest_homeassistant.common import mock_restore_cache

from custom_components.variable.binary_sensor import Variable
from custom_components.variable.const import (
    ATTR_ATTRIBUTES,
    ATTR_REPLACE_ATTRIBUTES,
    CONF_ATTRIBUTES,
    CONF_ENTITY_PLATFORM,
    CONF_FORCE_UPDATE,
    CONF_RESTORE,
    CONF_VALUE,
    CONF_VARIABLE_ID,
    CONF_YAML_VARIABLE,
    DOMAIN,
    SERVICE_UPDATE_BINARY_SENSOR,
)
from custom_components.variable.device import _get_device_for_entry
from tests.types import ConfigEntryFactory


async def test_binary_sensor_restore_cache_is_applied_during_config_entry_setup(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
) -> None:
    """Restore a binary sensor's public state and custom attributes on startup.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
        config_entry_factory (ConfigEntryFactory): Factory for test configuration entries.
    """
    entity_id = "binary_sensor.restored_binary"
    restored_state = STATE_ON
    restored_attributes = {"source": "binary-cache"}
    cached_state = State(entity_id, restored_state, restored_attributes)
    mock_restore_cache(hass, [cached_state])
    entry = config_entry_factory(
        {
            CONF_ENTITY_PLATFORM: Platform.BINARY_SENSOR,
            CONF_VARIABLE_ID: "restored_binary",
            CONF_VALUE: "false",
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


async def test_binary_sensor_empty_restore_uses_config_attributes(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
) -> None:
    """Apply configured attributes when the restore cache has none.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
        config_entry_factory (ConfigEntryFactory): Factory for test configuration entries.
    """
    entity_id = "binary_sensor.empty_restored_binary"
    mock_restore_cache(hass, [State(entity_id, STATE_UNKNOWN, {})])
    configured_attributes = {"source": "config-fallback"}
    entry = config_entry_factory(
        {
            CONF_ENTITY_PLATFORM: Platform.BINARY_SENSOR,
            CONF_VARIABLE_ID: "empty_restored_binary",
            CONF_VALUE: "false",
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
    assert state.state == STATE_UNKNOWN
    assert state.attributes["source"] == "config-fallback"


async def test_device_linked_binary_sensor_name_is_not_prefixed_again_after_reload(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
) -> None:
    """Keep a device-linked binary sensor's friendly name stable across reload.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
        config_entry_factory (ConfigEntryFactory): Factory for test configuration entries.
    """
    entity_id = "binary_sensor.linked_contact"
    restored_state = STATE_ON
    entity_name = "Linked Contact"
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
    mock_restore_cache(hass, [cached_state])
    entity_entry = config_entry_factory(
        {
            CONF_ENTITY_PLATFORM: Platform.BINARY_SENSOR,
            CONF_VARIABLE_ID: "linked_contact",
            CONF_NAME: entity_name,
            CONF_DEVICE_ID: device.id,
            CONF_VALUE: "false",
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


@pytest.mark.parametrize(
    ("initial_value", "expected_state", "variable_suffix"),
    [
        pytest.param("true", STATE_OFF, "on_to_off", id="on-to-off"),
        pytest.param("false", STATE_ON, "off_to_on", id="off-to-on"),
        pytest.param(None, STATE_UNKNOWN, "unknown", id="unknown-remains-unknown"),
    ],
)
async def test_binary_sensor_toggle_service(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
    initial_value: str | None,
    expected_state: str,
    variable_suffix: str,
) -> None:
    """Toggle known binary states while preserving the public unknown state.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
        config_entry_factory (ConfigEntryFactory): Factory for test configuration entries.
        initial_value (str | None): Initial variable value provided to the binary sensor.
        expected_state (str): Expected public state after toggling.
        variable_suffix (str): Stable suffix for the test variable and entity IDs.
    """
    entry = config_entry_factory(
        {
            CONF_ENTITY_PLATFORM: Platform.BINARY_SENSOR,
            CONF_VARIABLE_ID: f"toggle_{variable_suffix}",
            CONF_VALUE: initial_value,
            CONF_YAML_VARIABLE: False,
            CONF_RESTORE: False,
            CONF_FORCE_UPDATE: False,
        }
    )
    entity_id = f"binary_sensor.toggle_{variable_suffix}"
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    await hass.services.async_call(
        DOMAIN,
        "toggle_binary_sensor",
        {"entity_id": [entity_id]},
        blocking=True,
    )

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == expected_state


@pytest.mark.parametrize(
    ("value", "expected_state"),
    [
        pytest.param("true", STATE_ON, id="true"),
        pytest.param("false", STATE_OFF, id="false"),
        pytest.param("None", STATE_UNKNOWN, id="none"),
    ],
)
async def test_update_binary_sensor_service_value_and_attribute_merge(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
    value: str,
    expected_state: str,
) -> None:
    """Apply allowed update_binary_sensor values while merging attributes.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
        config_entry_factory (ConfigEntryFactory): Factory for test configuration entries.
        value (str): Service payload value allowed by the entity-service schema.
        expected_state (str): Expected public binary state after the update.
    """
    entry = config_entry_factory(
        {
            CONF_ENTITY_PLATFORM: Platform.BINARY_SENSOR,
            CONF_VARIABLE_ID: "coercion_binary",
            CONF_VALUE: "false",
            CONF_YAML_VARIABLE: False,
            CONF_RESTORE: False,
            CONF_FORCE_UPDATE: False,
            CONF_ATTRIBUTES: {"source": "initial"},
        }
    )
    entity_id = "binary_sensor.coercion_binary"
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_UPDATE_BINARY_SENSOR,
        {
            "entity_id": [entity_id],
            CONF_VALUE: value,
            ATTR_ATTRIBUTES: {"merged": True},
            ATTR_REPLACE_ATTRIBUTES: False,
        },
        blocking=True,
    )

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == expected_state
    assert state.attributes["source"] == "initial"
    assert state.attributes["merged"] is True


@pytest.mark.parametrize(
    ("value", "expected_is_on"),
    [
        pytest.param("1", True, id="one"),
        pytest.param("yes", True, id="yes"),
        pytest.param("on", True, id="on"),
        pytest.param("0", False, id="zero"),
        pytest.param("unavailable", None, id="unavailable"),
        pytest.param(True, True, id="bool-true"),
        pytest.param(False, False, id="bool-false"),
        pytest.param(None, None, id="null"),
    ],
)
async def test_update_binary_sensor_value_coercion_aliases(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
    monkeypatch: pytest.MonkeyPatch,
    value: str | bool | None,
    expected_is_on: bool | None,
) -> None:
    """Coerce direct update payloads across aliases outside the service schema.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
        config_entry_factory (ConfigEntryFactory): Factory for test configuration entries.
        monkeypatch (pytest.MonkeyPatch): Pytest fixture for replacing the state writer.
        value (str | bool | None): Update payload value to coerce.
        expected_is_on (bool | None): Expected internal binary state after the update.
    """
    entry = config_entry_factory(
        {
            CONF_VARIABLE_ID: "alias_binary",
            CONF_VALUE: "false",
        }
    )
    binary_sensor = Variable(hass, dict(entry.data), entry, entry.entry_id)
    monkeypatch.setattr(Variable, "async_write_ha_state", lambda self: None)

    await binary_sensor.async_update_variable(**{CONF_VALUE: value})

    assert binary_sensor.is_on is expected_is_on
