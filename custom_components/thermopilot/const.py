"""Constants for ThermoPilot."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "thermopilot"
INTEGRATION_VERSION: Final = "0.1.2"
PLATFORMS: Final = ["climate", "sensor"]
STORAGE_VERSION: Final = 1

CONF_NAME: Final = "name"
CONF_DEVICE_ID: Final = "device_id"
CONF_STRATEGY: Final = "strategy"
CONF_MODES: Final = "modes"
CONF_ENABLE_DRY: Final = "enable_dry"
CONF_TEMPERATURE_SENSORS: Final = "temperature_sensors"
CONF_HUMIDITY_SENSORS: Final = "humidity_sensors"
CONF_PRESSURE_SENSORS: Final = "pressure_sensors"
CONF_COOL_COMMAND: Final = "cool_command"
CONF_HEAT_COMMAND: Final = "heat_command"
CONF_DRY_COMMAND: Final = "dry_command"
CONF_TOGGLE_COMMAND: Final = "toggle_command"
CONF_POWER_SENSOR: Final = "power_sensor"

STRATEGY_DISCRETE: Final = "discrete_commands"
STRATEGY_POWER_TOGGLE: Final = "toggle_with_power_feedback"

MODE_COOL: Final = "cool"
MODE_HEAT: Final = "heat"
MODE_DRY: Final = "dry"
MODE_OFF: Final = "off"

OPT_MIN_TEMP: Final = "minimum_temperature"
OPT_MAX_TEMP: Final = "maximum_temperature"
OPT_TEMP_STEP: Final = "temperature_step"
OPT_HYSTERESIS: Final = "hysteresis"
OPT_TEMP_VALID_MIN: Final = "temperature_valid_min"
OPT_TEMP_VALID_MAX: Final = "temperature_valid_max"
OPT_HUMIDITY_VALID_MIN: Final = "humidity_valid_min"
OPT_HUMIDITY_VALID_MAX: Final = "humidity_valid_max"
OPT_PRESSURE_VALID_MIN: Final = "pressure_valid_min"
OPT_PRESSURE_VALID_MAX: Final = "pressure_valid_max"
OPT_STARTUP_DELAY: Final = "startup_command_delay"
OPT_RESTORE_OFF_ON_DELAY: Final = "restore_off_on_delay"
OPT_DRY_ON: Final = "dry_humidity_on"
OPT_DRY_OFF: Final = "dry_humidity_off"
OPT_DRY_MIN_INTERVAL: Final = "dry_minimum_interval"
OPT_POWER_OFF_BELOW: Final = "power_off_below"
OPT_POWER_ON_ABOVE: Final = "power_on_above"
OPT_POWER_STABILIZATION: Final = "power_stabilization"
OPT_TOGGLE_PULSE: Final = "toggle_pulse_duration"
OPT_FEEDBACK_TIMEOUT: Final = "feedback_timeout"
OPT_MAX_ATTEMPTS: Final = "maximum_attempts"
OPT_NOTIFICATION_SERVICE: Final = "notification_service"

PRESET_HOME: Final = "home"
PRESET_AWAY: Final = "away"
PRESET_SLEEP: Final = "sleep"
PRESET_COMFORT: Final = "comfort"
PRESET_NONE: Final = "none"
PRESETS: Final = [PRESET_HOME, PRESET_AWAY, PRESET_SLEEP, PRESET_COMFORT]

DEFAULTS: Final = {
    OPT_MIN_TEMP: 16.0,
    OPT_MAX_TEMP: 30.0,
    OPT_TEMP_STEP: 0.1,
    OPT_HYSTERESIS: 0.2,
    OPT_TEMP_VALID_MIN: -20.0,
    OPT_TEMP_VALID_MAX: 60.0,
    OPT_HUMIDITY_VALID_MIN: 0.0,
    OPT_HUMIDITY_VALID_MAX: 100.0,
    OPT_PRESSURE_VALID_MIN: 800.0,
    OPT_PRESSURE_VALID_MAX: 1200.0,
    OPT_STARTUP_DELAY: 60,
    OPT_RESTORE_OFF_ON_DELAY: 10,
    OPT_DRY_ON: 60.0,
    OPT_DRY_OFF: 55.0,
    OPT_DRY_MIN_INTERVAL: 300,
    OPT_POWER_OFF_BELOW: 50.0,
    OPT_POWER_ON_ABOVE: 200.0,
    OPT_POWER_STABILIZATION: 30,
    OPT_TOGGLE_PULSE: 2,
    OPT_FEEDBACK_TIMEOUT: 35,
    OPT_MAX_ATTEMPTS: 3,
    OPT_NOTIFICATION_SERVICE: "",
    "preset_home_cool": 26.0,
    "preset_home_heat": 21.0,
    "preset_away_cool": 28.0,
    "preset_away_heat": 17.0,
    "preset_sleep_cool": 26.2,
    "preset_sleep_heat": 18.0,
    "preset_comfort_cool": 24.0,
    "preset_comfort_heat": 20.0,
}


def option_value(entry, key: str):
    """Return an option value with the integration default."""
    return entry.options.get(key, DEFAULTS[key])
