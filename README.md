# Variables+History
### aka. `variable`

  <img alt="Variable Logo" src="https://github.com/wibias/hass-variables/raw/master/custom_components/variable/brand/icon@2x.png">

[![Integration Usage][integration-usage-shield]][releases]

[![GitHub Downloads][downloads-shield]][releases]
[![GitHub Latest Downloads][downloads-latest-shield]][releases]
[![GitHub Release][releases-shield]][releases]
[![GitHub Release Date][release-date-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![Coverage][coverage-shield]][coverage]
[![License][license-shield]](LICENSE)
[![hacs][hacsbadge]][hacs]

A Home Assistant Integration to declare and set/update variables.

Requires Home Assistant 2026.6 or later.

## Installation

1. Ensure that [HACS](https://hacs.xyz/) is installed
2. [Click Here](https://my.home-assistant.io/redirect/hacs_repository/?owner=wibias&repository=hass-variables) to directly open `Variables+History` in HACS **or**<br/>
  a. Navigate to HACS<br/>
  b. Click `+ Explore & Download Repositories`<br/>
  c. Find the `Variables+History` integration <br/>
3. Click `Download`
4. Restart Home Assistant
5. See [Configuration](#configuration) below

## <a name="configuration"></a>Preferred Configuration
1. [Click Here](https://my.home-assistant.io/redirect/config_flow_start/?domain=variable) to directly add a `Variables+History` sensor **or**<br/>
  a. In Home Assistant, go to Settings -> [Integrations](https://my.home-assistant.io/redirect/integrations/)<br/>
  b. Click `+ Add Integrations` and select `Variables+History`<br/>
2. Add your configuration ([see Configuration Options below](#configuration-options))
3. Click `Submit`
* Repeat as needed to create additional `Variables+History` sensors
* Options can be changed for existing `Variables+History` sensors in Home Assistant Integrations by selecting `Configure` under the desired `Variables+History` sensor.

## Configuration Options

### First choose the `variable` type.

<details>
<summary><h3>Sensor</h3></summary>

| Name                    | Required | Default        | Description                                                                                                                     |
|-------------------------|----------|----------------|---------------------------------------------------------------------------------------------------------------------------------|
| `Variable ID`           | `Yes`    |                | The desired id of the new sensor (ex. `test_variable` would create an entity_id of `sensor.test_variable`)                      |
| `Name`                  | `No`     |                | Friendly name of the variable sensor                                                                                            |
| `Icon`                  | `No`     | `mdi:variable` | Icon of the Variable                                                                                                            |
| `Initial Value`         | `No`     |                | Initial value/state of the variable. If `Restore on Restart` is `False`, the variable will reset to this value on every restart |
| `Initial Attributes`    | `No`     |                | Initial attributes of the variable. If `Restore on Restart` is `False`, the variable will reset to this value on every restart  |
| `Restore on Restart`    | `No`     | `True`         | If `True` will restore previous value on restart. If `False`, will reset to `Initial Value` and `Initial Attributes` on restart |
| `Force Update`          | `No`     | `False`        | Variable's `last_updated` time will change with any service calls to update the variable even if the value does not change      |
| `Exclude from Recorder` | `No`     | `False`        | Excludes attributes from Recorder while preserving state history. Enable for Variables with large attributes to prevent Recorder Errors. |

</details>

<details>
<summary><h3>Binary Sensor</h3></summary>

| Name                    | Required | Default        | Description                                                                                                                                    |
|-------------------------|----------|----------------|------------------------------------------------------------------------------------------------------------------------------------------------|
| `Variable ID`           | `Yes`    |                | The desired id of the new binary sensor (ex. `test_variable` would create an entity_id of `binary_sensor.test_variable`)                       |
| `Name`                  | `No`     |                | Friendly name of the variable binary sensor                                                                                                    |
| `Icon`                  | `No`     | `mdi:variable` | Icon of the Variable                                                                                                                           |
| `Initial Value`         | `No`     | `False`        | Initial `True`/`False` value/state of the variable. If `Restore on Restart` is `False`, the variable will reset to this value on every restart |
| `Initial Attributes`    | `No`     |                | Initial attributes of the variable. If `Restore on Restart` is `False`, the variable will reset to this value on every restart                 |
| `Restore on Restart`    | `No`     | `True`         | If `True` will restore previous value on restart. If `False`, will reset to `Initial Value` and `Initial Attributes` on restart                |
| `Force Update`          | `No`     | `False`        | Variable's `last_updated` time will change with any service calls to update the variable even if the value does not change                     |
| `Exclude from Recorder` | `No`     | `False`        | Excludes attributes from Recorder while preserving state history. Enable for Variables with large attributes to prevent Recorder Errors. |

</details>

<details>
<summary><h3>Device Tracker</h3></summary>

| Name                    | Required | Default        | Description                                                                                                                                                                                                                        |
|-------------------------|----------|----------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `Variable ID`           | `Yes`    |                | The desired id of the new device tracker (ex. `test_variable` would create an entity_id of `device_tracker.test_variable`)                                                                                                         |
| `Name`                  | `No`     |                | Friendly name of the variable device tracker                                                                                                                                                                                       |
| `Icon`                  | `No`     | `mdi:variable` | Icon of the Variable                                                                                                                                                                                                               |
| `Initial Latitude`      | `Yes`    |                | Latitude. Home Assistant matches these coordinates against your zones to set state unless `in_zones` is set.                                                    |
| `Initial Longitude`     | `Yes`    |                | Longitude. Used with latitude for zone matching.                                                                                                                |
| `Initial Location Name` | `No`     |                | Extra attribute only; does **not** set entity state.                                                                                                            |
| `Initial GPS Accuracy`  | `No`     |                | Accuracy in meters                                                                                                                                                                                                                 |
| `Initial Battery Level` | `No`     |                | Battery level from 0-100%                                                                                                                                                                                                          |
| `Initial Attributes`    | `No`     |                | Initial attributes of the variable                                                                                                                                                                                                 |
| `Restore on Restart`    | `No`     | `True`         | If `True` will restore previous value on restart. If `False`, will reset to `Initial Latitude`, `Initial Longitude`, `Initial Location Name`, `Initial GPS Accuracy`, `Initial Battery Level`, and `Initial Attributes` on restart |
| `Force Update`          | `No`     | `False`        | Variable's `last_updated` time will change with any service calls to update the variable even if the value does not change                                                                                                         |
| `Exclude from Recorder` | `No`     | `False`        | Excludes attributes from Recorder while preserving state history. Enable for Variables with large attributes to prevent Recorder Errors.                                                                                          |

**How device tracker state is set**

Home Assistant does not let a device tracker use a free-form `location_name` as its state. State is computed as:

1. **`in_zones`**: a list of zone entity IDs such as `zone.home` or `zone.work`. The first active zone becomes the state (`home` when that zone is the home zone).
2. **Latitude / longitude**: if `in_zones` is not set, Home Assistant matches coordinates against your zones (`home`, `not_home`, or a zone name). If both `in_zones` and coordinates are set, **`in_zones` takes priority**.

`location_name` is kept as an extra attribute for compatibility and does **not** change state. Custom place names that are not Home Assistant zones cannot be the entity state; create a zone for that place, or provide coordinates inside an existing zone.

</details>

<details>
<summary><h2>Alternate YAML Configuration</h2></summary>

**Variables created via YAML will all start with `sensor.` and cannot be edited in the UI.**

_You can have a combination of Variables created via the UI and via YAML._

Add the component `variable` to your configuration and declare the variables you want.

| Name                  | yaml                    | Required | Default | Description                                                                                                                     |
|-----------------------|-------------------------|----------|---------|---------------------------------------------------------------------------------------------------------------------------------|
| Variable ID           | `<key>:`                | `Yes`    |         | The desired id of the new sensor (ex. `test_variable` would create an entity_id of `sensor.test_variable`)                      |
| Name                  | `name`                  | `No`     |         | Friendly name of the variable sensor                                                                                            |
| Initial Value         | `value`                 | `No`     |         | Initial value/state of the variable. If `Restore on Restart` is `False`, the variable will reset to this value on every restart |
| Initial Attributes    | `attributes`            | `No`     |         | Initial attributes of the variable. If `Restore on Restart` is `False`, the variable will reset to this value on every restart. `device_class`, `state_class`, and `unit_of_measurement` are applied as native sensor properties. |
| Restore on Restart    | `restore`               | `No`     | `True`  | If `True` will restore previous value on restart. If `False`, will reset to `Initial Value` and `Initial Attributes` on restart |
| Force Update          | `force_update`          | `No`     | `False` | Variable's `last_updated` time will change with any service calls to update the variable even if the value does not change      |
| Exclude from Recorder | `exclude_from_recorder` | `No`     | `False` | Excludes attributes from Recorder while preserving state history. Set to `True` for Variables with large attributes to prevent Recorder Errors. |

#### Example:

```yaml
variable:
  countdown_timer:
    value: 30
    attributes:
      friendly_name: 'Countdown'
      icon: mdi:alarm
  countdown_trigger:
    name: Countdown
    value: False
  light_scene:
    value: 'normal'
    attributes:
      previous: ''
    restore: true
  current_power_usage:
    value: 1
    force_update: true
    attributes:
      state_class: measurement
      device_class: power
      unit_of_measurement: kW

  daily_download:
    value: 0
    restore: true
    attributes:
      state_class: measurement
      unit_of_measurement: GB
      icon: mdi:download
```

</details>

## Services

There are instructions and selectors when the service is called from the Developer Tools or within a Script or Automation.

### `variable.update_sensor`

Used to update the value or attributes of a Sensor Variable

| Name                 | Key                                     | Required | Default | Description                                                                           |
|----------------------|-----------------------------------------|----------|---------|---------------------------------------------------------------------------------------|
| `Targets`            | `target:`<br />&nbsp;&nbsp;`entity_id:` | `Yes`    |         | The entity_ids of one or more sensor variables to update (ex. `sensor.test_variable`) |
| `New Value`          | `value`                                 | `No`     |         | Value/state to change the variable to. One matching pair of wrapping quotes is stripped, so quoted templates still store a numeric state usable in `numeric_state` conditions |
| `New Attributes`     | `attributes`                            | `No`     |         | What to update the attributes to                                                      |
| `Replace Attributes` | `replace_attributes`                    | `No`     | `False` | Replace or merge current attributes (`False` = merge)                                 |

### `variable.update_binary_sensor`

Used to update the value or attributes of a Binary Sensor Variable

| Name                 | Key                                     | Required | Default | Description                                                                                         |
|----------------------|-----------------------------------------|----------|---------|-----------------------------------------------------------------------------------------------------|
| `Targets`            | `target:`<br />&nbsp;&nbsp;`entity_id:` | `Yes`    |         | The entity_ids of one or more binary sensor variables to update (ex. `binary_sensor.test_variable`) |
| `New Value`          | `value`                                 | `No`     |         | Value/state to change the variable to                                                               |
| `New Attributes`     | `attributes`                            | `No`     |         | What to update the attributes to                                                                    |
| `Replace Attributes` | `replace_attributes`                    | `No`     | `False` | Replace or merge current attributes (`False` = merge)                                               |

### `variable.update_device_tracker`

Used to update the value or attributes of a Device Tracker Variable

| Name                   | Key                                     | Required | Default | Description                                                                                           |
|------------------------|-----------------------------------------|----------|---------|-------------------------------------------------------------------------------------------------------|
| `Targets`              | `target:`<br />&nbsp;&nbsp;`entity_id:` | `Yes`    |         | The entity_ids of one or more device tracker variables to update (ex. `device_tracker.test_variable`) |
| `Latitude`             | `latitude`                              | `No`     |         | Latitude. Used for zone matching when `in_zones` is not set.                                      |
| `Longitude`            | `longitude`                             | `No`     |         | Longitude. Used with latitude for zone matching.                                                  |
| `Location Name`        | `location_name`                         | `No`     |         | Extra attribute only; does **not** set state. Logs a deprecation warning.                         |
| `Delete Location Name` | `delete_location_name`                  | `No`     |         | Removes the `location_name` attribute (`boolean`). Does not change state.                         |
| `In Zones`             | `in_zones`                              | `No`     |         | List of zone entity IDs that sets state (e.g. `zone.home`). Takes priority over coordinates when set. |
| `Delete In Zones`      | `delete_in_zones`                       | `No`     |         | Clears `in_zones` so state falls back to coordinates or `not_home`                                |
| `GPS Accuracy`         | `gps_accuracy`                          | `No`     |         | Accuracy in meters                                                                                    |
| `Battery Level`        | `battery_level`                         | `No`     |         | Battery level from 0-100%                                                                             |
| `New Attributes`       | `attributes`                            | `No`     |         | What to update the attributes to                                                                      |
| `Replace Attributes`   | `replace_attributes`                    | `No`     | `False` | Replace or merge current attributes (`False` = merge)                                                  |

### `variable.toggle_binary_sensor`

Used to toggle the state or update attributes of a Binary Sensor Variable. If the binary_sensor state is None, the toggle service will not change the state.

| Name                 | Key                                     | Required | Default | Description                                                                                         |
|----------------------|-----------------------------------------|----------|---------|-----------------------------------------------------------------------------------------------------|
| `Targets`            | `target:`<br />&nbsp;&nbsp;`entity_id:` | `Yes`    |         | The entity_ids of one or more binary sensor variables to toggle (ex. `binary_sensor.test_variable`) |
| `New Attributes`     | `attributes`                            | `No`     |         | What to update the attributes to                                                                    |
| `Replace Attributes` | `replace_attributes`                    | `No`     | `False` | Replace or merge current attributes (`False` = merge)                                               |

### `variable.increment_sensor`

Used to increment the value of a Sensor Variable by a specified amount (works with numeric variables only).

| Name               | Key            | Required | Default | Description                                                                                            |
|--------------------|----------------|----------|---------|--------------------------------------------------------------------------------------------------------|
| `Targets`          | `target:`<br />&nbsp;&nbsp;`entity_id:` | `Yes`    |         | The entity_ids of one or more sensor variables to increment (ex. `sensor.test_counter`)               |
| `Increment Value`  | `value_delta`  | `No`     | `1`     | Amount to increment by (supports positive or negative values)                                          |

### `variable.decrement_sensor`

Used to decrement the value of a Sensor Variable by a specified amount (works with numeric variables only).

| Name               | Key            | Required | Default | Description                                                                                            |
|--------------------|----------------|----------|---------|--------------------------------------------------------------------------------------------------------|
| `Targets`          | `target:`<br />&nbsp;&nbsp;`entity_id:` | `Yes`    |         | The entity_ids of one or more sensor variables to decrement (ex. `sensor.test_counter`)               |
| `Decrement Value`  | `value_delta`  | `No`     | `1`     | Amount to decrement by (supports positive or negative values)                                          |

<details>
<summary><h2>Legacy Services</h2></summary>

#### These will only work for Sensor Variables
_These services are from the previous version of the integration and are being kept for pre-existing automations and scripts. In general, the new `variable.update_` and `variable.toggle_` services above should be used going forward._

Both services are similar and used to update the value or attributes of a Sensor Variable. `variable.set_variable` uses just the `variable_id` and `variable.set_entity` uses the full `entity_id`. There are instructions and selectors when the service is called from the Developer Tools or within a Script or Automation.

### `variable.set_variable`

| Name                 | Key                  | Required | Default | Description                                                                                                   |
|----------------------|----------------------|----------|---------|---------------------------------------------------------------------------------------------------------------|
| `Variable ID`        | `variable`           | `Yes`    |         | The id of the sensor variable to update (ex. `test_variable` for a sensor variable of `sensor.test_variable`) |
| `Value`              | `value`              | `No`     |         | Value/state to change the variable to                                                                         |
| `Attributes`         | `attributes`         | `No`     |         | What to update the attributes to                                                                              |
| `Replace Attributes` | `replace_attributes` | `No`     | `False` | Replace or merge current attributes (`False` = merge)                                                         |

### `variable.set_entity`

| Name                 | Key                  | Required | Default | Description                                                                 |
|----------------------|----------------------|----------|---------|-----------------------------------------------------------------------------|
| `Entity ID`          | `entity`             | `Yes`    |         | The entity_id of the sensor variable to update (ex. `sensor.test_variable`) |
| `Value`              | `value`              | `No`     |         | Value/state to change the variable to                                       |
| `Attributes`         | `attributes`         | `No`     |         | What to update the attributes to                                            |
| `Replace Attributes` | `replace_attributes` | `No`     | `False` | Replace or merge current attributes (`False` = merge)                       |

</details>

## Example service calls

```yaml
action:
  - service: variable.update_sensor
    data:
      value: 30
    target:
      entity_id: sensor.test_timer
```
```yaml
action:
  - service: variable.update_sensor
    data:
      value: >-
        {{trigger.to_state.name|replace('Motion Sensor','')}}
      attributes:
        history_1: "{{states('sensor.last_motion')}}"
        history_2: "{{state_attr('sensor.last_motion','history_1')}}"
        history_3: "{{state_attr('sensor.last_motion','history_2')}}"
    target:
      entity_id: sensor.last_motion
```
```yaml
action:
  - service: variable.update_binary_sensor
    data:
      value: true
      replace_attributes: true
      attributes:
        country: USA
    target:
      entity_id: binary_sensor.test_binary_var
```
```yaml
action:
  - service: variable.increment_sensor
    data:
      value_delta: 1
    target:
      entity_id: sensor.test_counter
```
```yaml
action:
  - service: variable.decrement_sensor
    data:
      value_delta: 5
    target:
      entity_id: sensor.test_counter
```

## Example timer automation

* Create a sensor variable with the Variable ID of `test_timer` and Initial Value of `0`

```yaml
script:
  schedule_test_timer:
    sequence:
      - service: variable.update_sensor
        data:
          value: 30
        target:
          entity_id: sensor.test_timer
      - service: automation.turn_on
        data:
          entity_id: automation.test_timer_countdown

automation:
  - alias: test_timer_countdown
    initial_state: 'off'
    trigger:
      - platform: time_pattern
        seconds: '/1'
    action:
      - service: variable.update_sensor
        data:
          value: >
            {{ [((states('sensor.test_timer') | int(default=0)) - 1), 0] | max }}
        target:
          entity_id: sensor.test_timer
  - alias: test_timer_trigger
    trigger:
      platform: state
      entity_id: sensor.test_timer
      to: '0'
    action:
      - service: automation.turn_off
        data:
          entity_id: automation.test_timer_countdown
```

## Examples

<details>
<summary><h3>Play and Save TTS Messages + Message History - Made by <a href="https://github.com/jazzyisj">jazzyisj</a></h3></summary>

#### https://github.com/jazzyisj/save-tts-messages

This is more or less an answering machine (remember those?) for your TTS messages. When you play a TTS message that you want saved under certain conditions (i.e. nobody is home), you will call the script Play or Save TTS Message script.play_or_save_message instead of calling your tts service (or Alexa notify) directly. The script will decide whether to play the message immediately, or save it based on the conditions you specify. If a saved tts message is repeated another message is not saved, only the timestamp is updated to the most recent instance.

Messages are played back using the Play Saved TTS Messages script "script.play_saved_tts_messages". Set an appropriate trigger (for example when you arrive home) in the automation Play Saved Messages automation.play_saved_messages automation to call this script automatically.

Saved messages will survive restarts.

BONUS - OPTIONAL TTS MESSAGE HISTORY

You can find the full documentation on how to do this and adjust this to your needs in the [Save TTS Messages repository](https://github.com/jazzyisj/save-tts-messages).
</details>

#### More examples can be found in the [examples](https://github.com/wibias/hass-variables/tree/master/examples) folder.

## Removing variables safely

This project implements safeguards to avoid orphaned variables and entity registry entries. If you need to remove a variable created via YAML or via the UI, follow the steps below.

Removing YAML-created variables

- Remove the variable entry from your `configuration.yaml` (under the `variable:` section).
- Reload or restart Home Assistant.
- The integration will detect YAML-imported variables that are no longer present and automatically remove their corresponding config entries. If an entry remains, you can remove it from Settings → Integrations → Variables+History → `...` → Delete.

Removing UI-created variables

- In Home Assistant go to Settings → Integrations → Variables+History and select the variable to configure.
- Use the integration's UI to remove or delete the variable. This will delete the Config Entry and the integration now also cleans up entity registry entries during unload so the entity should disappear from the Entities list.

<details>
<summary><b>Advanced:</b> If an entity remains without a unique_id (orphaned entity)</summary>

1. Open Settings → Devices & Services → Entities and search for the orphaned entity.
2. If the entity has no unique ID and cannot be removed via the UI, go to Settings → Devices & Services → Entities → three-dot menu → Delete (if available). If that is not available, you can remove the entity registry entry manually by editing the `.storage/core.entity_registry` file in your Home Assistant config (advanced — backup first) or use the UI or `entity_registry` service from a local script.
3. After removing the registry entry, restart Home Assistant. The entity should no longer appear.

Note: Manual edits to `.storage` are advanced and should be done carefully with a backup. The integration now tries to prevent these situations by removing YAML-missing entries and cleaning up entity registry entries when a config entry unloads.

</details>

## Development

Tests need Python 3.14.2 or newer. In a virtual environment, install the dependencies and run the tests and checks:

```bash
python -m pip install --group dev -e . --config-settings editable_mode=compat
python -m pytest
prek run --all-files
```

CI also runs the tests against the minimum supported Home Assistant release declared in `hacs.json`. The `pytest Home Assistant minimum` job in `.github/workflows/pytest_coverage.yml` tests exactly that release, together with the oldest test plugin release that supports it: `pytest-homeassistant` from Home Assistant 2026.11, otherwise its predecessor `pytest-homeassistant-custom-component`. It installs them with the `pytest-base` dependency group in a separate environment. Raising the minimum in `hacs.json` is all the job needs; it fails if that release or a matching test plugin cannot be installed. Both test jobs require Python 3.14.2 or newer, check that exactly one test plugin is installed and that it matches the installed Home Assistant, and print the versions they use.

For pull requests from bots or labeled `dependencies`, both check names are reported
without running tests.

Import Home Assistant test plugin helpers such as `MockConfigEntry` from `tests.common` so the tests work with either plugin, and never install both plugins in one environment. To reproduce the minimum job locally, run its steps from a separate clone with `RUNNER_TEMP` set to a scratch directory. The steps create their own `.venv`, so use a directory that doesn't have one.

## Attribution

Forked and updated from initial integration developed by [rogro82](https://github.com/rogro82)

[integration-usage-shield]: https://img.shields.io/badge/dynamic/json?color=41BDF5&logo=home-assistant&label=integration%20usage&suffix=%20installs&cacheSeconds=15600&url=https%3A%2F%2Fanalytics.home-assistant.io%2Fcustom_integrations.json&query=%24.variable.total&style=for-the-badge
[commits-shield]: https://img.shields.io/github/last-commit/Wibias/hass-variables?style=for-the-badge
[commits]: https://github.com/Wibias/hass-variables/commits/master
[hacs]: https://hacs.xyz
[hacsbadge]: https://img.shields.io/badge/HACS-Default-blue.svg?style=for-the-badge
[license-shield]: https://img.shields.io/github/license/Wibias/hass-variables.svg?style=for-the-badge
[downloads-latest-shield]: https://img.shields.io/github/downloads-pre/Wibias/hass-variables/latest/total?style=for-the-badge
[downloads-shield]: https://img.shields.io/github/downloads/Wibias/hass-variables/total?style=for-the-badge&label=total%20downloads
[release-date-shield]: https://img.shields.io/github/release-date/Wibias/hass-variables?display_date=published_at&style=for-the-badge
[releases-shield]: https://img.shields.io/github/v/release/Wibias/hass-variables?style=for-the-badge
[releases]: https://github.com/Wibias/hass-variables/releases
[coverage]: https://htmlpreview.github.io/?https://github.com/Wibias/hass-variables/blob/python-coverage-comment-action-data/htmlcov/index.html
[coverage-shield]: https://img.shields.io/endpoint?url=https%3A%2F%2Fraw.githubusercontent.com%2FWibias%2Fhass-variables%2Fpython-coverage-comment-action-data%2Fendpoint.json&style=for-the-badge
