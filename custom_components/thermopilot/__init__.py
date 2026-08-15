"""ThermoPilot native Home Assistant integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, PLATFORMS
from .controller import ThermoPilotController


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ThermoPilot from a config entry."""
    controller = ThermoPilotController(hass, entry)
    await controller.async_initialize()
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = controller
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a ThermoPilot config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        controller: ThermoPilotController = hass.data[DOMAIN].pop(entry.entry_id)
        await controller.async_shutdown()
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)
    return unloaded


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload ThermoPilot after options change."""
    await hass.config_entries.async_reload(entry.entry_id)
