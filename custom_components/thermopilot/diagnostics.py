"""Diagnostics support for ThermoPilot."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .controller import ThermoPilotController


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict:
    """Return downloadable non-sensitive diagnostics."""
    controller: ThermoPilotController = hass.data[DOMAIN][entry.entry_id]
    return {
        "entry": {
            "title": entry.title,
            "version": entry.version,
            "strategy": controller.strategy,
            "supported_modes": controller.supported_modes,
        },
        "runtime": controller.diagnostic_attributes,
        "environment": {
            "temperature": controller.current_temperature,
            "humidity": controller.current_humidity,
            "pressure": controller.current_pressure,
            "perceived_temperature": controller.perceived_temperature,
            "dew_point": controller.current_dew_point,
        },
        "thermostat": {
            "hvac_mode": controller.state.hvac_mode,
            "hvac_action": controller.hvac_action,
            "target_temperature": controller.target_temperature,
            "target_humidity": controller.target_humidity,
            "preset": controller.preset,
        },
    }
