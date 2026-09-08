"""Config and options flows for ThermoPilot."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.helpers import selector
from homeassistant.util import slugify

from .const import (
    CONF_COOL_COMMAND,
    CONF_DEVICE_ID,
    CONF_DRY_COMMAND,
    CONF_ENABLE_DRY,
    CONF_HEAT_COMMAND,
    CONF_HUMIDITY_SENSORS,
    CONF_MODES,
    CONF_NAME,
    CONF_POWER_SENSOR,
    CONF_PRESSURE_SENSORS,
    CONF_STRATEGY,
    CONF_TEMPERATURE_SENSORS,
    CONF_TOGGLE_COMMAND,
    DEFAULTS,
    DOMAIN,
    MODE_COOL,
    MODE_DRY,
    MODE_HEAT,
    OPT_DRY_DEW_POINT_HYSTERESIS,
    OPT_DRY_MIN_INTERVAL,
    OPT_DRY_OFF,
    OPT_DRY_ON,
    OPT_FEEDBACK_TIMEOUT,
    OPT_HUMIDITY_VALID_MAX,
    OPT_HUMIDITY_VALID_MIN,
    OPT_HUMIDITY_STEP,
    OPT_HYSTERESIS,
    OPT_MAX_ATTEMPTS,
    OPT_MAX_HUMIDITY,
    OPT_MAX_TEMP,
    OPT_MIN_TEMP,
    OPT_MIN_HUMIDITY,
    OPT_NOTIFICATION_SERVICE,
    OPT_POWER_OFF_BELOW,
    OPT_POWER_ON_ABOVE,
    OPT_POWER_STABILIZATION,
    OPT_POWER_UNAVAILABLE_GRACE,
    OPT_PRESSURE_VALID_MAX,
    OPT_PRESSURE_VALID_MIN,
    OPT_RESTORE_OFF_ON_DELAY,
    OPT_STARTUP_DELAY,
    OPT_TEMP_STEP,
    OPT_TEMP_VALID_MAX,
    OPT_TEMP_VALID_MIN,
    OPT_TOGGLE_PULSE,
    PRESETS,
    STRATEGY_DISCRETE,
    STRATEGY_POWER_TOGGLE,
)


def _entity_selector(domain: str, *, multiple: bool = False):
    return selector.EntitySelector(
        selector.EntitySelectorConfig(domain=domain, multiple=multiple)
    )


def _number(minimum: float, maximum: float, step: float = 0.1):
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=minimum,
            max=maximum,
            step=step,
            mode=selector.NumberSelectorMode.BOX,
        )
    )


class ThermoPilotConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the ThermoPilot setup wizard."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect the name and hardware strategy."""
        if user_input is not None:
            self._data.update(user_input)
            return await self.async_step_modes()

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME): selector.TextSelector(),
                vol.Required(CONF_STRATEGY): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[STRATEGY_DISCRETE, STRATEGY_POWER_TOGGLE],
                        translation_key="strategy",
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema)

    async def async_step_modes(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect supported thermal modes and optional dry support."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input.get(CONF_MODES):
                errors[CONF_MODES] = "select_at_least_one_mode"
            else:
                self._data.update(user_input)
                if self._data[CONF_STRATEGY] != STRATEGY_DISCRETE:
                    self._data[CONF_ENABLE_DRY] = False
                return await self.async_step_sensors()

        fields: dict[Any, Any] = {
            vol.Required(CONF_MODES, default=[MODE_COOL, MODE_HEAT]): (
                selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[MODE_COOL, MODE_HEAT],
                        multiple=True,
                        translation_key="thermal_mode",
                    )
                )
            )
        }
        if self._data[CONF_STRATEGY] == STRATEGY_DISCRETE:
            fields[vol.Optional(CONF_ENABLE_DRY, default=False)] = bool
        return self.async_show_form(
            step_id="modes", data_schema=vol.Schema(fields), errors=errors
        )

    async def async_step_sensors(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect environment sensors."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input.get(CONF_TEMPERATURE_SENSORS):
                errors[CONF_TEMPERATURE_SENSORS] = "temperature_required"
            elif self._data.get(CONF_ENABLE_DRY) and not user_input.get(
                CONF_HUMIDITY_SENSORS
            ):
                errors[CONF_HUMIDITY_SENSORS] = "humidity_required_for_dry"
            else:
                self._data.update(user_input)
                return await self.async_step_hardware()

        schema = vol.Schema(
            {
                vol.Required(CONF_TEMPERATURE_SENSORS): _entity_selector(
                    "sensor", multiple=True
                ),
                vol.Optional(CONF_HUMIDITY_SENSORS, default=[]): _entity_selector(
                    "sensor", multiple=True
                ),
                vol.Optional(CONF_PRESSURE_SENSORS, default=[]): _entity_selector(
                    "sensor", multiple=True
                ),
            }
        )
        return self.async_show_form(
            step_id="sensors", data_schema=schema, errors=errors
        )

    async def async_step_hardware(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect only hardware fields relevant to the chosen strategy."""
        if user_input is not None:
            self._data.update(user_input)
            device_id = slugify(self._data[CONF_NAME])
            await self.async_set_unique_id(device_id)
            self._abort_if_unique_id_configured()
            self._data[CONF_DEVICE_ID] = device_id
            return self.async_create_entry(
                title=self._data[CONF_NAME], data=self._data
            )

        fields: dict[Any, Any] = {}
        modes = self._data[CONF_MODES]
        if self._data[CONF_STRATEGY] == STRATEGY_DISCRETE:
            if MODE_COOL in modes:
                fields[vol.Required(CONF_COOL_COMMAND)] = _entity_selector("switch")
            if MODE_HEAT in modes:
                fields[vol.Required(CONF_HEAT_COMMAND)] = _entity_selector("switch")
            if self._data.get(CONF_ENABLE_DRY):
                fields[vol.Required(CONF_DRY_COMMAND)] = _entity_selector("switch")
            fields[vol.Optional(CONF_POWER_SENSOR)] = _entity_selector("sensor")
        else:
            fields[vol.Required(CONF_TOGGLE_COMMAND)] = _entity_selector("switch")
            fields[vol.Required(CONF_POWER_SENSOR)] = _entity_selector("sensor")

        return self.async_show_form(
            step_id="hardware", data_schema=vol.Schema(fields)
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        """Return the advanced options flow."""
        return ThermoPilotOptionsFlow()

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Update sensors, supported modes and hardware entities."""
        entry = self._get_reconfigure_entry()
        current = entry.data
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input.get(CONF_MODES):
                errors[CONF_MODES] = "select_at_least_one_mode"
            elif not user_input.get(CONF_TEMPERATURE_SENSORS):
                errors[CONF_TEMPERATURE_SENSORS] = "temperature_required"
            elif user_input.get(CONF_ENABLE_DRY) and not user_input.get(
                CONF_HUMIDITY_SENSORS
            ):
                errors[CONF_HUMIDITY_SENSORS] = "humidity_required_for_dry"
            elif user_input.get(CONF_ENABLE_DRY) and not user_input.get(
                CONF_DRY_COMMAND
            ):
                errors[CONF_DRY_COMMAND] = "dry_command_required"
            elif (
                current[CONF_STRATEGY] == STRATEGY_DISCRETE
                and MODE_COOL in user_input[CONF_MODES]
                and not user_input.get(CONF_COOL_COMMAND)
            ):
                errors[CONF_COOL_COMMAND] = "mode_command_required"
            elif (
                current[CONF_STRATEGY] == STRATEGY_DISCRETE
                and MODE_HEAT in user_input[CONF_MODES]
                and not user_input.get(CONF_HEAT_COMMAND)
            ):
                errors[CONF_HEAT_COMMAND] = "mode_command_required"
            else:
                await self.async_set_unique_id(entry.unique_id)
                self._abort_if_unique_id_mismatch()
                updated = {**current, **user_input}
                if current[CONF_STRATEGY] != STRATEGY_DISCRETE:
                    updated[CONF_ENABLE_DRY] = False
                elif not user_input.get(CONF_POWER_SENSOR):
                    updated.pop(CONF_POWER_SENSOR, None)
                return self.async_update_reload_and_abort(
                    entry, data_updates=updated
                )

        fields: dict[Any, Any] = {
            vol.Required(CONF_MODES, default=current[CONF_MODES]): (
                selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=[MODE_COOL, MODE_HEAT],
                        multiple=True,
                        translation_key="thermal_mode",
                    )
                )
            ),
            vol.Required(
                CONF_TEMPERATURE_SENSORS,
                default=current[CONF_TEMPERATURE_SENSORS],
            ): _entity_selector("sensor", multiple=True),
            vol.Optional(
                CONF_HUMIDITY_SENSORS,
                default=current.get(CONF_HUMIDITY_SENSORS, []),
            ): _entity_selector("sensor", multiple=True),
            vol.Optional(
                CONF_PRESSURE_SENSORS,
                default=current.get(CONF_PRESSURE_SENSORS, []),
            ): _entity_selector("sensor", multiple=True),
        }
        if current[CONF_STRATEGY] == STRATEGY_DISCRETE:
            fields[vol.Optional(
                CONF_ENABLE_DRY, default=current.get(CONF_ENABLE_DRY, False)
            )] = bool
            cool_marker = (
                vol.Optional(CONF_COOL_COMMAND, default=current[CONF_COOL_COMMAND])
                if CONF_COOL_COMMAND in current
                else vol.Optional(CONF_COOL_COMMAND)
            )
            heat_marker = (
                vol.Optional(CONF_HEAT_COMMAND, default=current[CONF_HEAT_COMMAND])
                if CONF_HEAT_COMMAND in current
                else vol.Optional(CONF_HEAT_COMMAND)
            )
            dry_marker = (
                vol.Optional(CONF_DRY_COMMAND, default=current[CONF_DRY_COMMAND])
                if CONF_DRY_COMMAND in current
                else vol.Optional(CONF_DRY_COMMAND)
            )
            fields[cool_marker] = _entity_selector("switch")
            fields[heat_marker] = _entity_selector("switch")
            fields[dry_marker] = _entity_selector("switch")
            power_marker = (
                vol.Optional(CONF_POWER_SENSOR, default=current[CONF_POWER_SENSOR])
                if CONF_POWER_SENSOR in current
                else vol.Optional(CONF_POWER_SENSOR)
            )
            fields[power_marker] = _entity_selector("sensor")
        else:
            fields[vol.Required(
                CONF_TOGGLE_COMMAND, default=current[CONF_TOGGLE_COMMAND]
            )] = _entity_selector("switch")
            fields[vol.Required(
                CONF_POWER_SENSOR, default=current[CONF_POWER_SENSOR]
            )] = _entity_selector("sensor")

        return self.async_show_form(
            step_id="reconfigure", data_schema=vol.Schema(fields), errors=errors
        )


class ThermoPilotOptionsFlow(config_entries.OptionsFlow):
    """Manage advanced ThermoPilot settings after initial setup."""

    def _current(self, key: str):
        return self.config_entry.options.get(key, DEFAULTS[key])

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show advanced options with validated defaults."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if user_input[OPT_MIN_TEMP] >= user_input[OPT_MAX_TEMP]:
                errors["base"] = "invalid_temperature_range"
            elif user_input[OPT_TEMP_VALID_MIN] >= user_input[OPT_TEMP_VALID_MAX]:
                errors["base"] = "invalid_sensor_range"
            elif user_input[OPT_HUMIDITY_VALID_MIN] >= user_input[OPT_HUMIDITY_VALID_MAX]:
                errors["base"] = "invalid_sensor_range"
            elif (
                self.config_entry.data.get(CONF_ENABLE_DRY)
                and user_input[OPT_MIN_HUMIDITY] >= user_input[OPT_MAX_HUMIDITY]
            ):
                errors["base"] = "invalid_humidity_target_range"
            elif user_input[OPT_PRESSURE_VALID_MIN] >= user_input[OPT_PRESSURE_VALID_MAX]:
                errors["base"] = "invalid_sensor_range"
            elif (
                self.config_entry.data.get(CONF_POWER_SENSOR)
                and user_input[OPT_POWER_OFF_BELOW] >= user_input[OPT_POWER_ON_ABOVE]
            ):
                errors["base"] = "invalid_power_range"
            else:
                for legacy_key in (OPT_DRY_ON, OPT_DRY_OFF):
                    if legacy_key in self.config_entry.options:
                        user_input[legacy_key] = self.config_entry.options[legacy_key]
                return self.async_create_entry(title="", data=user_input)

        fields: dict[Any, Any] = {
            vol.Required(OPT_MIN_TEMP, default=self._current(OPT_MIN_TEMP)): _number(5, 25),
            vol.Required(OPT_MAX_TEMP, default=self._current(OPT_MAX_TEMP)): _number(20, 40),
            vol.Required(OPT_TEMP_STEP, default=self._current(OPT_TEMP_STEP)): _number(0.1, 1, 0.1),
            vol.Required(OPT_HYSTERESIS, default=self._current(OPT_HYSTERESIS)): _number(0.1, 5, 0.1),
            vol.Required(OPT_TEMP_VALID_MIN, default=self._current(OPT_TEMP_VALID_MIN)): _number(-50, 20),
            vol.Required(OPT_TEMP_VALID_MAX, default=self._current(OPT_TEMP_VALID_MAX)): _number(20, 100),
            vol.Required(OPT_HUMIDITY_VALID_MIN, default=self._current(OPT_HUMIDITY_VALID_MIN)): _number(0, 100),
            vol.Required(OPT_HUMIDITY_VALID_MAX, default=self._current(OPT_HUMIDITY_VALID_MAX)): _number(0, 100),
            vol.Required(OPT_PRESSURE_VALID_MIN, default=self._current(OPT_PRESSURE_VALID_MIN)): _number(500, 1200),
            vol.Required(OPT_PRESSURE_VALID_MAX, default=self._current(OPT_PRESSURE_VALID_MAX)): _number(800, 1500),
            vol.Required(OPT_STARTUP_DELAY, default=self._current(OPT_STARTUP_DELAY)): _number(10, 15, 1),
            vol.Required(OPT_RESTORE_OFF_ON_DELAY, default=self._current(OPT_RESTORE_OFF_ON_DELAY)): _number(1, 120, 1),
        }

        if self.config_entry.data.get(CONF_ENABLE_DRY):
            fields.update(
                {
                    vol.Required(OPT_MIN_HUMIDITY, default=self._current(OPT_MIN_HUMIDITY)): _number(20, 60, 1),
                    vol.Required(OPT_MAX_HUMIDITY, default=self._current(OPT_MAX_HUMIDITY)): _number(25, 70, 1),
                    vol.Required(OPT_HUMIDITY_STEP, default=self._current(OPT_HUMIDITY_STEP)): _number(1, 5, 1),
                    vol.Required(
                        OPT_DRY_DEW_POINT_HYSTERESIS,
                        default=self._current(OPT_DRY_DEW_POINT_HYSTERESIS),
                    ): _number(0.1, 5, 0.1),
                    vol.Required(OPT_DRY_MIN_INTERVAL, default=self._current(OPT_DRY_MIN_INTERVAL)): _number(0, 3600, 1),
                }
            )

        if self.config_entry.data.get(CONF_POWER_SENSOR):
            fields.update(
                {
                    vol.Required(OPT_POWER_OFF_BELOW, default=self._current(OPT_POWER_OFF_BELOW)): _number(0, 1000),
                    vol.Required(OPT_POWER_ON_ABOVE, default=self._current(OPT_POWER_ON_ABOVE)): _number(1, 5000),
                    vol.Required(OPT_POWER_STABILIZATION, default=self._current(OPT_POWER_STABILIZATION)): _number(0, 300, 1),
                    vol.Required(OPT_POWER_UNAVAILABLE_GRACE, default=self._current(OPT_POWER_UNAVAILABLE_GRACE)): _number(30, 900, 1),
                    vol.Required(OPT_FEEDBACK_TIMEOUT, default=self._current(OPT_FEEDBACK_TIMEOUT)): _number(1, 300, 1),
                    vol.Required(OPT_MAX_ATTEMPTS, default=self._current(OPT_MAX_ATTEMPTS)): _number(1, 10, 1),
                    vol.Optional(OPT_NOTIFICATION_SERVICE, default=self._current(OPT_NOTIFICATION_SERVICE)): selector.TextSelector(),
                }
            )
            if self.config_entry.data[CONF_STRATEGY] == STRATEGY_POWER_TOGGLE:
                fields[vol.Required(
                    OPT_TOGGLE_PULSE, default=self._current(OPT_TOGGLE_PULSE)
                )] = _number(0.1, 30, 0.1)

        for preset in PRESETS:
            for mode in self.config_entry.data[CONF_MODES]:
                key = f"preset_{preset}_{mode}"
                fields[vol.Required(key, default=self._current(key))] = _number(5, 40)
            if self.config_entry.data.get(CONF_ENABLE_DRY):
                key = f"preset_{preset}_{MODE_DRY}"
                fields[vol.Required(key, default=self._current(key))] = _number(-5, 25)

        return self.async_show_form(
            step_id="init", data_schema=vol.Schema(fields), errors=errors
        )
