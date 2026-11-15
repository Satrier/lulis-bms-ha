"""Wake / restart and (experimental) sleep buttons for LULIS BMS."""

from __future__ import annotations

from homeassistant.components.button import ButtonDeviceClass, ButtonEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import LulisConfigEntry
from .coordinator import LulisCoordinator
from .entity import LulisEntity
from .protocol import CTL_RESET, CTL_SLEEP


class LulisRestartButton(LulisEntity, ButtonEntity):
    """Resets the BMS MCU (the app's Control → Reset MCU → Open).

    This is also how a sleeping pack (output stuck at ~37 V) is woken up.
    The BLE link drops and reconnects.
    """

    _attr_device_class = ButtonDeviceClass.RESTART
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "restart"

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


class LulisSleepButton(LulisEntity, ButtonEntity):
    """Experimental: sets the Control (0x3C) sleep slot.

    Hidden in the app's UI and untested on LULIS packs. The hope is that it puts
    the BMS into the same sleep (output off, ~37 V) that Wake / restart leaves.
    Disabled by default; the ack and the MOS state are logged at debug level.
    """

    _attr_entity_category = EntityCategory.CONFIG
    _attr_entity_registry_enabled_default = False
    _attr_translation_key = "sleep"

    def __init__(self, coordinator: LulisCoordinator) -> None:
        super().__init__(coordinator, "sleep")

    async def async_press(self) -> None:
        # a sleeping MCU may not answer; refresh afterwards shows the MOS state (or none)
        await self.coordinator.async_control(CTL_SLEEP, True, require_ack=False)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LulisConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([LulisRestartButton(entry.runtime_data), LulisSleepButton(entry.runtime_data)])
