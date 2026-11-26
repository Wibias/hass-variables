"""Tests for Variable device orchestration and lifecycle behavior."""

from unittest.mock import Mock

from homeassistant.components.device_tracker.const import ATTR_LOCATION_NAME
from homeassistant.const import (
    ATTR_BATTERY_LEVEL,
    ATTR_GPS_ACCURACY,
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
    CONF_DEVICE,
    CONF_DEVICE_CLASS,
    CONF_DEVICE_ID,
    CONF_NAME,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import device_registry as dr, entity_registry as er
import pytest

from custom_components.variable.const import (
    CONF_ATTRIBUTES,
    CONF_CLEAR_DEVICE_ID,
    CONF_ENTITY_PLATFORM,
    CONF_EXCLUDE_FROM_RECORDER,
    CONF_FORCE_UPDATE,
    CONF_RESTORE,
    CONF_VALUE,
    CONF_VALUE_TYPE,
    CONF_VARIABLE_ID,
    CONF_YAML_VARIABLE,
    DOMAIN,
)
from custom_components.variable.device import (
    _get_device_for_entry,
    create_device,
    remove_device,
    update_device,
)
from tests.types import ConfigEntryFactory


async def test_create_device_reloads_only_linked_variable_entities(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Reload linked Variable entities while ignoring YAML and other platforms.

    Args:
        hass (HomeAssistant): Home Assistant instance that hosts the integration.
        config_entry_factory (ConfigEntryFactory): Factory that creates registered Variable entries.
        monkeypatch (pytest.MonkeyPatch): Pytest fixture used to observe scheduled entry reloads.
    """
    device_entry = config_entry_factory(
        {
            CONF_ENTITY_PLATFORM: CONF_DEVICE,
            CONF_NAME: "Reload Hub",
            CONF_YAML_VARIABLE: False,
        }
    )
    assert await hass.config_entries.async_setup(device_entry.entry_id)
    await hass.async_block_till_done()
    device = _get_device_for_entry(dr.async_get(hass), device_entry)
    assert device is not None

    linked_entry = config_entry_factory(
        {
            CONF_ENTITY_PLATFORM: Platform.SENSOR,
            CONF_VARIABLE_ID: "linked_reload_sensor",
            CONF_NAME: "Linked Reload Sensor",
            CONF_VALUE: 1,
            CONF_VALUE_TYPE: "number",
            CONF_DEVICE_ID: device.id,
            CONF_YAML_VARIABLE: False,
            CONF_RESTORE: False,
            CONF_FORCE_UPDATE: False,
        }
    )
    yaml_entry = config_entry_factory(
        {
            CONF_ENTITY_PLATFORM: Platform.SENSOR,
            CONF_VARIABLE_ID: "yaml_reload_sensor",
            CONF_NAME: "YAML Reload Sensor",
            CONF_VALUE: 2,
            CONF_VALUE_TYPE: "number",
            CONF_YAML_VARIABLE: True,
            CONF_RESTORE: False,
            CONF_FORCE_UPDATE: False,
        }
    )
    for entry in (linked_entry, yaml_entry):
        assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    er.async_get(hass).async_get_or_create(
        "sensor",
        "other_platform",
        "other-platform-linked-device",
        config_entry=linked_entry,
        device_id=device.id,
        suggested_object_id="other_platform_linked_device",
    )
    schedule_reload = Mock()
    monkeypatch.setattr(hass.config_entries, "async_schedule_reload", schedule_reload)

    await create_device(hass, device_entry)

    schedule_reload.assert_called_once_with(linked_entry.entry_id)


async def test_update_device_changes_all_registry_metadata(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
) -> None:
    """Update every supported device metadata field in the registry.

    Args:
        hass (HomeAssistant): Home Assistant instance that hosts the integration.
        config_entry_factory (ConfigEntryFactory): Factory that creates the device config entry.
    """
    entry = config_entry_factory(
        {
            CONF_ENTITY_PLATFORM: CONF_DEVICE,
            CONF_NAME: "Metadata Hub",
            CONF_YAML_VARIABLE: False,
        }
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    metadata = {
        "manufacturer": "Variables Inc.",
        "model": "Virtual Hub",
        "model_id": "VH-2",
        "sw_version": "2.0",
        "hw_version": "B",
        "serial_number": "SERIAL-2",
        "configuration_url": "https://example.com/metadata",
    }

    assert await update_device(hass, entry, metadata)

    device = _get_device_for_entry(dr.async_get(hass), entry)
    assert device is not None
    assert device.manufacturer == metadata["manufacturer"]
    assert device.model == metadata["model"]
    assert device.model_id == metadata["model_id"]
    assert device.sw_version == metadata["sw_version"]
    assert device.hw_version == metadata["hw_version"]
    assert device.serial_number == metadata["serial_number"]
    assert str(device.configuration_url) == metadata["configuration_url"]


async def test_update_device_returns_false_when_registry_device_is_missing(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
) -> None:
    """Report that metadata cannot be updated without a registry device.

    Args:
        hass (HomeAssistant): Home Assistant instance that hosts the integration.
        config_entry_factory (ConfigEntryFactory): Factory that creates the unconfigured entry.
    """
    entry = config_entry_factory(
        {
            CONF_ENTITY_PLATFORM: CONF_DEVICE,
            CONF_NAME: "Missing Hub",
            CONF_YAML_VARIABLE: False,
        }
    )

    assert not await update_device(hass, entry, {"model": "Unapplied"})


def test_get_device_for_entry_uses_legacy_lookup_before_home_assistant_2026_8(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Use the unscoped lookup only when the scoped API is unavailable.

    Args:
        hass (HomeAssistant): Home Assistant instance that hosts the registry.
        config_entry_factory (ConfigEntryFactory): Factory that creates the device config entry.
        monkeypatch (pytest.MonkeyPatch): Pytest fixture used to simulate Home Assistant 2026.6.
    """
    entry = config_entry_factory(
        {
            CONF_ENTITY_PLATFORM: CONF_DEVICE,
            CONF_NAME: "Legacy Lookup Hub",
            CONF_YAML_VARIABLE: False,
        }
    )
    device_registry = dr.async_get(hass)
    expected_device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        name="Legacy Lookup Hub",
    )
    legacy_lookup = Mock(wraps=device_registry.async_get_device)
    monkeypatch.delattr(dr.DeviceRegistry, "async_get_device_by_identifier", raising=False)
    monkeypatch.setattr(dr.DeviceRegistry, "async_get_device", legacy_lookup)

    assert _get_device_for_entry(device_registry, entry) is expected_device
    legacy_lookup.assert_called_once_with(identifiers={(DOMAIN, entry.entry_id)})


async def test_remove_device_reloads_only_attached_variable_entities(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Remove a registry device and reload only attached Variable entities.

    Args:
        hass (HomeAssistant): Home Assistant instance that hosts the integration.
        config_entry_factory (ConfigEntryFactory): Factory that creates registered Variable entries.
        monkeypatch (pytest.MonkeyPatch): Pytest fixture used to observe scheduled entry reloads.
    """
    device_entry = config_entry_factory(
        {
            CONF_ENTITY_PLATFORM: CONF_DEVICE,
            CONF_NAME: "Removal Hub",
            CONF_YAML_VARIABLE: False,
        }
    )
    assert await hass.config_entries.async_setup(device_entry.entry_id)
    await hass.async_block_till_done()
    device_registry = dr.async_get(hass)
    device = _get_device_for_entry(device_registry, device_entry)
    assert device is not None

    linked_entry = config_entry_factory(
        {
            CONF_ENTITY_PLATFORM: Platform.SENSOR,
            CONF_VARIABLE_ID: "removal_sensor",
            CONF_NAME: "Removal Sensor",
            CONF_VALUE: 1,
            CONF_VALUE_TYPE: "number",
            CONF_DEVICE_ID: device.id,
            CONF_YAML_VARIABLE: False,
            CONF_RESTORE: False,
            CONF_FORCE_UPDATE: False,
        }
    )
    assert await hass.config_entries.async_setup(linked_entry.entry_id)
    await hass.async_block_till_done()
    er.async_get(hass).async_get_or_create(
        "sensor",
        "other_platform",
        "other-platform-removal-device",
        config_entry=linked_entry,
        device_id=device.id,
        suggested_object_id="other_platform_removal_device",
    )
    schedule_reload = Mock()
    monkeypatch.setattr(hass.config_entries, "async_schedule_reload", schedule_reload)

    assert await remove_device(hass, device_entry)

    assert _get_device_for_entry(device_registry, device_entry) is None
    schedule_reload.assert_called_once_with(linked_entry.entry_id)


async def test_remove_device_succeeds_when_registry_device_is_missing(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
) -> None:
    """Treat removal of an already absent registry device as successful.

    Args:
        hass (HomeAssistant): Home Assistant instance that hosts the integration.
        config_entry_factory (ConfigEntryFactory): Factory that creates the unconfigured entry.
    """
    entry = config_entry_factory(
        {
            CONF_ENTITY_PLATFORM: CONF_DEVICE,
            CONF_NAME: "Already Removed Hub",
            CONF_YAML_VARIABLE: False,
        }
    )

    assert await remove_device(hass, entry)


async def test_setup_device_entry_creates_registry_device(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
) -> None:
    """Load a device config entry and register its metadata.

    Args:
        hass (HomeAssistant): Home Assistant instance that hosts the integration.
        config_entry_factory (ConfigEntryFactory): Factory that creates the device config entry.
    """
    entry = config_entry_factory(
        {
            CONF_ENTITY_PLATFORM: CONF_DEVICE,
            CONF_NAME: "Virtual Hub",
            CONF_YAML_VARIABLE: False,
            "manufacturer": "Variables",
            "configuration_url": "https://example.com/device",
        }
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    device = _get_device_for_entry(dr.async_get(hass), entry)
    assert device is not None
    assert device.name == "Virtual Hub"
    assert device.manufacturer == "Variables"
    assert str(device.configuration_url) == "https://example.com/device"


async def test_clearing_variable_device_links_preserves_entities_when_device_removed(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
) -> None:
    """Unlink every variable platform before removing its virtual device.

    Args:
        hass (HomeAssistant): Home Assistant test instance used for the lifecycle workflow.
        config_entry_factory (ConfigEntryFactory): Factory that creates registered Variable entries.
    """
    flow_result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
    )
    flow_result = await hass.config_entries.flow.async_configure(
        flow_result["flow_id"],
        user_input={"next_step_id": "add_device"},
    )
    flow_result = await hass.config_entries.flow.async_configure(
        flow_result["flow_id"],
        user_input={
            CONF_NAME: "Lifecycle Device",
            "manufacturer": "Variables",
        },
    )

    assert flow_result["type"] is FlowResultType.CREATE_ENTRY
    device_entry = flow_result["result"]
    await hass.async_block_till_done()

    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)
    device = _get_device_for_entry(device_registry, device_entry)
    assert device is not None

    entries = [
        config_entry_factory(
            {
                CONF_ENTITY_PLATFORM: Platform.SENSOR,
                CONF_VARIABLE_ID: "linked_sensor",
                CONF_NAME: "Linked Sensor",
                CONF_VALUE: "21.5",
                CONF_VALUE_TYPE: "string",
                CONF_DEVICE_ID: device.id,
                CONF_YAML_VARIABLE: False,
                CONF_RESTORE: False,
                CONF_FORCE_UPDATE: False,
            }
        ),
        config_entry_factory(
            {
                CONF_ENTITY_PLATFORM: Platform.BINARY_SENSOR,
                CONF_VARIABLE_ID: "linked_binary",
                CONF_NAME: "Linked Binary",
                CONF_VALUE: "true",
                CONF_DEVICE_ID: device.id,
                CONF_YAML_VARIABLE: False,
                CONF_RESTORE: False,
                CONF_FORCE_UPDATE: False,
            }
        ),
        config_entry_factory(
            {
                CONF_ENTITY_PLATFORM: Platform.DEVICE_TRACKER,
                CONF_VARIABLE_ID: "linked_tracker",
                CONF_NAME: "Linked Tracker",
                ATTR_LATITUDE: 40.0,
                ATTR_LONGITUDE: -75.0,
                ATTR_GPS_ACCURACY: 10,
                ATTR_BATTERY_LEVEL: 80,
                CONF_DEVICE_ID: device.id,
                CONF_YAML_VARIABLE: False,
                CONF_RESTORE: False,
                CONF_FORCE_UPDATE: False,
            }
        ),
    ]
    entity_ids = (
        "sensor.linked_sensor",
        "binary_sensor.linked_binary",
        "device_tracker.linked_tracker",
    )

    for entry in entries:
        assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    for entity_id, entry in zip(entity_ids, entries, strict=True):
        assert hass.states.get(entity_id) is not None
        registry_entry = entity_registry.async_get(entity_id)
        assert registry_entry is not None
        assert registry_entry.config_entry_id == entry.entry_id
        assert registry_entry.device_id == device.id

    sensor_flow = await hass.config_entries.options.async_init(entries[0].entry_id)
    sensor_flow = await hass.config_entries.options.async_configure(
        sensor_flow["flow_id"],
        user_input={"next_step_id": "sensor_options"},
    )
    assert sensor_flow["step_id"] == "sensor_options"
    sensor_flow = await hass.config_entries.options.async_configure(
        sensor_flow["flow_id"],
        user_input={
            CONF_DEVICE_CLASS: "None",
            CONF_CLEAR_DEVICE_ID: True,
            CONF_RESTORE: False,
            CONF_FORCE_UPDATE: False,
            CONF_EXCLUDE_FROM_RECORDER: False,
        },
    )
    assert sensor_flow["step_id"] == "sensor_options_page_2"
    sensor_flow = await hass.config_entries.options.async_configure(
        sensor_flow["flow_id"],
        user_input={
            CONF_VALUE: "21.5",
            CONF_ATTRIBUTES: {"source": "sensor-options"},
        },
    )
    assert sensor_flow["type"] is FlowResultType.CREATE_ENTRY

    binary_flow = await hass.config_entries.options.async_init(entries[1].entry_id)
    binary_flow = await hass.config_entries.options.async_configure(
        binary_flow["flow_id"],
        user_input={"next_step_id": "binary_sensor_options"},
    )
    binary_flow = await hass.config_entries.options.async_configure(
        binary_flow["flow_id"],
        user_input={
            CONF_VALUE: "true",
            CONF_ATTRIBUTES: {"source": "binary-options"},
            CONF_DEVICE_CLASS: "None",
            CONF_CLEAR_DEVICE_ID: True,
            CONF_RESTORE: False,
            CONF_FORCE_UPDATE: False,
            CONF_EXCLUDE_FROM_RECORDER: False,
        },
    )
    assert binary_flow["type"] is FlowResultType.CREATE_ENTRY

    tracker_flow = await hass.config_entries.options.async_init(entries[2].entry_id)
    tracker_flow = await hass.config_entries.options.async_configure(
        tracker_flow["flow_id"],
        user_input={"next_step_id": "device_tracker_options"},
    )
    tracker_flow = await hass.config_entries.options.async_configure(
        tracker_flow["flow_id"],
        user_input={
            ATTR_LATITUDE: 40.0,
            ATTR_LONGITUDE: -75.0,
            ATTR_LOCATION_NAME: "Test Location",
            ATTR_GPS_ACCURACY: 10,
            ATTR_BATTERY_LEVEL: 80,
            CONF_ATTRIBUTES: {"source": "tracker-options"},
            CONF_CLEAR_DEVICE_ID: True,
            CONF_RESTORE: False,
            CONF_FORCE_UPDATE: False,
            CONF_EXCLUDE_FROM_RECORDER: False,
        },
    )
    assert tracker_flow["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    for entity_id, entry in zip(entity_ids, entries, strict=True):
        assert CONF_DEVICE_ID not in entry.data
        assert hass.states.get(entity_id) is not None
        registry_entry = entity_registry.async_get(entity_id)
        assert registry_entry is not None
        assert registry_entry.config_entry_id == entry.entry_id
        assert registry_entry.device_id is None

    assert await hass.config_entries.async_remove(device_entry.entry_id)
    await hass.async_block_till_done()

    assert _get_device_for_entry(device_registry, device_entry) is None
    for entity_id, entry in zip(entity_ids, entries, strict=True):
        assert hass.states.get(entity_id) is not None
        registry_entry = entity_registry.async_get(entity_id)
        assert registry_entry is not None
        assert registry_entry.config_entry_id == entry.entry_id
        assert registry_entry.device_id is None
