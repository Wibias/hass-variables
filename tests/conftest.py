"""Shared pytest fixtures for the Variable integration."""

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, Platform
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant.common import MockConfigEntry

import custom_components
from custom_components.variable.const import (
    CONF_ATTRIBUTES,
    CONF_ENTITY_PLATFORM,
    CONF_FORCE_UPDATE,
    CONF_RESTORE,
    CONF_VALUE,
    CONF_VALUE_TYPE,
    CONF_VARIABLE_ID,
    CONF_YAML_VARIABLE,
    DOMAIN,
)
from tests.types import ConfigEntryFactory


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Enable loading custom integrations in every test.

    Args:
        enable_custom_integrations (None): Home Assistant fixture that enables custom
            integration loading.
        monkeypatch (pytest.MonkeyPatch): Pytest fixture used to expose the repository integration
            package.
    """
    monkeypatch.setattr(
        custom_components,
        "__path__",
        [str(Path(__file__).parents[1] / "custom_components")],
    )


@pytest.fixture
def config_entry_factory(hass: HomeAssistant) -> ConfigEntryFactory:
    """Return a factory that adds Variable config entries to Home Assistant.

    Args:
        hass (HomeAssistant): Home Assistant test instance that receives each config entry.

    Returns:
        ConfigEntryFactory: A factory that creates and registers a Variable config entry.
    """

    def _create(data: Mapping[str, Any]) -> ConfigEntry:
        """Create and register a Variable config entry from supplied data.

        Args:
            data (Mapping[str, Any]): Config-entry data to copy into the mock entry.

        Returns:
            ConfigEntry: The registered Variable config entry.
        """
        entry = MockConfigEntry(
            domain=DOMAIN,
            title=str(data.get(CONF_VARIABLE_ID, data.get(CONF_NAME, "Variable"))),
            data=dict(data),
        )
        entry.add_to_hass(hass)
        return entry

    return _create


@pytest.fixture
def sensor_entry(config_entry_factory: ConfigEntryFactory) -> ConfigEntry:
    """Create a representative sensor config entry.

    Args:
        config_entry_factory (ConfigEntryFactory): Factory that creates registered Variable entries.

    Returns:
        ConfigEntry: A registered numeric sensor config entry.
    """
    return config_entry_factory(
        {
            CONF_ENTITY_PLATFORM: Platform.SENSOR,
            CONF_VARIABLE_ID: "office_temperature",
            CONF_YAML_VARIABLE: False,
            CONF_NAME: "Office Temperature",
            CONF_RESTORE: False,
            CONF_FORCE_UPDATE: False,
            CONF_VALUE: 21.5,
            CONF_VALUE_TYPE: "number",
            CONF_ATTRIBUTES: {"source": "test"},
        }
    )
