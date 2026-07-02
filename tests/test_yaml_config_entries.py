import asyncio
from dataclasses import dataclass, field
import importlib
import sys
from types import ModuleType, SimpleNamespace
from typing import Any


class Platform(str):
    SENSOR = "sensor"
    BINARY_SENSOR = "binary_sensor"
    DEVICE_TRACKER = "device_tracker"


def _install_homeassistant_stubs() -> None:
    def schema(value):
        return value

    def marker(key, *args, **kwargs):
        return key

    def noop(*args, **kwargs):
        return None

    homeassistant = ModuleType("homeassistant")
    config_entries = ModuleType("homeassistant.config_entries")
    config_entries.SOURCE_IMPORT = "import"
    config_entries.ConfigEntry = object

    const = ModuleType("homeassistant.const")
    const.CONF_DEVICE = "device"
    const.CONF_DEVICE_ID = "device_id"
    const.CONF_ENTITY_ID = "entity_id"
    const.CONF_FRIENDLY_NAME = "friendly_name"
    const.CONF_ICON = "icon"
    const.CONF_NAME = "name"
    const.SERVICE_RELOAD = "reload"
    const.Platform = Platform

    core = ModuleType("homeassistant.core")
    core.HomeAssistant = object
    core.ServiceCall = object

    exceptions = ModuleType("homeassistant.exceptions")
    exceptions.HomeAssistantError = Exception

    helpers = ModuleType("homeassistant.helpers")
    helpers.config_validation = SimpleNamespace(
        boolean=bool,
        match_all=lambda value: value,
        string=str,
    )

    device = ModuleType("homeassistant.helpers.device")
    device.async_remove_stale_devices_links_keep_current_device = noop

    entity_registry = ModuleType("homeassistant.helpers.entity_registry")
    entity_registry.async_get = noop

    reload_module = ModuleType("homeassistant.helpers.reload")

    async def async_integration_yaml_config(*args, **kwargs):
        return None

    reload_module.async_integration_yaml_config = async_integration_yaml_config

    typing_module = ModuleType("homeassistant.helpers.typing")
    typing_module.ConfigType = dict

    voluptuous = ModuleType("voluptuous")
    voluptuous.Schema = schema
    voluptuous.Required = marker
    voluptuous.Optional = marker

    variable_device = ModuleType("custom_components.variable.device")

    async def create_device(*args, **kwargs):
        return True

    async def remove_device(*args, **kwargs):
        return True

    variable_device.create_device = create_device
    variable_device.remove_device = remove_device

    sys.modules.update(
        {
            "homeassistant": homeassistant,
            "homeassistant.config_entries": config_entries,
            "homeassistant.const": const,
            "homeassistant.core": core,
            "homeassistant.exceptions": exceptions,
            "homeassistant.helpers": helpers,
            "homeassistant.helpers.device": device,
            "homeassistant.helpers.entity_registry": entity_registry,
            "homeassistant.helpers.reload": reload_module,
            "homeassistant.helpers.typing": typing_module,
            "voluptuous": voluptuous,
            "custom_components.variable.device": variable_device,
        }
    )


_install_homeassistant_stubs()

variable = importlib.import_module("custom_components.variable")
const = importlib.import_module("custom_components.variable.const")


@dataclass
class FakeEntry:
    entry_id: str
    data: dict[str, Any]
    update_listeners: list[Any] = field(default_factory=list)
    unload_callbacks: list[Any] = field(default_factory=list)

    def add_update_listener(self, listener):
        self.update_listeners.append(listener)
        return listener

    def async_on_unload(self, callback):
        self.unload_callbacks.append(callback)


class FakeConfigEntries:
    def __init__(self, entries):
        self._entries = entries
        self.forwarded = []
        self.reloaded = []
        self.removed = []
        self.updated = []

    def async_entries(self, domain):
        assert domain == const.DOMAIN
        return list(self._entries)

    def async_update_entry(self, entry, data, options):
        entry.data = data
        self.updated.append((entry.entry_id, data, options))

    async def async_forward_entry_setups(self, entry, platforms):
        self.forwarded.append((entry.entry_id, platforms))

    async def async_reload(self, entry_id):
        self.reloaded.append(entry_id)

    async def async_remove(self, entry_id):
        self.removed.append(entry_id)


class FakeHass:
    def __init__(self, entries):
        self.config_entries = FakeConfigEntries(entries)
        self.data = {}
        self.tasks = []

    def async_create_task(self, coroutine):
        task = asyncio.create_task(coroutine)
        self.tasks.append(task)
        return task


def test_yaml_entry_setup_without_yaml_present_does_not_delete_or_listen():
    entry = FakeEntry(
        "yaml-entry",
        {
            const.CONF_ENTITY_PLATFORM: Platform.SENSOR,
            const.CONF_VARIABLE_ID: "kitchen_light",
            const.CONF_YAML_VARIABLE: True,
        },
    )
    hass = FakeHass([entry])

    result = asyncio.run(variable.async_setup_entry(hass, entry))

    assert result is True
    assert hass.config_entries.removed == []
    assert entry.update_listeners == []
    assert hass.config_entries.forwarded == [("yaml-entry", [Platform.SENSOR])]


def test_yaml_entry_setup_strips_yaml_present_without_registering_listener():
    entry = FakeEntry(
        "yaml-entry",
        {
            const.CONF_ENTITY_PLATFORM: Platform.SENSOR,
            const.CONF_VARIABLE_ID: "kitchen_light",
            const.CONF_YAML_VARIABLE: True,
            const.CONF_YAML_PRESENT: True,
        },
    )
    hass = FakeHass([entry])

    result = asyncio.run(variable.async_setup_entry(hass, entry))

    assert result is True
    assert const.CONF_YAML_PRESENT not in entry.data
    assert hass.config_entries.removed == []
    assert entry.update_listeners == []
    assert hass.config_entries.updated == [
        (
            "yaml-entry",
            {
                const.CONF_ENTITY_PLATFORM: Platform.SENSOR,
                const.CONF_VARIABLE_ID: "kitchen_light",
                const.CONF_YAML_VARIABLE: True,
            },
            {},
        )
    ]


def test_ui_entry_setup_registers_update_listener_that_reloads_entry():
    entry = FakeEntry(
        "ui-entry",
        {
            const.CONF_ENTITY_PLATFORM: Platform.SENSOR,
            const.CONF_VARIABLE_ID: "kitchen_light",
            const.CONF_YAML_VARIABLE: False,
        },
    )
    hass = FakeHass([entry])

    asyncio.run(variable.async_setup_entry(hass, entry))
    asyncio.run(entry.update_listeners[0](hass, entry))

    assert hass.config_entries.removed == []
    assert hass.config_entries.reloaded == ["ui-entry"]


def test_yaml_processing_removes_only_yaml_entries_missing_from_config():
    yaml_entry = FakeEntry(
        "yaml-entry",
        {
            const.CONF_VARIABLE_ID: "removed_from_yaml",
            const.CONF_YAML_VARIABLE: True,
        },
    )
    ui_entry = FakeEntry(
        "ui-entry",
        {
            const.CONF_VARIABLE_ID: "created_in_ui",
            const.CONF_YAML_VARIABLE: False,
        },
    )
    hass = FakeHass([yaml_entry, ui_entry])

    async def process_yaml():
        await variable._async_process_yaml(hass, {const.DOMAIN: {}})
        await asyncio.gather(*hass.tasks)

    asyncio.run(process_yaml())

    assert hass.config_entries.removed == ["yaml-entry"]
