"""Unified status sensor for ThermoPilot."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_DEVICE_ID, DOMAIN
from .controller import ThermoPilotController


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the unified status and diagnostics entity."""
    controller: ThermoPilotController = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ThermoPilotStatusSensor(controller, entry)])


class ThermoPilotSensorBase(SensorEntity):
    _attr_should_poll = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, controller: ThermoPilotController, entry: ConfigEntry) -> None:
        self.controller = controller
        self.entry = entry
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            self.controller.async_add_update_listener(self._controller_updated)
        )

    @callback
    def _controller_updated(self) -> None:
        self.async_write_ha_state()


class ThermoPilotStatusSensor(ThermoPilotSensorBase):
    _attr_has_entity_name = True
    _attr_translation_key = "status"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = [
        "initializing",
        "degraded",
        "error",
        "off",
        "on",
        "starting",
        "stopping",
        "waiting",
        "retrying",
        "unknown",
    ]

    def __init__(self, controller: ThermoPilotController, entry: ConfigEntry) -> None:
        super().__init__(controller, entry)
        self._attr_unique_id = f"{entry.data[CONF_DEVICE_ID]}_diagnostics"

    @property
    def native_value(self) -> str:
        return self.controller.unified_status

    @property
    def extra_state_attributes(self) -> dict:
        return {
            **self.controller.diagnostic_attributes,
            "thermopilot_role": "status",
            "power": self.controller.power,
        }
