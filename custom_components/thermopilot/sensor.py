"""Diagnostic sensors for ThermoPilot."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_DEVICE_ID, DOMAIN, STRATEGY_POWER_TOGGLE
from .controller import ThermoPilotController


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up general and optional power-feedback diagnostics."""
    controller: ThermoPilotController = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = [ThermoPilotDiagnosticSensor(controller, entry)]
    if controller.has_power_feedback:
        entities.append(ThermoPilotPowerStatusSensor(controller, entry))
    async_add_entities(entities)


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


class ThermoPilotDiagnosticSensor(ThermoPilotSensorBase):
    _attr_has_entity_name = True
    _attr_translation_key = "diagnostics"

    def __init__(self, controller: ThermoPilotController, entry: ConfigEntry) -> None:
        super().__init__(controller, entry)
        self._attr_unique_id = f"{entry.data[CONF_DEVICE_ID]}_diagnostics"

    @property
    def native_value(self) -> str:
        return self.controller.diagnostic_status

    @property
    def extra_state_attributes(self) -> dict:
        return self.controller.diagnostic_attributes


class ThermoPilotPowerStatusSensor(ThermoPilotSensorBase):
    _attr_has_entity_name = True
    _attr_translation_key = "power_feedback_status"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["off", "starting", "on", "unknown"]

    def __init__(self, controller: ThermoPilotController, entry: ConfigEntry) -> None:
        super().__init__(controller, entry)
        self._attr_unique_id = f"{entry.data[CONF_DEVICE_ID]}_stato"

    @property
    def native_value(self) -> str:
        return self.controller.power_classification

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "power": self.controller.power,
            "last_command_result": self.controller.last_command_result,
            "command_phase": self.controller.command_phase,
            "requested_physical_state": self.controller.requested_physical_state,
            "attempt": self.controller.command_attempt,
            "maximum_attempts": self.controller.maximum_attempts,
            "confirmation_pending": self.controller.confirmation_pending,
            "state_quality": "confirmed",
        }
