"""Runtime controller for ThermoPilot."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    CONF_COOL_COMMAND,
    CONF_DEVICE_ID,
    CONF_DRY_COMMAND,
    CONF_ENABLE_DRY,
    CONF_HEAT_COMMAND,
    CONF_HUMIDITY_SENSORS,
    CONF_MODES,
    CONF_POWER_SENSOR,
    CONF_PRESSURE_SENSORS,
    CONF_STRATEGY,
    CONF_TEMPERATURE_SENSORS,
    CONF_TOGGLE_COMMAND,
    DEFAULTS,
    DOMAIN,
    INTEGRATION_VERSION,
    MODE_COOL,
    MODE_DRY,
    MODE_HEAT,
    MODE_OFF,
    OPT_DRY_MIN_INTERVAL,
    OPT_DRY_DEW_POINT_HYSTERESIS,
    OPT_FEEDBACK_TIMEOUT,
    OPT_HUMIDITY_VALID_MAX,
    OPT_HUMIDITY_VALID_MIN,
    OPT_MAX_HUMIDITY,
    OPT_HYSTERESIS,
    OPT_MAX_ATTEMPTS,
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
    OPT_TEMP_VALID_MAX,
    OPT_TEMP_VALID_MIN,
    OPT_TOGGLE_PULSE,
    PRESET_HOME,
    PRESET_NONE,
    PRESETS,
    STORAGE_VERSION,
    STRATEGY_DISCRETE,
    STRATEGY_POWER_TOGGLE,
)
from .models import (
    ModeState,
    PersistedState,
    bounded_dew_point,
    classify_power,
    dry_decision,
    dew_point_celsius,
    perceived_temperature,
    power_target_reached,
    relative_humidity_for_dew_point,
    thermal_decision,
    valid_average,
)

_LOGGER = logging.getLogger(__name__)


class ThermoPilotController:
    """Coordinate one configured ThermoPilot thermostat."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.data = entry.data
        self.strategy = self.data[CONF_STRATEGY]
        self.device_id = self.data[CONF_DEVICE_ID]
        self.store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self.state: PersistedState
        self.current_temperature: float | None = None
        self.current_humidity: float | None = None
        self.current_pressure: float | None = None
        self.perceived_temperature: float | None = None
        self.hvac_action = "off"
        self.available = True
        self.commands_blocked = True
        self.manual_mode_unknown = False
        self.sensor_health: dict[str, Any] = {}
        self.last_command_result = "none"
        self.last_error: str | None = None
        self.started_at = dt_util.utcnow().isoformat()
        self._listeners: list[Callable[[], None]] = []
        self._update_callbacks: list[Callable[[], None]] = []
        self._tasks: set[asyncio.Task] = set()
        self._command_lock = asyncio.Lock()
        self._evaluation_lock = asyncio.Lock()
        self._command_pending = False
        self._confirmation_task: asyncio.Task | None = None
        self._confirmation_generation = 0
        self._power_feedback_event = asyncio.Event()
        self._environment_evaluation_cancel: Callable[[], None] | None = None
        self._power_debounce_cancel: Callable[[], None] | None = None
        self._last_power_classification = "unknown"
        self._initialized = False
        self._power_unavailable_cancel: Callable[[], None] | None = None
        self._power_outage_notified = False

    def option(self, key: str):
        """Return a configured advanced option or its default."""
        value = self.entry.options.get(key, DEFAULTS[key])
        if key == OPT_STARTUP_DELAY:
            return min(15.0, max(10.0, float(value)))
        return value

    @property
    def supported_modes(self) -> list[str]:
        """Return configured HVAC modes including off and optional dry."""
        modes = [MODE_OFF, *self.data[CONF_MODES]]
        if self.data.get(CONF_ENABLE_DRY):
            modes.append(MODE_DRY)
        return modes

    @property
    def has_power_feedback(self) -> bool:
        return bool(self.data.get(CONF_POWER_SENSOR))

    @property
    def target_temperature(self) -> float | None:
        """Return target for the active or last selected thermal mode."""
        if self.state.hvac_mode == MODE_DRY:
            return None
        mode = self._settings_mode()
        return self.state.modes[mode].target if mode in self.state.modes else None

    @property
    def target_humidity(self) -> float | None:
        """Return the temperature-adaptive RH equivalent of the dry target."""
        target_dew_point = self.effective_dry_target_dew_point
        if target_dew_point is None:
            return None
        return relative_humidity_for_dew_point(
            self.current_temperature, target_dew_point
        )

    @property
    def effective_dry_target_dew_point(self) -> float | None:
        """Return the Dry target constrained to the advertised RH range."""
        if not self.data.get(CONF_ENABLE_DRY) or MODE_DRY not in self.state.modes:
            return None
        return bounded_dew_point(
            self.current_temperature,
            self.state.modes[MODE_DRY].target,
            float(self.option(OPT_MIN_HUMIDITY)),
            float(self.option(OPT_MAX_HUMIDITY)),
        )

    @property
    def current_dew_point(self) -> float | None:
        """Return current dew point for diagnostics and dry decisions."""
        return dew_point_celsius(self.current_temperature, self.current_humidity)

    @property
    def preset(self) -> str:
        """Return preset for the active or last selected thermal mode."""
        mode = self._preset_settings_mode()
        return self.state.modes[mode].preset if mode in self.state.modes else PRESET_NONE

    def preset_values(self, preset: str, mode: str) -> float:
        """Return one editable standard preset value."""
        return float(self.option(f"preset_{preset}_{mode}"))

    def _default_mode_states(self) -> tuple[dict[str, ModeState], str]:
        modes: dict[str, ModeState] = {}
        for mode in self.data[CONF_MODES]:
            modes[mode] = ModeState(self.preset_values(PRESET_HOME, mode), PRESET_HOME)
        if self.data.get(CONF_ENABLE_DRY):
            modes[MODE_DRY] = ModeState(
                self.preset_values(PRESET_HOME, MODE_DRY), PRESET_HOME
            )
        fallback = MODE_COOL if MODE_COOL in modes else MODE_HEAT
        return modes, fallback

    async def async_initialize(self) -> None:
        """Restore state, register listeners and begin guarded startup."""
        default_modes, fallback = self._default_mode_states()
        raw = await self.store.async_load() or {}
        self.state = PersistedState.from_dict(raw, default_modes, fallback)
        self._read_environment()

        environment_entities = {
            *self.data[CONF_TEMPERATURE_SENSORS],
            *self.data.get(CONF_HUMIDITY_SENSORS, []),
            *self.data.get(CONF_PRESSURE_SENSORS, []),
        }
        if environment_entities:
            self._listeners.append(
                async_track_state_change_event(
                    self.hass, environment_entities, self._environment_changed
                )
            )
        self.available = False
        self.last_command_result = "initializing"
        if self.has_power_feedback:
            self._last_power_classification = self.power_classification
            self._listeners.append(
                async_track_state_change_event(
                    self.hass,
                    [self.data[CONF_POWER_SENSOR]],
                    self._power_changed,
                )
            )
        self._create_task(self._async_finish_startup())
        self._notify_update()

    async def async_shutdown(self) -> None:
        """Stop callbacks, cancel timers and persist final state."""
        self.available = False
        self._notify_update()
        if self._power_debounce_cancel:
            self._power_debounce_cancel()
            self._power_debounce_cancel = None
        if self._environment_evaluation_cancel:
            self._environment_evaluation_cancel()
            self._environment_evaluation_cancel = None
        if self._power_unavailable_cancel:
            self._power_unavailable_cancel()
            self._power_unavailable_cancel = None
        for remove in self._listeners:
            remove()
        self._listeners.clear()
        for task in list(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        await self._save()

    def async_add_update_listener(self, update_callback: Callable[[], None]) -> Callable[[], None]:
        """Register an entity update callback."""
        self._update_callbacks.append(update_callback)

        @callback
        def remove() -> None:
            if update_callback in self._update_callbacks:
                self._update_callbacks.remove(update_callback)

        return remove

    def _notify_update(self) -> None:
        for update_callback in list(self._update_callbacks):
            update_callback()

    def _create_task(self, coroutine) -> asyncio.Task:
        task = self.hass.async_create_task(coroutine)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def _save(self) -> None:
        await self.store.async_save(self.state.to_dict())

    def _settings_mode(self) -> str:
        if self.state.hvac_mode in {MODE_COOL, MODE_HEAT}:
            return self.state.hvac_mode
        return self.state.last_thermal_mode

    def _preset_settings_mode(self) -> str:
        """Return Dry while active, otherwise the selected thermal mode."""
        if self.state.hvac_mode == MODE_DRY and MODE_DRY in self.state.modes:
            return MODE_DRY
        return self._settings_mode()

    def _states_for(self, entities: list[str]) -> list[object]:
        return [
            state.state if (state := self.hass.states.get(entity_id)) else None
            for entity_id in entities
        ]

    def _read_environment(self) -> None:
        temp_entities = self.data[CONF_TEMPERATURE_SENSORS]
        humidity_entities = self.data.get(CONF_HUMIDITY_SENSORS, [])
        pressure_entities = self.data.get(CONF_PRESSURE_SENSORS, [])

        temp, temp_valid, temp_invalid = valid_average(
            self._states_for(temp_entities),
            self.option(OPT_TEMP_VALID_MIN),
            self.option(OPT_TEMP_VALID_MAX),
        )
        humidity, humidity_valid, humidity_invalid = valid_average(
            self._states_for(humidity_entities),
            self.option(OPT_HUMIDITY_VALID_MIN),
            self.option(OPT_HUMIDITY_VALID_MAX),
        ) if humidity_entities else (None, 0, 0)
        pressure, pressure_valid, pressure_invalid = valid_average(
            self._states_for(pressure_entities),
            self.option(OPT_PRESSURE_VALID_MIN),
            self.option(OPT_PRESSURE_VALID_MAX),
        ) if pressure_entities else (None, 0, 0)

        self.current_temperature = temp
        self.current_humidity = humidity
        self.current_pressure = pressure
        self.perceived_temperature = (
            perceived_temperature(temp, humidity, pressure) if temp is not None else None
        )
        degraded = temp_valid == 0 or (
            bool(humidity_entities) and humidity_valid == 0
        ) or (bool(pressure_entities) and pressure_valid == 0)
        self.sensor_health = {
            "status": "degraded" if degraded else "ok",
            "temperature_valid": temp_valid,
            "temperature_invalid": temp_invalid,
            "humidity_valid": humidity_valid,
            "humidity_invalid": humidity_invalid,
            "pressure_valid": pressure_valid,
            "pressure_invalid": pressure_invalid,
        }

    @callback
    def _environment_changed(self, event: Event) -> None:
        self._read_environment()
        if self._environment_evaluation_cancel:
            self._environment_evaluation_cancel()
        self._environment_evaluation_cancel = async_call_later(
            self.hass, 0.1, self._async_environment_settled
        )

    async def _async_environment_settled(self, now) -> None:
        """Evaluate once after a group of environment-source updates settles."""
        self._environment_evaluation_cancel = None
        await self.async_evaluate()

    @callback
    def _power_changed(self, event: Event) -> None:
        self._power_feedback_event.set()
        classification = self.power_classification
        if classification == "unknown":
            self.last_error = "power_sensor_degraded"
            self.commands_blocked = True
            if self._initialized and not self._power_unavailable_cancel:
                self._power_unavailable_cancel = async_call_later(
                    self.hass,
                    float(self.option(OPT_POWER_UNAVAILABLE_GRACE)),
                    self._async_power_unavailable,
                )
            self._notify_update()
            return
        if self._power_unavailable_cancel:
            self._power_unavailable_cancel()
            self._power_unavailable_cancel = None
        was_unavailable = not self.available
        was_blocked = self.commands_blocked
        self.available = self._initialized
        self.commands_blocked = not self._initialized
        self.last_error = None
        recovered_from_feedback_loss = self._initialized and (
            was_unavailable or was_blocked
        )
        if recovered_from_feedback_loss:
            self._create_task(
                self._async_recover_after_feedback_return(
                    was_unavailable and self._power_outage_notified
                )
            )
        if classification == self._last_power_classification:
            return
        self._last_power_classification = classification
        if self._command_pending:
            return
        if recovered_from_feedback_loss:
            return
        if self._power_debounce_cancel:
            self._power_debounce_cancel()
        self._power_debounce_cancel = async_call_later(
            self.hass,
            float(self.option(OPT_POWER_STABILIZATION)),
            self._async_reconcile_manual_power,
        )

    async def _async_finish_startup(self) -> None:
        await asyncio.sleep(float(self.option(OPT_STARTUP_DELAY)))
        self._initialized = True
        self.available = True
        self.commands_blocked = False
        if (
            self.strategy == STRATEGY_DISCRETE
            and not self.has_power_feedback
            and self.state.physical_on
            and self.state.hvac_mode != MODE_OFF
        ):
            saved_mode = self.state.physical_mode or self._settings_mode()
            await self._async_discrete_command(saved_mode, False, force=True)
            await asyncio.sleep(float(self.option(OPT_RESTORE_OFF_ON_DELAY)))
        elif self.has_power_feedback:
            if self.power_classification == "unknown":
                self.commands_blocked = True
                self.last_error = "power_sensor_degraded"
                self._power_unavailable_cancel = async_call_later(
                    self.hass,
                    float(self.option(OPT_POWER_UNAVAILABLE_GRACE)),
                    self._async_power_unavailable,
                )
                self._notify_update()
                return
            await self._async_adopt_power_at_startup()
            await self._async_reconcile_after_power_return()
        await self.async_evaluate()

    async def _async_adopt_power_at_startup(self) -> None:
        classification = self.power_classification
        if classification in {"starting", "on"}:
            self.state.physical_on = True
            if self.state.hvac_mode in self.state.modes:
                self.state.physical_mode = self.state.hvac_mode
                self.last_command_result = "adopted_from_power"
            else:
                inferred = self._infer_manual_mode()
                if inferred:
                    self.state.hvac_mode = inferred
                    self.state.last_thermal_mode = inferred
                    self.state.physical_mode = inferred
                    self.last_command_result = f"startup_manual_{inferred}"
                else:
                    self.state.physical_mode = None
                    self.manual_mode_unknown = True
                    self.hvac_action = "unknown"
                    self.last_command_result = "startup_manual_mode_unknown"
        elif classification == "off":
            self.state.physical_on = False
            self.state.physical_mode = None
        await self._save()

    @property
    def power(self) -> float | None:
        if not self.has_power_feedback:
            return None
        state = self.hass.states.get(self.data[CONF_POWER_SENSOR])
        try:
            return float(state.state) if state else None
        except (TypeError, ValueError):
            return None

    @property
    def power_classification(self) -> str:
        return classify_power(
            self.power,
            float(self.option(OPT_POWER_OFF_BELOW)),
            float(self.option(OPT_POWER_ON_ABOVE)),
        )

    async def async_set_hvac_mode(self, mode: str) -> None:
        """Select a logical mode, stopping the previous physical mode first."""
        if self.commands_blocked:
            self.last_command_result = "discarded_while_initializing"
            self._notify_update()
            return
        if mode not in self.supported_modes:
            raise ValueError(f"Unsupported HVAC mode: {mode}")
        previous_mode = self.state.hvac_mode
        if previous_mode == mode and not (
            mode == MODE_OFF and self.state.physical_on
        ):
            return
        physical_was_on = self.state.physical_on
        self.state.hvac_mode = mode
        self.manual_mode_unknown = False
        if mode in self.state.modes:
            self.state.last_thermal_mode = mode
        self.hvac_action = "off" if mode == MODE_OFF else "idle"
        await self._save()
        self._notify_update()
        if physical_was_on:
            # Explicit mode changes, especially user OFF, bypass the automatic
            # dry command interval and stop the active hardware immediately.
            await self._async_set_physical(False)
        await self.async_evaluate()

    async def async_turn_on(self) -> None:
        """Restore the last thermal mode without forcing physical demand."""
        await self.async_set_hvac_mode(self.state.last_thermal_mode)

    async def async_set_temperature(self, temperature: float) -> None:
        """Set a manual target for the active or last thermal mode."""
        if self.commands_blocked:
            self.last_command_result = "discarded_while_initializing"
            self._notify_update()
            return
        mode = self._settings_mode()
        target = max(
            float(self.option("minimum_temperature")),
            min(float(self.option("maximum_temperature")), float(temperature)),
        )
        self.state.modes[mode].target = target
        self.state.modes[mode].preset = PRESET_NONE
        await self._save()
        self._notify_update()
        await self.async_evaluate()

    async def async_set_humidity(self, humidity: float) -> None:
        """Set a manual Dry target, persisted internally as dew point."""
        if self.commands_blocked:
            self.last_command_result = "discarded_while_initializing"
            self._notify_update()
            return
        if not self.data.get(CONF_ENABLE_DRY) or MODE_DRY not in self.state.modes:
            raise ValueError("Dry mode is not enabled")
        if self.current_temperature is None:
            self.last_command_result = "humidity_target_rejected_no_temperature"
            self._notify_update()
            return
        target_humidity = min(
            float(self.option(OPT_MAX_HUMIDITY)),
            max(float(self.option(OPT_MIN_HUMIDITY)), float(humidity)),
        )
        target_dew_point = dew_point_celsius(
            self.current_temperature, target_humidity
        )
        if target_dew_point is None:
            raise ValueError("Invalid humidity target")
        self.state.modes[MODE_DRY].target = target_dew_point
        self.state.modes[MODE_DRY].preset = PRESET_NONE
        await self._save()
        self._notify_update()
        if self.state.hvac_mode == MODE_DRY:
            await self.async_evaluate()

    async def async_set_preset(self, preset: str) -> None:
        """Apply one standard preset to the active or last thermal mode."""
        if self.commands_blocked:
            self.last_command_result = "discarded_while_initializing"
            self._notify_update()
            return
        if preset == PRESET_NONE:
            mode = self._preset_settings_mode()
            self.state.modes[mode].preset = PRESET_NONE
            await self._save()
            self._notify_update()
            await self.async_evaluate()
            return
        if preset not in PRESETS:
            raise ValueError(f"Unsupported preset: {preset}")
        mode = self._preset_settings_mode()
        self.state.modes[mode].target = self.preset_values(preset, mode)
        self.state.modes[mode].preset = preset
        await self._save()
        self._notify_update()
        await self.async_evaluate()

    async def async_evaluate(self) -> None:
        """Evaluate current readings and apply one normalized decision."""
        async with self._evaluation_lock:
            await self._async_evaluate_locked()

    async def _async_evaluate_locked(self) -> None:
        """Evaluate one aggregated input while excluding overlapping decisions."""
        if self.commands_blocked:
            self._set_passive_action()
            self._notify_update()
            return
        mode = self.state.hvac_mode
        if mode == MODE_OFF:
            if self.state.physical_on and not self.manual_mode_unknown:
                await self._async_set_physical(False)
            self.hvac_action = "off" if not self.manual_mode_unknown else "unknown"
            self._notify_update()
            return
        if mode == MODE_DRY:
            target_dew_point = self.effective_dry_target_dew_point
            decision = dry_decision(
                self.current_temperature,
                self.current_humidity,
                self.state.physical_on,
                target_dew_point,
                float(self.option(OPT_DRY_DEW_POINT_HYSTERESIS)),
                self._minimum_dry_interval_elapsed(),
            )
        else:
            decision = thermal_decision(
                mode,
                self.perceived_temperature,
                self.state.modes[mode].target,
                float(self.option(OPT_HYSTERESIS)),
                self.state.physical_on,
            )
        self.hvac_action = decision.action
        if decision.command == "on":
            await self._async_set_physical(True)
        elif decision.command == "off":
            await self._async_set_physical(False)
        self._notify_update()

    def _set_passive_action(self) -> None:
        if self.state.hvac_mode == MODE_OFF:
            self.hvac_action = "off"
        elif self.state.physical_on:
            self.hvac_action = {
                MODE_COOL: "cooling",
                MODE_HEAT: "heating",
                MODE_DRY: "drying",
            }.get(self.state.hvac_mode, "unknown")
        else:
            self.hvac_action = "idle"

    def _minimum_dry_interval_elapsed(self) -> bool:
        if not self.state.last_command_at:
            return True
        try:
            previous = datetime.fromisoformat(self.state.last_command_at)
        except ValueError:
            return True
        elapsed = (dt_util.utcnow() - previous).total_seconds()
        return elapsed >= float(self.option(OPT_DRY_MIN_INTERVAL))

    async def _async_set_physical(self, turn_on: bool) -> bool:
        if self.commands_blocked:
            return False
        async with self._command_lock:
            mode = self.state.hvac_mode if turn_on else (
                self.state.physical_mode or self._settings_mode()
            )
            had_pending_confirmation = bool(
                self._confirmation_task and not self._confirmation_task.done()
            )
            self._cancel_pending_confirmation()
            generation = self._confirmation_generation

            if (
                self.has_power_feedback
                and not had_pending_confirmation
                and self._toggle_target_reached(turn_on)
            ):
                self.state.physical_on = turn_on
                self.state.physical_mode = mode if turn_on else None
                self.last_command_result = "already_confirmed"
                self.last_error = None
                await self._save()
                self._notify_update()
                return True

            await self._async_issue_physical_command(mode, turn_on)
            self.state.physical_on = turn_on
            self.state.physical_mode = mode if turn_on else None
            self.state.last_command_at = dt_util.utcnow().isoformat()
            self.last_error = None

            if not self.has_power_feedback:
                self.last_command_result = "on" if turn_on else "off"
                await self._save()
                self._notify_update()
                return True

            self._command_pending = True
            self.last_command_result = (
                "on_sent_waiting_feedback"
                if turn_on
                else "off_sent_waiting_feedback"
            )
            await self._save()
            self._notify_update()
            self._confirmation_task = self._create_task(
                self._async_confirm_physical_state(mode, turn_on, generation)
            )
            return True

    def _cancel_pending_confirmation(self) -> None:
        """Cancel an obsolete feedback wait before issuing a newer command."""
        self._confirmation_generation += 1
        if self._confirmation_task and not self._confirmation_task.done():
            self._confirmation_task.cancel()
        self._confirmation_task = None
        self._command_pending = False

    async def _async_issue_physical_command(
        self, mode: str, turn_on: bool
    ) -> None:
        """Issue one hardware command immediately without waiting for feedback."""
        if self.strategy == STRATEGY_DISCRETE:
            await self._async_discrete_command(mode, turn_on)
            return
        await self._async_toggle_pulse()

    def _discrete_entity(self, mode: str) -> str:
        mapping = {
            MODE_COOL: CONF_COOL_COMMAND,
            MODE_HEAT: CONF_HEAT_COMMAND,
            MODE_DRY: CONF_DRY_COMMAND,
        }
        key = mapping.get(mode)
        if not key or key not in self.data:
            raise ValueError(f"No discrete command configured for mode: {mode}")
        return self.data[key]

    async def _async_discrete_command(
        self, mode: str, turn_on: bool, *, force: bool = False
    ) -> bool:
        entity_id = self._discrete_entity(mode)
        service = "turn_on" if turn_on else "turn_off"
        await self.hass.services.async_call(
            "switch", service, {"entity_id": entity_id}, blocking=True
        )
        if force:
            self.state.physical_on = turn_on
            self.state.physical_mode = mode if turn_on else None
            self.state.last_command_at = dt_util.utcnow().isoformat()
            self.last_command_result = f"startup_{service}"
            await self._save()
        return True

    async def _async_toggle_pulse(self) -> None:
        await self.hass.services.async_call(
            "switch",
            "turn_on",
            {"entity_id": self.data[CONF_TOGGLE_COMMAND]},
            blocking=True,
        )
        try:
            await asyncio.sleep(float(self.option(OPT_TOGGLE_PULSE)))
        finally:
            await asyncio.shield(
                self.hass.services.async_call(
                    "switch",
                    "turn_off",
                    {"entity_id": self.data[CONF_TOGGLE_COMMAND]},
                    blocking=True,
                )
            )

    async def _async_wait_for_power_target(
        self, turn_on: bool, timeout: float
    ) -> bool:
        """Wake on power updates and use timeout only as the upper bound."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while not self._toggle_target_reached(turn_on):
            remaining = deadline - loop.time()
            if remaining <= 0:
                return False
            self._power_feedback_event.clear()
            if self._toggle_target_reached(turn_on):
                return True
            try:
                await asyncio.wait_for(
                    self._power_feedback_event.wait(), timeout=remaining
                )
            except TimeoutError:
                return self._toggle_target_reached(turn_on)
        return True

    async def _async_confirm_physical_state(
        self, mode: str, turn_on: bool, generation: int
    ) -> bool:
        """Confirm in the background and recover without blocking HA services."""
        attempts = int(self.option(OPT_MAX_ATTEMPTS))
        timeout = float(self.option(OPT_FEEDBACK_TIMEOUT))
        try:
            for attempt in range(1, attempts + 1):
                if await self._async_wait_for_power_target(turn_on, timeout):
                    if generation != self._confirmation_generation:
                        return False
                    self.state.physical_on = turn_on
                    self.state.physical_mode = mode if turn_on else None
                    self.last_command_result = f"confirmed_attempt_{attempt}"
                    self.last_error = None
                    await self._save()
                    self._notify_update()
                    return True
                if attempt >= attempts or generation != self._confirmation_generation:
                    break
                async with self._command_lock:
                    await self._async_issue_physical_command(mode, not turn_on)
                await self._async_wait_for_power_target(not turn_on, timeout)
                if generation != self._confirmation_generation:
                    return False
                async with self._command_lock:
                    await self._async_issue_physical_command(mode, turn_on)

            if generation == self._confirmation_generation:
                observed_on = self.power_classification in {"starting", "on"}
                self.state.physical_on = observed_on
                self.state.physical_mode = mode if observed_on else None
                self.last_command_result = "failed"
                self.last_error = "power_feedback_not_reached"
                await self._save()
                await self._async_notify_failure(turn_on, attempts)
                self._notify_update()
            return False
        except asyncio.CancelledError:
            return False
        finally:
            if generation == self._confirmation_generation:
                self._command_pending = False
                self._confirmation_task = None
                self._notify_update()

    def _toggle_target_reached(self, turn_on: bool) -> bool:
        return power_target_reached(self.power_classification, turn_on)

    async def _async_notify_failure(self, turn_on: bool, attempts: int) -> None:
        configured = str(self.option(OPT_NOTIFICATION_SERVICE)).strip()
        if not configured or "." not in configured:
            return
        domain, service = configured.split(".", 1)
        await self.hass.services.async_call(
            domain,
            service,
            {
                "title": "ThermoPilot command failed",
                "message": (
                    f"{self.entry.title}: {'ON' if turn_on else 'OFF'} was not "
                    f"confirmed after {attempts} attempts."
                ),
            },
            blocking=False,
        )

    async def _async_power_unavailable(self, now) -> None:
        self._power_unavailable_cancel = None
        if self.power_classification != "unknown":
            return
        self.available = False
        self.commands_blocked = True
        self.last_error = "power_sensor_unavailable"
        self.last_command_result = "feedback_unavailable"
        configured = str(self.option(OPT_NOTIFICATION_SERVICE)).strip()
        if configured and "." in configured and not self._power_outage_notified:
            domain, service = configured.split(".", 1)
            await self.hass.services.async_call(
                domain,
                service,
                {
                    "title": "⚠️ ThermoPilot unavailable",
                    "message": (
                        f"{self.entry.title}: the dedicated power sensor has been "
                        "unavailable for more than 3 minutes. Hardware commands are blocked."
                    ),
                },
                blocking=False,
            )
            self._power_outage_notified = True
        self._notify_update()

    async def _async_notify_power_restored(
        self, reconciliation_succeeded: bool
    ) -> None:
        configured = str(self.option(OPT_NOTIFICATION_SERVICE)).strip()
        if configured and "." in configured and self._power_outage_notified:
            domain, service = configured.split(".", 1)
            title = (
                "✅ ThermoPilot restored"
                if reconciliation_succeeded
                else "❌ ThermoPilot recovery failed"
            )
            message = (
                f"{self.entry.title}: the dedicated power sensor is available "
                "again. ThermoPilot is online and physical state reconciliation "
                "completed successfully."
                if reconciliation_succeeded
                else (
                    f"{self.entry.title}: power feedback is available again, but "
                    "the requested physical state could not be restored after 3 "
                    "recovery cycles."
                )
            )
            await self.hass.services.async_call(
                domain,
                service,
                {
                    "title": title,
                    "message": message,
                },
                blocking=False,
            )
        self._power_outage_notified = False

    async def _async_recover_after_feedback_return(
        self, notification_required: bool
    ) -> None:
        """Reconcile first, then report the actual recovery outcome."""
        reconciliation_succeeded = await self._async_reconcile_after_power_return()
        if notification_required:
            await self._async_notify_power_restored(reconciliation_succeeded)

    async def _async_reconcile_after_power_return(self) -> bool:
        if not self._initialized or self.power_classification == "unknown":
            return False
        physical_on = self.power_classification in {"starting", "on"}
        self.state.physical_on = physical_on
        self.state.physical_mode = self._settings_mode() if physical_on else None
        await self._save()
        await self.async_evaluate()
        confirmation_task = self._confirmation_task
        if confirmation_task:
            return await confirmation_task
        return self.last_error is None and self.power_classification != "unknown"

    async def _async_reconcile_manual_power(self, now) -> None:
        self._power_debounce_cancel = None
        if self._command_pending or self.commands_blocked:
            return
        classification = self.power_classification
        observed_on = classification in {"starting", "on"}
        if observed_on == self.state.physical_on or classification == "unknown":
            return
        if not observed_on:
            self.state.physical_on = False
            self.state.physical_mode = None
            self.state.hvac_mode = MODE_OFF
            self.hvac_action = "off"
            self.last_command_result = "manual_off_detected"
            await self._save()
            self._notify_update()
            return

        inferred = self._infer_manual_mode()
        self.state.physical_on = True
        if inferred:
            self.state.hvac_mode = inferred
            self.state.last_thermal_mode = inferred
            self.state.physical_mode = inferred
            self.hvac_action = "cooling" if inferred == MODE_COOL else "heating"
            self.manual_mode_unknown = False
            self.last_command_result = f"manual_{inferred}_detected"
        else:
            self.state.physical_mode = None
            self.state.hvac_mode = MODE_OFF
            self.hvac_action = "unknown"
            self.manual_mode_unknown = True
            self.last_command_result = "manual_mode_unknown"
        await self._save()
        self._notify_update()

    def _infer_manual_mode(self) -> str | None:
        current = self.perceived_temperature
        hysteresis = float(self.option(OPT_HYSTERESIS))
        if current is None:
            return None
        if MODE_COOL in self.state.modes:
            if current > self.state.modes[MODE_COOL].target + hysteresis:
                return MODE_COOL
        if MODE_HEAT in self.state.modes:
            if current < self.state.modes[MODE_HEAT].target - hysteresis:
                return MODE_HEAT
        return None

    @property
    def diagnostic_attributes(self) -> dict[str, Any]:
        """Return non-sensitive runtime diagnostics."""
        return {
            "integration_version": INTEGRATION_VERSION,
            "configuration_version": self.entry.version,
            "strategy": self.strategy,
            "started_at": self.started_at,
            "commands_blocked": self.commands_blocked,
            "sensor_health": self.sensor_health,
            "dew_point": self.current_dew_point,
            "target_humidity": self.target_humidity,
            "target_dew_point": self.effective_dry_target_dew_point,
            "last_command_result": self.last_command_result,
            "last_command_at": self.state.last_command_at,
            "last_error": self.last_error,
            "physical_state": "on" if self.state.physical_on else "off",
            "state_quality": "confirmed" if self.has_power_feedback else "estimated",
        }

    @property
    def diagnostic_status(self) -> str:
        """Return prioritized user-facing controller health."""
        if not self._initialized:
            return "initializing"
        if self.last_error == "power_sensor_degraded":
            return "degraded"
        if self.last_error:
            return "error"
        if self.sensor_health.get("status") == "degraded":
            return "degraded"
        return "online"
