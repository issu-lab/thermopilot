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
    OPT_DRY_OFF,
    OPT_DRY_ON,
    OPT_FEEDBACK_TIMEOUT,
    OPT_HUMIDITY_VALID_MAX,
    OPT_HUMIDITY_VALID_MIN,
    OPT_HYSTERESIS,
    OPT_MAX_ATTEMPTS,
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
    classify_power,
    dry_decision,
    perceived_temperature,
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
        self._command_pending = False
        self._power_debounce_cancel: Callable[[], None] | None = None
        self._last_power_classification = "unknown"
        self._initialized = False
        self._power_unavailable_cancel: Callable[[], None] | None = None
        self._power_outage_notified = False

    def option(self, key: str):
        """Return a configured advanced option or its default."""
        return self.entry.options.get(key, DEFAULTS[key])

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
        mode = self._settings_mode()
        return self.state.modes[mode].target if mode in self.state.modes else None

    @property
    def preset(self) -> str:
        """Return preset for the active or last selected thermal mode."""
        mode = self._settings_mode()
        return self.state.modes[mode].preset if mode in self.state.modes else PRESET_NONE

    def preset_values(self, preset: str, mode: str) -> float:
        """Return one editable standard preset value."""
        return float(self.option(f"preset_{preset}_{mode}"))

    def _default_mode_states(self) -> tuple[dict[str, ModeState], str]:
        modes: dict[str, ModeState] = {}
        for mode in self.data[CONF_MODES]:
            modes[mode] = ModeState(self.preset_values(PRESET_HOME, mode), PRESET_HOME)
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
        if self.state.hvac_mode in self.state.modes:
            return self.state.hvac_mode
        return self.state.last_thermal_mode

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
        self._create_task(self.async_evaluate())

    @callback
    def _power_changed(self, event: Event) -> None:
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
        self.available = self._initialized
        self.commands_blocked = not self._initialized
        self.last_error = None
        if was_unavailable and self._power_outage_notified:
            self._create_task(self._async_notify_power_restored())
        if self._initialized:
            self._create_task(self._async_reconcile_after_power_return())
        if classification == self._last_power_classification:
            return
        self._last_power_classification = classification
        if self._command_pending:
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
            await self._async_discrete_command(saved_mode, True, force=True)
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
        if mode not in self.supported_modes:
            raise ValueError(f"Unsupported HVAC mode: {mode}")
        previous_mode = self.state.hvac_mode
        if previous_mode == mode and not (
            mode == MODE_OFF and self.state.physical_on
        ):
            return
        if self.state.physical_on:
            await self._async_set_physical(False)
        self.state.hvac_mode = mode
        self.manual_mode_unknown = False
        if mode in self.state.modes:
            self.state.last_thermal_mode = mode
        self.hvac_action = "off" if mode == MODE_OFF else "idle"
        await self._save()
        if mode != MODE_OFF and not self.state.physical_on:
            await self._async_set_physical(True)
            self.hvac_action = "idle"
            self._notify_update()
            return
        await self.async_evaluate()

    async def async_set_temperature(self, temperature: float) -> None:
        """Set a manual target for the active or last thermal mode."""
        mode = self._settings_mode()
        target = max(
            float(self.option("minimum_temperature")),
            min(float(self.option("maximum_temperature")), float(temperature)),
        )
        self.state.modes[mode].target = target
        self.state.modes[mode].preset = PRESET_NONE
        await self._save()
        await self.async_evaluate()

    async def async_set_preset(self, preset: str) -> None:
        """Apply one standard preset to the active or last thermal mode."""
        if preset not in PRESETS:
            raise ValueError(f"Unsupported preset: {preset}")
        mode = self._settings_mode()
        self.state.modes[mode].target = self.preset_values(preset, mode)
        self.state.modes[mode].preset = preset
        await self._save()
        await self.async_evaluate()

    async def async_evaluate(self) -> None:
        """Evaluate current readings and apply one normalized decision."""
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
            decision = dry_decision(
                self.current_humidity,
                self.state.physical_on,
                float(self.option(OPT_DRY_ON)),
                float(self.option(OPT_DRY_OFF)),
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
            self._command_pending = True
            try:
                mode = self.state.hvac_mode if turn_on else (
                    self.state.physical_mode or self._settings_mode()
                )
                if self.strategy == STRATEGY_DISCRETE:
                    success = (
                        await self._async_confirmed_discrete_command(mode, turn_on)
                        if self.has_power_feedback
                        else await self._async_discrete_command(mode, turn_on)
                    )
                else:
                    success = await self._async_toggle_command(turn_on)
                if success:
                    self.state.physical_on = turn_on
                    self.state.physical_mode = mode if turn_on else None
                    self.state.last_command_at = dt_util.utcnow().isoformat()
                    self.last_command_result = "on" if turn_on else "off"
                    self.last_error = None
                    await self._save()
                return success
            finally:
                self._command_pending = False
                self._notify_update()

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

    async def _async_confirmed_discrete_command(
        self, mode: str, turn_on: bool
    ) -> bool:
        """Send explicit commands and recover by alternating the physical state."""
        attempts = int(self.option(OPT_MAX_ATTEMPTS))
        for attempt in range(1, attempts + 1):
            await self._async_discrete_command(mode, turn_on)
            await asyncio.sleep(float(self.option(OPT_FEEDBACK_TIMEOUT)))
            if self._toggle_target_reached(turn_on):
                self.last_command_result = f"confirmed_attempt_{attempt}"
                return True
            await self._async_discrete_command(mode, not turn_on)
            await asyncio.sleep(float(self.option(OPT_FEEDBACK_TIMEOUT)))
        self.last_command_result = "failed"
        self.last_error = "power_feedback_not_reached"
        await self._async_notify_failure(turn_on, attempts)
        return False

    async def _async_toggle_command(self, turn_on: bool) -> bool:
        attempts = int(self.option(OPT_MAX_ATTEMPTS))
        for attempt in range(1, attempts + 1):
            if self._toggle_target_reached(turn_on):
                return True
            await self.hass.services.async_call(
                "switch",
                "turn_on",
                {"entity_id": self.data[CONF_TOGGLE_COMMAND]},
                blocking=True,
            )
            await asyncio.sleep(float(self.option(OPT_TOGGLE_PULSE)))
            await self.hass.services.async_call(
                "switch",
                "turn_off",
                {"entity_id": self.data[CONF_TOGGLE_COMMAND]},
                blocking=True,
            )
            await asyncio.sleep(float(self.option(OPT_FEEDBACK_TIMEOUT)))
            if self._toggle_target_reached(turn_on):
                self.last_command_result = f"confirmed_attempt_{attempt}"
                return True
        self.last_command_result = "failed"
        self.last_error = "power_feedback_not_reached"
        await self._async_notify_failure(turn_on, attempts)
        return False

    def _toggle_target_reached(self, turn_on: bool) -> bool:
        power = self.power
        if power is None:
            return False
        if turn_on:
            return power >= float(self.option(OPT_POWER_OFF_BELOW))
        return power < float(self.option(OPT_POWER_ON_ABOVE))

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

    async def _async_notify_power_restored(self) -> None:
        configured = str(self.option(OPT_NOTIFICATION_SERVICE)).strip()
        if configured and "." in configured and self._power_outage_notified:
            domain, service = configured.split(".", 1)
            await self.hass.services.async_call(
                domain,
                service,
                {
                    "title": "✅ ThermoPilot restored",
                    "message": (
                        f"{self.entry.title}: the dedicated power sensor is available "
                        "again. ThermoPilot is online and state reconciliation has started."
                    ),
                },
                blocking=False,
            )
        self._power_outage_notified = False

    async def _async_reconcile_after_power_return(self) -> None:
        if not self._initialized or self.power_classification == "unknown":
            return
        requested_on = self.state.hvac_mode != MODE_OFF
        physical_on = self.power_classification in {"starting", "on"}
        self.state.physical_on = physical_on
        if requested_on != physical_on:
            await self._async_set_physical(requested_on)
        else:
            await self._save()
        self._notify_update()

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
            "last_command_result": self.last_command_result,
            "last_command_at": self.state.last_command_at,
            "last_error": self.last_error,
            "physical_state": "on" if self.state.physical_on else "off",
            "state_quality": "confirmed" if self.strategy == STRATEGY_POWER_TOGGLE else "estimated",
        }
