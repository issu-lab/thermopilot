"""Climate platform for ThermoPilot."""

from __future__ import annotations

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature
from homeassistant.components.climate.const import HVACAction, HVACMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    CONF_DEVICE_ID,
    DOMAIN,
    INTEGRATION_VERSION,
    MODE_COOL,
    MODE_DRY,
    MODE_HEAT,
    MODE_OFF,
    OPT_MAX_TEMP,
    OPT_MAX_HUMIDITY,
    OPT_MIN_TEMP,
    OPT_MIN_HUMIDITY,
    OPT_HUMIDITY_STEP,
    OPT_TEMP_STEP,
    PRESET_NONE,
    PRESETS,
)
from .controller import ThermoPilotController

MODE_TO_HA = {
    MODE_OFF: HVACMode.OFF,
    MODE_COOL: HVACMode.COOL,
    MODE_HEAT: HVACMode.HEAT,
    MODE_DRY: HVACMode.DRY,
}
ACTION_TO_HA = {
    "off": HVACAction.OFF,
    "idle": HVACAction.IDLE,
    "cooling": HVACAction.COOLING,
    "heating": HVACAction.HEATING,
    "drying": HVACAction.DRYING,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the ThermoPilot climate entity."""
    controller: ThermoPilotController = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ThermoPilotClimate(controller, entry)])


class ThermoPilotClimate(ClimateEntity):
    """Native climate entity backed by one ThermoPilot controller."""

    _attr_has_entity_name = False
    _attr_should_poll = False
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE
        | ClimateEntityFeature.PRESET_MODE
        | ClimateEntityFeature.TURN_ON
        | ClimateEntityFeature.TURN_OFF
    )

    def __init__(self, controller: ThermoPilotController, entry: ConfigEntry) -> None:
        self.controller = controller
        self.entry = entry
        self._attr_name = entry.title
        self._attr_unique_id = entry.data[CONF_DEVICE_ID]
        self._attr_hvac_modes = [MODE_TO_HA[mode] for mode in controller.supported_modes]
        self._attr_preset_modes = [PRESET_NONE, *PRESETS]
        self._attr_min_temp = float(controller.option(OPT_MIN_TEMP))
        self._attr_max_temp = float(controller.option(OPT_MAX_TEMP))
        self._attr_target_temperature_step = float(controller.option(OPT_TEMP_STEP))
        if MODE_DRY in controller.supported_modes:
            self._attr_supported_features |= ClimateEntityFeature.TARGET_HUMIDITY
            self._attr_min_humidity = float(controller.option(OPT_MIN_HUMIDITY))
            self._attr_max_humidity = float(controller.option(OPT_MAX_HUMIDITY))
            self._attr_target_humidity_step = float(
                controller.option(OPT_HUMIDITY_STEP)
            )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            manufacturer="iSSU Lab",
            model="ThermoPilot Virtual Climate Controller",
            sw_version=INTEGRATION_VERSION,
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            self.controller.async_add_update_listener(self._controller_updated)
        )

    @callback
    def _controller_updated(self) -> None:
        self.async_write_ha_state()

    @property
    def available(self) -> bool:
        return self.controller.available

    @property
    def current_temperature(self) -> float | None:
        return self.controller.perceived_temperature

    @property
    def current_humidity(self) -> float | None:
        return self.controller.current_humidity

    @property
    def target_temperature(self) -> float | None:
        return self.controller.target_temperature

    @property
    def target_humidity(self) -> float | None:
        return self.controller.target_humidity

    @property
    def hvac_mode(self) -> HVACMode:
        return MODE_TO_HA[self.controller.state.hvac_mode]

    @property
    def hvac_action(self) -> HVACAction | None:
        return ACTION_TO_HA.get(self.controller.hvac_action)

    @property
    def preset_mode(self) -> str:
        return self.controller.preset

    @property
    def extra_state_attributes(self) -> dict:
        return {
            "raw_temperature": self.controller.current_temperature,
            "pressure": self.controller.current_pressure,
            "dew_point": self.controller.current_dew_point,
            "target_dew_point": (
                self.controller.effective_dry_target_dew_point
            ),
            **self.controller.diagnostic_attributes,
        }

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        await self.controller.async_set_hvac_mode(hvac_mode.value)

    async def async_turn_on(self) -> None:
        """Restore the last thermal mode and evaluate physical demand."""
        await self.controller.async_turn_on()

    async def async_turn_off(self) -> None:
        """Select logical OFF and stop an active physical device."""
        await self.controller.async_set_hvac_mode(MODE_OFF)

    async def async_set_temperature(self, **kwargs) -> None:
        if ATTR_TEMPERATURE in kwargs:
            await self.controller.async_set_temperature(float(kwargs[ATTR_TEMPERATURE]))

    async def async_set_humidity(self, humidity: int) -> None:
        await self.controller.async_set_humidity(float(humidity))

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        await self.controller.async_set_preset(preset_mode)
