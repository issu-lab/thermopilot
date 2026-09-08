"""Pure models and decisions used by ThermoPilot."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import exp, isfinite, log
from typing import Iterable

from .const import MODE_COOL, MODE_HEAT, MODE_OFF, PRESET_HOME, PRESET_NONE

INVALID_STATES = {None, "", "unknown", "unavailable"}


def valid_average(
    values: Iterable[object], minimum: float, maximum: float
) -> tuple[float | None, int, int]:
    """Average valid finite readings and return valid/invalid counts."""
    valid: list[float] = []
    invalid = 0
    for value in values:
        if value in INVALID_STATES:
            invalid += 1
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            invalid += 1
            continue
        if isfinite(number) and minimum <= number <= maximum:
            valid.append(number)
        else:
            invalid += 1
    average = sum(valid) / len(valid) if valid else None
    return average, len(valid), invalid


def perceived_temperature(
    temperature: float,
    humidity: float | None = None,
    pressure: float | None = None,
) -> float:
    """Calculate perceived temperature using the existing Steadman behavior."""
    pressure_delta = 0.0 if pressure is None else (1013.25 - pressure) * 0.005
    if humidity is None or temperature < 27 or humidity < 40:
        return round(temperature + pressure_delta, 1)

    c1, c2, c3 = -8.78469475556, 1.61139411, 2.33854883889
    c4, c5, c6 = -0.14611605, -0.012308094, -0.0164248277778
    c7, c8, c9 = 0.002211732, 0.00072546, -0.000003582
    heat_index = (
        c1
        + c2 * temperature
        + c3 * humidity
        + c4 * temperature * humidity
        + c5 * temperature**2
        + c6 * humidity**2
        + c7 * temperature**2 * humidity
        + c8 * temperature * humidity**2
        + c9 * temperature**2 * humidity**2
    )
    return round(heat_index + pressure_delta, 1)


def dew_point_celsius(
    temperature: float | None, humidity: float | None
) -> float | None:
    """Return dew point from air temperature and relative humidity."""
    if temperature is None or humidity is None:
        return None
    try:
        temp = float(temperature)
        relative_humidity = float(humidity)
    except (TypeError, ValueError):
        return None
    if not isfinite(temp) or not isfinite(relative_humidity):
        return None
    if relative_humidity <= 0 or relative_humidity > 100:
        return None
    a, b = 17.62, 243.12
    gamma = log(relative_humidity / 100.0) + (a * temp) / (b + temp)
    return round((b * gamma) / (a - gamma), 2)


def relative_humidity_for_dew_point(
    temperature: float | None, dew_point: float | None
) -> float | None:
    """Return relative humidity represented by one dew point at a temperature."""
    if temperature is None or dew_point is None:
        return None
    try:
        temp = float(temperature)
        target = float(dew_point)
    except (TypeError, ValueError):
        return None
    if not isfinite(temp) or not isfinite(target):
        return None
    a, b = 17.62, 243.12
    humidity = 100.0 * exp(
        (a * target) / (b + target) - (a * temp) / (b + temp)
    )
    return round(min(100.0, max(0.0, humidity)), 1)


def bounded_dew_point(
    temperature: float | None,
    target_dew_point: float | None,
    minimum_humidity: float,
    maximum_humidity: float,
) -> float | None:
    """Clamp a dew-point target to the configured relative-humidity band."""
    equivalent = relative_humidity_for_dew_point(temperature, target_dew_point)
    if equivalent is None:
        return None
    bounded_humidity = min(maximum_humidity, max(minimum_humidity, equivalent))
    return dew_point_celsius(temperature, bounded_humidity)


def classify_power(power: object, off_below: float, on_above: float) -> str:
    """Classify dedicated power feedback as off, starting, on or unknown."""
    try:
        value = float(power)
    except (TypeError, ValueError):
        return "unknown"
    if not isfinite(value) or value < 0:
        return "unknown"
    if value < off_below:
        return "off"
    if value <= on_above:
        return "starting"
    return "on"


def power_target_reached(classification: str, turn_on: bool) -> bool:
    """Return whether measured power confirms the requested physical state."""
    if turn_on:
        return classification in {"starting", "on"}
    return classification == "off"


@dataclass
class ModeState:
    """Persisted settings for one thermal mode."""

    target: float
    preset: str = PRESET_HOME


@dataclass
class PersistedState:
    """State that must survive Home Assistant restarts."""

    schema_version: int = 1
    hvac_mode: str = MODE_OFF
    last_thermal_mode: str = MODE_COOL
    modes: dict[str, ModeState] = field(default_factory=dict)
    physical_on: bool = False
    physical_mode: str | None = None
    last_command_at: str | None = None

    def to_dict(self) -> dict:
        """Serialize the persisted model."""
        data = asdict(self)
        return data

    @classmethod
    def from_dict(
        cls, data: dict, default_modes: dict[str, ModeState], fallback_mode: str
    ) -> "PersistedState":
        """Load a compatible state while retaining newly introduced defaults."""
        modes = {
            mode: ModeState(state.target, state.preset)
            for mode, state in default_modes.items()
        }
        for mode, raw in data.get("modes", {}).items():
            if mode in modes and isinstance(raw, dict):
                try:
                    modes[mode] = ModeState(
                        target=float(raw.get("target", modes[mode].target)),
                        preset=str(raw.get("preset", PRESET_NONE)),
                    )
                except (TypeError, ValueError):
                    continue
        hvac_mode = str(data.get("hvac_mode", MODE_OFF))
        if hvac_mode not in {MODE_OFF, *modes}:
            hvac_mode = MODE_OFF
        last_mode = str(data.get("last_thermal_mode", fallback_mode))
        if last_mode not in {MODE_COOL, MODE_HEAT} or last_mode not in modes:
            last_mode = fallback_mode
        return cls(
            schema_version=1,
            hvac_mode=hvac_mode,
            last_thermal_mode=last_mode,
            modes=modes,
            physical_on=bool(data.get("physical_on", False)),
            physical_mode=data.get("physical_mode"),
            last_command_at=data.get("last_command_at"),
        )


@dataclass(frozen=True)
class Decision:
    """Normalized thermostat output decision."""

    action: str
    command: str | None = None


def thermal_decision(
    mode: str,
    current: float | None,
    target: float,
    hysteresis: float,
    physical_on: bool,
) -> Decision:
    """Apply shared cool and heat hysteresis."""
    if current is None:
        return Decision("unknown")
    if mode == MODE_COOL:
        if not physical_on and current > target + hysteresis:
            return Decision("cooling", "on")
        if physical_on and current <= target - hysteresis:
            return Decision("idle", "off")
        return Decision("cooling" if physical_on else "idle")
    if mode == MODE_HEAT:
        if not physical_on and current < target - hysteresis:
            return Decision("heating", "on")
        if physical_on and current >= target + hysteresis:
            return Decision("idle", "off")
        return Decision("heating" if physical_on else "idle")
    raise ValueError(f"Unsupported thermal mode: {mode}")


def dry_decision(
    temperature: float | None,
    humidity: float | None,
    physical_on: bool,
    target_dew_point: float | None,
    dew_point_hysteresis: float,
    interval_elapsed: bool,
) -> Decision:
    """Control dry mode by moisture content instead of raw relative humidity."""
    current_dew_point = dew_point_celsius(temperature, humidity)
    if current_dew_point is None or target_dew_point is None:
        return Decision("unknown")
    if not interval_elapsed:
        return Decision("drying" if physical_on else "idle")
    if not physical_on and current_dew_point > target_dew_point + dew_point_hysteresis:
        return Decision("drying", "on")
    if physical_on and current_dew_point <= target_dew_point:
        return Decision("idle", "off")
    return Decision("drying" if physical_on else "idle")
