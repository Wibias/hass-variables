"""Home Assistant test plugin helpers shared across the test suite.

``pytest-homeassistant`` covers Home Assistant 2026.11 and later. Older supported
versions are only covered by its predecessor,
``pytest-homeassistant-custom-component``. Import plugin helpers from here so the
same tests run against either package.
"""

try:
    from pytest_homeassistant.common import (
        MockConfigEntry,
        mock_restore_cache,
        mock_restore_cache_with_extra_data,
    )
except ModuleNotFoundError:
    from pytest_homeassistant_custom_component.common import (
        MockConfigEntry,
        mock_restore_cache,
        mock_restore_cache_with_extra_data,
    )

__all__ = ["MockConfigEntry", "mock_restore_cache", "mock_restore_cache_with_extra_data"]
