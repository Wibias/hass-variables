"""Integration and regression tests for Variable device trackers."""

import ast
from pathlib import Path

from homeassistant.components.device_tracker.const import ATTR_LOCATION_NAME
from homeassistant.const import (
    ATTR_BATTERY_LEVEL,
    ATTR_FRIENDLY_NAME,
    ATTR_GPS_ACCURACY,
    ATTR_LATITUDE,
    ATTR_LONGITUDE,
    CONF_DEVICE,
    CONF_DEVICE_ID,
    CONF_NAME,
    STATE_NOT_HOME,
    STATE_UNKNOWN,
    Platform,
)
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import device_registry as dr
import pytest
from pytest_homeassistant.common import mock_restore_cache

from custom_components.variable.const import (
    ATTR_ATTRIBUTES,
    ATTR_DELETE_IN_ZONES,
    ATTR_DELETE_LOCATION_NAME,
    ATTR_IN_ZONES,
    ATTR_REPLACE_ATTRIBUTES,
    CONF_ATTRIBUTES,
    CONF_ENTITY_PLATFORM,
    CONF_FORCE_UPDATE,
    CONF_RESTORE,
    CONF_UPDATED,
    CONF_VARIABLE_ID,
    CONF_YAML_VARIABLE,
    DOMAIN,
    SERVICE_UPDATE_DEVICE_TRACKER,
)
from custom_components.variable.device import _get_device_for_entry
from custom_components.variable.device_tracker import Variable
from tests.types import ConfigEntryFactory


async def test_device_tracker_restore_cache_is_applied_during_config_entry_setup(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
) -> None:
    """Restore a tracker's public state and custom attributes on startup.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
        config_entry_factory (ConfigEntryFactory): Factory for test configuration entries.
    """
    entity_id = "device_tracker.restored_tracker"
    restored_location_name = "Studio"
    restored_attributes = {
        ATTR_LATITUDE: 41.25,
        ATTR_LONGITUDE: -74.75,
        ATTR_LOCATION_NAME: restored_location_name,
        "source": "tracker-cache",
    }
    cached_state = State(entity_id, restored_location_name, restored_attributes)
    mock_restore_cache(hass, [cached_state])
    entry = config_entry_factory(
        {
            CONF_ENTITY_PLATFORM: Platform.DEVICE_TRACKER,
            CONF_VARIABLE_ID: "restored_tracker",
            ATTR_LATITUDE: 40.0,
            ATTR_LONGITUDE: -75.0,
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
    assert state.state == STATE_NOT_HOME
    assert state.attributes["source"] == restored_attributes["source"]
    for attribute in (ATTR_LATITUDE, ATTR_LONGITUDE, ATTR_LOCATION_NAME):
        assert state.attributes[attribute] == restored_attributes[attribute]


async def test_device_tracker_empty_restore_uses_config_attributes(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
) -> None:
    """Apply configured custom and special attributes when the restore cache is empty.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
        config_entry_factory (ConfigEntryFactory): Factory for test configuration entries.
    """
    entity_id = "device_tracker.empty_restored_tracker"
    mock_restore_cache(hass, [State(entity_id, STATE_UNKNOWN, {})])
    configured_location_name = "Config Location"
    configured_battery_level = 80
    configured_attributes = {
        ATTR_BATTERY_LEVEL: configured_battery_level,
        ATTR_LOCATION_NAME: configured_location_name,
    }
    entry = config_entry_factory(
        {
            CONF_ENTITY_PLATFORM: Platform.DEVICE_TRACKER,
            CONF_VARIABLE_ID: "empty_restored_tracker",
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
    assert state.attributes[ATTR_LOCATION_NAME] == configured_location_name
    assert state.attributes[ATTR_BATTERY_LEVEL] == configured_battery_level


async def test_updated_device_tracker_discards_reserved_restored_attributes(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
) -> None:
    """Keep updated tracker settings while restoring only custom attributes.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
        config_entry_factory (ConfigEntryFactory): Factory for test configuration entries.
    """
    entity_id = "device_tracker.updated_tracker"
    mock_restore_cache(
        hass,
        [
            State(
                entity_id,
                "Cached Location",
                {
                    ATTR_LATITUDE: 1.0,
                    ATTR_LONGITUDE: 2.0,
                    ATTR_LOCATION_NAME: "Cached Location",
                    "source": "restore-cache",
                },
            )
        ],
    )
    entry = config_entry_factory(
        {
            CONF_ENTITY_PLATFORM: Platform.DEVICE_TRACKER,
            CONF_VARIABLE_ID: "updated_tracker",
            ATTR_LATITUDE: 41.0,
            ATTR_LONGITUDE: -75.0,
            ATTR_LOCATION_NAME: "Config Location",
            CONF_YAML_VARIABLE: False,
            CONF_RESTORE: True,
            CONF_UPDATED: True,
            CONF_FORCE_UPDATE: False,
        }
    )

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(entity_id)
    assert state is not None
    assert state.attributes[ATTR_LATITUDE] == 41.0
    assert state.attributes[ATTR_LONGITUDE] == -75.0
    assert state.attributes[ATTR_LOCATION_NAME] == "Config Location"
    assert state.attributes["source"] == "restore-cache"


def test_update_attr_settings_rejects_non_mapping_and_handles_none(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Return unsupported helper inputs unchanged and report invalid data.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
        config_entry_factory (ConfigEntryFactory): Factory for test configuration entries.
        caplog (pytest.LogCaptureFixture): Pytest log capture fixture.
    """
    entry = config_entry_factory({CONF_VARIABLE_ID: "helper_tracker"})
    tracker = Variable(hass, entry.data, entry, entry.entry_id)
    invalid_attributes = ["not", "a", "mapping"]

    assert tracker._update_attr_settings(invalid_attributes) is invalid_attributes
    assert "Attributes must be a dictionary" in caplog.text
    assert tracker._update_attr_settings(None) is None


async def test_device_linked_tracker_name_is_not_prefixed_again_after_reload(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
) -> None:
    """Keep a device-linked tracker's friendly name stable across reload.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
        config_entry_factory (ConfigEntryFactory): Factory for test configuration entries.
    """
    entity_id = "device_tracker.linked_tracker"
    restored_state = "Workshop"
    entity_name = "Linked Tracker"
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
            CONF_ENTITY_PLATFORM: Platform.DEVICE_TRACKER,
            CONF_VARIABLE_ID: "linked_tracker",
            CONF_NAME: entity_name,
            CONF_DEVICE_ID: device.id,
            ATTR_LOCATION_NAME: "Config Location",
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


async def test_device_tracker_update_and_delete_services(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
) -> None:
    """Update tracker location data, then delete its optional location fields.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
        config_entry_factory (ConfigEntryFactory): Factory for test configuration entries.
    """
    entity_id = "device_tracker.service_tracker"
    entry = config_entry_factory(
        {
            CONF_ENTITY_PLATFORM: Platform.DEVICE_TRACKER,
            CONF_VARIABLE_ID: "service_tracker",
            ATTR_BATTERY_LEVEL: 80,
            CONF_ATTRIBUTES: {"retained": True},
            CONF_YAML_VARIABLE: False,
            CONF_RESTORE: False,
            CONF_FORCE_UPDATE: False,
        }
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_UPDATE_DEVICE_TRACKER,
        {
            "entity_id": [entity_id],
            ATTR_LOCATION_NAME: "Workshop",
            ATTR_BATTERY_LEVEL: 64,
            ATTR_LATITUDE: 41.5,
            ATTR_LONGITUDE: -74.5,
            ATTR_GPS_ACCURACY: 4,
            ATTR_ATTRIBUTES: {"updated": True},
            ATTR_REPLACE_ATTRIBUTES: False,
        },
        blocking=True,
    )
    updated = hass.states.get(entity_id)
    assert updated is not None
    assert updated.state == STATE_NOT_HOME
    assert updated.attributes[ATTR_LOCATION_NAME] == "Workshop"
    assert updated.attributes[ATTR_BATTERY_LEVEL] == 64
    assert updated.attributes[ATTR_LATITUDE] == 41.5
    assert updated.attributes[ATTR_LONGITUDE] == -74.5
    assert updated.attributes[ATTR_GPS_ACCURACY] == 4
    assert updated.attributes["retained"] is True
    assert updated.attributes["updated"] is True

    await hass.services.async_call(
        DOMAIN,
        SERVICE_UPDATE_DEVICE_TRACKER,
        {
            "entity_id": [entity_id],
            ATTR_DELETE_LOCATION_NAME: True,
        },
        blocking=True,
    )
    deleted = hass.states.get(entity_id)
    assert deleted is not None
    assert ATTR_LOCATION_NAME not in deleted.attributes
    assert deleted.state == STATE_NOT_HOME


async def test_device_tracker_update_contains_state_write_failure(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Contain a state-write failure from the public tracker update service.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
        config_entry_factory (ConfigEntryFactory): Factory for test configuration entries.
        monkeypatch (pytest.MonkeyPatch): Pytest fixture for replacing the state writer.
        caplog (pytest.LogCaptureFixture): Pytest log capture fixture.
    """
    entity_id = "device_tracker.failing_write_tracker"
    entry = config_entry_factory(
        {
            CONF_ENTITY_PLATFORM: Platform.DEVICE_TRACKER,
            CONF_VARIABLE_ID: "failing_write_tracker",
            CONF_YAML_VARIABLE: False,
            CONF_RESTORE: False,
            CONF_FORCE_UPDATE: False,
        }
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    def raise_write_failure(self: Variable) -> None:
        """Raise a representative Home Assistant state-write failure.

        Args:
            self (Variable): Device tracker entity whose state write is being replaced.

        Raises:
            RuntimeError: Always, to emulate a failed state write.
        """
        raise RuntimeError("state write failed")

    monkeypatch.setattr(Variable, "async_write_ha_state", raise_write_failure)

    await hass.services.async_call(
        DOMAIN,
        SERVICE_UPDATE_DEVICE_TRACKER,
        {"entity_id": [entity_id], ATTR_BATTERY_LEVEL: 50},
        blocking=True,
    )

    assert "async_write_ha_state failed during update: state write failed" in caplog.text


async def test_device_tracker_in_zones_service_and_delete(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
) -> None:
    """Set and delete a coordinate-free tracker's explicit zone membership.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
        config_entry_factory (ConfigEntryFactory): Factory for test configuration entries.
    """
    entity_id = "device_tracker.zone_tracker"
    zone_id = "zone.workshop"
    hass.states.async_set(
        zone_id,
        "zoning",
        {
            ATTR_FRIENDLY_NAME: "Workshop Zone",
            "latitude": 41.5,
            "longitude": -74.5,
            "radius": 100,
            "passive": False,
        },
    )
    entry = config_entry_factory(
        {
            CONF_ENTITY_PLATFORM: Platform.DEVICE_TRACKER,
            CONF_VARIABLE_ID: "zone_tracker",
            CONF_YAML_VARIABLE: False,
            CONF_RESTORE: False,
            CONF_FORCE_UPDATE: False,
        }
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_UPDATE_DEVICE_TRACKER,
        {"entity_id": [entity_id], "in_zones": [zone_id]},
        blocking=True,
    )
    zoned = hass.states.get(entity_id)
    assert zoned is not None
    assert zoned.state == "Workshop Zone"
    assert zoned.attributes["in_zones"] == [zone_id]

    await hass.services.async_call(
        DOMAIN,
        SERVICE_UPDATE_DEVICE_TRACKER,
        {"entity_id": [entity_id], ATTR_DELETE_IN_ZONES: True},
        blocking=True,
    )
    unzoned = hass.states.get(entity_id)
    assert unzoned is not None
    assert unzoned.state == STATE_UNKNOWN
    assert unzoned.attributes["in_zones"] == []


async def test_location_name_does_not_set_state_and_logs_warning(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Keep location_name as an attribute without changing tracker state.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
        config_entry_factory (ConfigEntryFactory): Factory for test configuration entries.
        caplog (pytest.LogCaptureFixture): Pytest log capture fixture.
    """
    entity_id = "device_tracker.named_tracker"
    entry = config_entry_factory(
        {
            CONF_ENTITY_PLATFORM: Platform.DEVICE_TRACKER,
            CONF_VARIABLE_ID: "named_tracker",
            CONF_YAML_VARIABLE: False,
            CONF_RESTORE: False,
            CONF_FORCE_UPDATE: False,
        }
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    await hass.services.async_call(
        DOMAIN,
        SERVICE_UPDATE_DEVICE_TRACKER,
        {
            "entity_id": [entity_id],
            ATTR_ATTRIBUTES: {ATTR_LOCATION_NAME: "Studio"},
        },
        blocking=True,
    )
    named = hass.states.get(entity_id)
    assert named is not None
    assert named.state != "Studio"
    assert named.attributes[ATTR_LOCATION_NAME] == "Studio"
    assert "location_name does not set device_tracker state" in caplog.text

    await hass.services.async_call(
        DOMAIN,
        SERVICE_UPDATE_DEVICE_TRACKER,
        {"entity_id": [entity_id], ATTR_LOCATION_NAME: "Workshop"},
        blocking=True,
    )
    assert caplog.text.count("location_name does not set device_tracker state") == 1


async def test_in_zones_takes_priority_over_coordinates(
    hass: HomeAssistant,
    config_entry_factory: ConfigEntryFactory,
) -> None:
    """Prefer explicit zone membership over coordinate matching for tracker state.

    Args:
        hass (HomeAssistant): Home Assistant test instance.
        config_entry_factory (ConfigEntryFactory): Factory for test configuration entries.
    """
    entity_id = "device_tracker.priority_tracker"
    zone_id = "zone.workshop"
    hass.states.async_set(
        zone_id,
        "zoning",
        {
            ATTR_FRIENDLY_NAME: "Workshop Zone",
            "latitude": 41.5,
            "longitude": -74.5,
            "radius": 100,
            "passive": False,
        },
    )
    entry = config_entry_factory(
        {
            CONF_ENTITY_PLATFORM: Platform.DEVICE_TRACKER,
            CONF_VARIABLE_ID: "priority_tracker",
            ATTR_LATITUDE: 40.0,
            ATTR_LONGITUDE: -75.0,
            CONF_YAML_VARIABLE: False,
            CONF_RESTORE: False,
            CONF_FORCE_UPDATE: False,
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
    assert zoned.attributes[ATTR_LATITUDE] == 40.0
    assert zoned.attributes[ATTR_LONGITUDE] == -75.0
    assert zoned.attributes[ATTR_IN_ZONES] == [zone_id]


DEVICE_TRACKER_PATH = (
    Path(__file__).parents[1] / "custom_components" / "variable" / "device_tracker.py"
)


@pytest.fixture(scope="module")
def device_tracker_ast() -> tuple[ast.Module, ast.ClassDef]:
    """Parse the device tracker platform once for all tests.

    Returns:
        tuple[ast.Module, ast.ClassDef]: Parsed module and its ``Variable`` entity class.
    """
    module = ast.parse(DEVICE_TRACKER_PATH.read_text(encoding="utf-8"))
    variable_class = next(
        node for node in module.body if isinstance(node, ast.ClassDef) and node.name == "Variable"
    )
    return module, variable_class


def test_tracker_entity_is_imported_from_public_module(
    device_tracker_ast: tuple[ast.Module, ast.ClassDef],
) -> None:
    """TrackerEntity should use Home Assistant's public import path.

    Args:
        device_tracker_ast (tuple[ast.Module, ast.ClassDef]): Parsed device tracker module and entity class.
    """
    module, _ = device_tracker_ast
    tracker_imports = [
        node.module
        for node in module.body
        if isinstance(node, ast.ImportFrom)
        and any(alias.name == "TrackerEntity" for alias in node.names)
    ]

    assert tracker_imports == ["homeassistant.components.device_tracker"]


def test_variable_does_not_override_final_tracker_properties(
    device_tracker_ast: tuple[ast.Module, ast.ClassDef],
) -> None:
    """Variable should not override deprecated or final tracker properties.

    Args:
        device_tracker_ast (tuple[ast.Module, ast.ClassDef]): Parsed device tracker module and entity class.
    """
    _, variable_class = device_tracker_ast
    method_names = {
        node.name
        for node in variable_class.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    assert {"location_name", "state_attributes", "_set_location_name"}.isdisjoint(method_names)


def test_deprecated_location_name_shorthand_is_not_used(
    device_tracker_ast: tuple[ast.Module, ast.ClassDef],
) -> None:
    """Do not assign the deprecated TrackerEntity location-name shorthand.

    Args:
        device_tracker_ast (tuple[ast.Module, ast.ClassDef]): Parsed device tracker module and entity class.
    """
    module, _ = device_tracker_ast
    forbidden_names = {
        node.id
        for node in ast.walk(module)
        if isinstance(node, ast.Name) and node.id == "SUPPORTS_TRACKER_IN_ZONES"
    }
    forbidden_attrs = {
        node.attr
        for node in ast.walk(module)
        if isinstance(node, ast.Attribute) and node.attr == "_attr_location_name"
    }

    assert not forbidden_names
    assert not forbidden_attrs
