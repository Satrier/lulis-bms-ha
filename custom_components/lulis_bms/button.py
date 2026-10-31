"""Restart-BMS button for LULIS BMS (disabled by default)."""

from __future__ import annotations

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import LulisConfigEntry
from .coordinator import LulisCoordinator
from .entity import LulisEntity
from .protocol import CTL_RESET


class LulisRestartButton(LulisEntity, ButtonEntity):
    """Resets the BMS MCU (the BLE link drops and reconnects)."""

    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False
    _attr_translation_key = "restart"

    def __init__(self, coordinator: LulisCoordinator) -> None:
        super().__init__(coordinator, "restart")

    async def async_press(self) -> None:
        await self.coordinator.async_control(CTL_RESET, True, refresh=False)
        await self.coordinator.async_disconnect()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LulisConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([LulisRestartButton(entry.runtime_data)])
