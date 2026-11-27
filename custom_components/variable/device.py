"""Device registry helpers for the Variable integration."""

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import (
    CONF_CONFIGURATION_URL,
    CONF_HW_VERSION,
    CONF_MANUFACTURER,
    CONF_MODEL,
    CONF_MODEL_ID,
    CONF_SERIAL_NUMBER,
    CONF_SW_VERSION,
    CONF_YAML_VARIABLE,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


def _get_device_for_entry(
    device_registry: dr.DeviceRegistry, entry: ConfigEntry
) -> dr.DeviceEntry | None:
    """Return the registry device owned by a Variable config entry.

    Home Assistant 2026.8 added the config-entry-scoped lookup. Retain the
    legacy lookup only for the integration's supported 2026.6 and 2026.7
    releases, where identifiers were still globally unique.

    Args:
        device_registry (dr.DeviceRegistry): Registry containing Variable devices.
        entry (ConfigEntry): Config entry that owns the requested device.

    Returns:
        dr.DeviceEntry | None: Matching device, if one exists.
    """
    identifier = (DOMAIN, entry.entry_id)
    if scoped_lookup := getattr(device_registry, "async_get_device_by_identifier", None):
        return scoped_lookup(identifier, entry.entry_id)
    return device_registry.async_get_device(identifiers={identifier})


async def create_device(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Create or update a registry device and reload affected Variable entities.

    Args:
        hass (HomeAssistant): Home Assistant instance hosting the integration.
        entry (ConfigEntry): Variable config entry that defines the helper device.
    """
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)

    device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.entry_id)},
        manufacturer=entry.data.get(CONF_MANUFACTURER),
        name=entry.data.get(CONF_NAME),
        model=entry.data.get(CONF_MODEL),
        model_id=entry.data.get(CONF_MODEL_ID),
        sw_version=entry.data.get(CONF_SW_VERSION),
        hw_version=entry.data.get(CONF_HW_VERSION),
        serial_number=entry.data.get(CONF_SERIAL_NUMBER),
        configuration_url=entry.data.get(CONF_CONFIGURATION_URL),
    )
    _LOGGER.debug("(%s) [create_device] device id: %s", device.name, device.id)
    device_entities = er.async_entries_for_device(
        registry=entity_registry, device_id=device.id, include_disabled_entities=True
    )
    domain_entries = hass.config_entries.async_loaded_entries(DOMAIN)
    domain_entities: list = []
    for domain_entry in domain_entries:
        if not domain_entry.data.get(CONF_YAML_VARIABLE, False):
            domain_entities.extend(
                er.async_entries_for_config_entry(
                    registry=entity_registry, config_entry_id=domain_entry.entry_id
                )
            )
    domain_reload_entities = [entity for entity in domain_entities if entity.device_id == device.id]
    reload_entities = device_entities + domain_reload_entities
    if len(reload_entities) > 0:
        _LOGGER.debug(
            "(%s) [create_device] Reloading %s entities", device.name, len(reload_entities)
        )
    else:
        _LOGGER.debug("(%s) [create_device] Reloading all Variable entities", device.name)
        reload_entities = domain_entities

    scheduled_entry_ids: set[str] = set()
    for entity in reload_entities:
        if entity.platform != DOMAIN:
            continue
        _LOGGER.debug("(%s) [create_device] Reloading entity_id: %s", device.name, entity.entity_id)
        if entity.config_entry_id and entity.config_entry_id not in scheduled_entry_ids:
            scheduled_entry_ids.add(entity.config_entry_id)
            hass.config_entries.async_schedule_reload(entity.config_entry_id)


async def update_device(
    hass: HomeAssistant, entry: ConfigEntry, user_input: dict[str, Any]
) -> bool:
    """Update the config entry's registry device metadata.

    Args:
        hass (HomeAssistant): Home Assistant instance hosting the integration.
        entry (ConfigEntry): Variable config entry associated with the helper device.
        user_input (dict[str, Any]): Device registry fields to update.

    Returns:
        bool: True when the device was updated; False when no matching device exists.
    """
    device_registry = dr.async_get(hass)
    device = _get_device_for_entry(device_registry, entry)
    if device is None:
        _LOGGER.debug("No device found to update")
        return False

    device_registry.async_update_device(
        device_id=device.id,
        manufacturer=user_input.get(CONF_MANUFACTURER),
        model=user_input.get(CONF_MODEL),
        model_id=user_input.get(CONF_MODEL_ID),
        sw_version=user_input.get(CONF_SW_VERSION),
        hw_version=user_input.get(CONF_HW_VERSION),
        serial_number=user_input.get(CONF_SERIAL_NUMBER),
        configuration_url=user_input.get(CONF_CONFIGURATION_URL),
    )
    _LOGGER.debug("(%s) [update_device] updated device id: %s", device.name or "", device.id)
    return True


async def remove_device(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Remove the config entry's registry device and reload linked entities.

    Args:
        hass (HomeAssistant): Home Assistant instance hosting the integration.
        entry (ConfigEntry): Variable config entry associated with the helper device.

    Returns:
        bool: True after the matching device is removed or when none exists.
    """
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)

    device = _get_device_for_entry(device_registry, entry)
    _LOGGER.debug(
        "(%s) [remove_device] device id: %s",
        getattr(device, "name", ""),
        getattr(device, "id", ""),
    )
    if device is None:
        return True
    entities = er.async_entries_for_device(
        registry=entity_registry, device_id=device.id, include_disabled_entities=True
    )
    _LOGGER.debug("(%s) [remove_device] Reloading %s entities", device.name, len(entities))
    device_registry.async_remove_device(device.id)

    for entity in entities:
        if entity.platform != DOMAIN:
            continue
        _LOGGER.debug("(%s) [remove_device] Reloading entity_id: %s", device.name, entity.entity_id)
        if entity.config_entry_id:
            hass.config_entries.async_schedule_reload(entity.config_entry_id)

    return True
