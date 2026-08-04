"""End-to-end setup orchestration tests for the Variable integration."""

import importlib
from typing import Any
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_BATTERY_LEVEL,
    ATTR_GPS_ACCURACY,
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
    SERVICE_RELOAD,
    STATE_ON,
    STATE_UNAVAILABLE,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
import pytest

from custom_components.variable.const import (
    CONF_ENTITY_PLATFORM,
    CONF_VALUE,
    CONF_VARIABLE_ID,
    CONF_YAML_PRESENT,
    CONF_YAML_VARIABLE,
    DOMAIN,
)
from tests.types import ConfigEntryFactory


async def test_yaml_setup_and_reload_manage_config_entries(
    hass: HomeAssistant,
) -> None:
    """Create, update, and remove YAML variables through Home Assistant APIs.

    Args:
        hass: Home Assistant instance that hosts the integration.
    """
    initial_config = {
        DOMAIN: {
            "yaml_temperature": {
                CONF_VALUE: 20,
                "attributes": {"source": "initial"},
            },
            "yaml_removed": {
                CONF_VALUE: "present",
            },
        }
    }

    assert await async_setup_component(hass, DOMAIN, initial_config)
    await hass.async_block_till_done()

    entries = {
        entry.data[CONF_VARIABLE_ID]: entry for entry in hass.config_entries.async_entries(DOMAIN)
    }
    temperature_entry = entries["yaml_temperature"]
    removed_entry = entries["yaml_removed"]
    assert temperature_entry.data[CONF_YAML_VARIABLE] is True
    assert temperature_entry.data[CONF_ENTITY_PLATFORM] == Platform.SENSOR
    initial_state = hass.states.get("sensor.yaml_temperature")
    assert initial_state is not None
    assert initial_state.state == "20"
    assert initial_state.attributes["source"] == "initial"
    removed_state = hass.states.get("sensor.yaml_removed")
    assert removed_state is not None
    removed_registry_entry = er.async_get(hass).async_get("sensor.yaml_removed")
    assert removed_registry_entry is not None
    assert removed_registry_entry.config_entry_id == removed_entry.entry_id

    reloaded_config = {
        DOMAIN: {
            "yaml_temperature": {
                CONF_VALUE: 24,
                "attributes": {"source": "reload"},
            }
        }
    }
    with patch(
        "custom_components.variable.async_integration_yaml_config",
        new=AsyncMock(return_value=reloaded_config),
    ):
        await hass.services.async_call(DOMAIN, SERVICE_RELOAD, blocking=True)
        await hass.async_block_till_done()

    current_entry = hass.config_entries.async_get_entry(temperature_entry.entry_id)
    assert current_entry is not None
    assert current_entry.data[CONF_VALUE] == 24
    assert current_entry.data[CONF_YAML_VARIABLE] is True
    assert CONF_YAML_PRESENT not in current_entry.data
    reloaded_state = hass.states.get("sensor.yaml_temperature")
    assert reloaded_state is not None
    assert reloaded_state.state == "24"
    assert reloaded_state.attributes["source"] == "reload"
    assert hass.config_entries.async_get_entry(removed_entry.entry_id) is None
    assert hass.states.get("sensor.yaml_removed") is None
    assert er.async_get(hass).async_get("sensor.yaml_removed") is None


@pytest.mark.parametrize(
    ("data", "entity_id", "expected_state", "expected_attributes"),
    [
        pytest.param(
            {
                CONF_ENTITY_PLATFORM: Platform.SENSOR,
                CONF_VARIABLE_ID: "workflow_sensor",
                CONF_VALUE: "ready",
                "value_type": "string",
            },
            "sensor.workflow_sensor",
            "ready",
            {"marker": "sensor"},
            id="sensor",
        ),
        pytest.param(
            {
                CONF_ENTITY_PLATFORM: Platform.BINARY_SENSOR,
                CONF_VARIABLE_ID: "workflow_switch",
                CONF_VALUE: "true",
            },
            "binary_sensor.workflow_switch",
            STATE_ON,
            {"marker": "binary"},
            id="binary-sensor",
        ),
        pytest.param(
            {
                CONF_ENTITY_PLATFORM: Platform.DEVICE_TRACKER,
                CONF_VARIABLE_ID: "workflow_tracker",
                ATTR_LATITUDE: 40.0,
                ATTR_LONGITUDE: -75.0,
                ATTR_GPS_ACCURACY: 15,
                ATTR_BATTERY_LEVEL: 90,
            },
            "device_tracker.workflow_tracker",
            "not_home",
            {"latitude": 40.0, "longitude": -75.0, "marker": "tracker"},
            id="device-tracker",
        ),
    ],
)
async def test_setup_entry_creates_platform_entity(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
    data: dict[str, Any],
    entity_id: str,
    expected_state: str,
    expected_attributes: dict[str, Any],
) -> None:
    """Load a config entry and expose its entity through Home Assistant state.

    Args:
        hass: Home Assistant instance that hosts the integration.
        config_entry_factory: Factory that creates the platform config entry.
        data: Platform-specific config-entry data to load.
        entity_id: Expected entity identifier after setup.
        expected_state: Expected state value for the created entity.
        expected_attributes: Expected attributes for the created entity.
    """
    marker = expected_attributes["marker"]
    entry_data = {
        **data,
        CONF_YAML_VARIABLE: False,
        "restore": False,
        "force_update": False,
        "attributes": {"marker": marker},
    }
    entry = config_entry_factory(entry_data)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.state == expected_state
    for attribute, value in expected_attributes.items():
        assert state.attributes[attribute] == value

    registry_entry = er.async_get(hass).async_get(entity_id)
    assert registry_entry is not None
    assert registry_entry.config_entry_id == entry.entry_id


async def test_unload_entry_removes_active_entity(
    hass: HomeAssistant,
    sensor_entry: ConfigEntry,
) -> None:
    """Unload a platform entry and remove its active entity state.

    Args:
        hass: Home Assistant instance that hosts the integration.
        sensor_entry: Sensor config entry to set up and unload.
    """
    assert await hass.config_entries.async_setup(sensor_entry.entry_id)
    await hass.async_block_till_done()
    assert hass.states.get("sensor.office_temperature") is not None

    assert await hass.config_entries.async_unload(sensor_entry.entry_id)
    await hass.async_block_till_done()

    unloaded_state = hass.states.get("sensor.office_temperature")
    assert unloaded_state is not None
    assert unloaded_state.state == STATE_UNAVAILABLE


async def test_setup_entry_calls_helper_device_cleanup(
    hass: HomeAssistant,
    sensor_entry: ConfigEntry,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Call helper device cleanup before forwarding platform setup.

    Args:
        hass: Home Assistant instance that hosts the integration.
        sensor_entry: Sensor config entry to set up.
        monkeypatch: Pytest fixture used to stub helper cleanup.
    """
    cleanup = AsyncMock()
    monkeypatch.setattr(
        "custom_components.variable.async_remove_helper_devices",
        cleanup,
    )

    assert await hass.config_entries.async_setup(sensor_entry.entry_id)
    await hass.async_block_till_done()

    cleanup.assert_called_once_with(
        hass,
        helper_config_entry_id=sensor_entry.entry_id,
        source_device_id=sensor_entry.data.get("device_id"),
        remove_all_devices=True,
    )


def test_async_remove_helper_devices_fallback_maps_keyword_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Map the 2026.8 helper cleanup API onto the legacy device helper.

    Args:
        monkeypatch: Pytest fixture used to simulate missing helper APIs.
    """
    stale_calls: list[tuple[str, str | None]] = []

    def fake_stale(
        _hass: HomeAssistant,
        helper_config_entry_id: str,
        source_device_id: str | None,
    ) -> None:
        stale_calls.append((helper_config_entry_id, source_device_id))

    import homeassistant.helpers.helper_integration as helper_integration
    from custom_components.variable import __init__ as variable_init

    monkeypatch.setattr(
        "homeassistant.helpers.device.async_remove_stale_devices_links_keep_current_device",
        fake_stale,
    )
    monkeypatch.delattr(helper_integration, "async_remove_helper_devices", raising=False)

    importlib.reload(variable_init)
    try:
        variable_init.async_remove_helper_devices(
            None,
            helper_config_entry_id="entry-1",
            source_device_id="device-1",
            remove_all_devices=True,
        )
        assert stale_calls == [("entry-1", "device-1")]
    finally:
        importlib.reload(variable_init)


async def test_remove_entry_cleans_up_entity_registry(
    hass: HomeAssistant,
    sensor_entry: ConfigEntry,
) -> None:
    """Remove a config entry and clean up its entity registry record.

    Args:
        hass: Home Assistant instance that hosts the integration.
        sensor_entry: Sensor config entry to set up and remove.
    """
    assert await hass.config_entries.async_setup(sensor_entry.entry_id)
    await hass.async_block_till_done()
    assert er.async_get(hass).async_get("sensor.office_temperature") is not None

    await hass.config_entries.async_remove(sensor_entry.entry_id)
    await hass.async_block_till_done()

    assert er.async_get(hass).async_get("sensor.office_temperature") is None
