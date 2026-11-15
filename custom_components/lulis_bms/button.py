"""Wake button for LULIS BMS."""

from __future__ import annotations

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import LulisConfigEntry
from .coordinator import LulisCoordinator
from .entity import LulisEntity
from .protocol import CTL_RESET


class LulisRestartButton(LulisEntity, ButtonEntity):
    """Wakes a sleeping pack (output stuck at ~37 V) by resetting the BMS MCU.

    Same as the app's Control → Reset MCU → Open; the BLE link drops and
    reconnects.
    Keeps the "restart" key so entity ids from 0.2-0.3 stay the same.
    """

    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_translation_key = "wake"

    def __init__(self, coordinator: LulisCoordinator) -> None:
        super().__init__(coordinator, "restart")

    @property
    def available(self) -> bool:
        # Must stay pressable while polling fails: that is exactly when the pack is asleep.
        # async_control raises a clear error if the battery is out of range.
        return True

    async def async_press(self) -> None:
        await self.coordinator.async_control(CTL_RESET, True, refresh=False, require_ack=False)
        await self.coordinator.async_disconnect()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LulisConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([LulisRestartButton(entry.runtime_data)])
