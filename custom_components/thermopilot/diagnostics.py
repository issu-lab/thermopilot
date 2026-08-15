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
        },
        "thermostat": {
            "hvac_mode": controller.state.hvac_mode,
            "hvac_action": controller.hvac_action,
            "target_temperature": controller.target_temperature,
            "preset": controller.preset,
        },
    }
