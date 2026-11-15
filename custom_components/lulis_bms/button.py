"""Wake, sleep and restart buttons for LULIS BMS."""

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
        if self.coordinator.asleep:
            await self.coordinator.async_wake()
        await self.coordinator.async_control(CTL_RESET, True, refresh=False, require_ack=False)
        await self.coordinator.async_disconnect()


class LulisWakeButton(LulisEntity, ButtonEntity):
    """Wakes a sleeping pack: a fresh BLE connection turns the discharge MOS on."""

    _attr_translation_key = "wake"

    def __init__(self, coordinator: LulisCoordinator) -> None:
        super().__init__(coordinator, "wake")

    @property
    def available(self) -> bool:
        return True  # needed exactly while polling is stopped or failing

    async def async_press(self) -> None:
        await self.coordinator.async_wake()


class LulisSleepButton(LulisEntity, ButtonEntity):
    """Lets the pack fall asleep: no new connections until Wake.

    The BMS ignores the sleep command; it turns its output off (~37 V) by itself a
    few minutes after a connection was opened, and any new connection wakes it.
    HA keeps polling over the open link until the discharge MOS is off.
    """

    _attr_translation_key = "sleep"

    def __init__(self, coordinator: LulisCoordinator) -> None:
        super().__init__(coordinator, "sleep")

    @property
    def available(self) -> bool:
        return True

    async def async_press(self) -> None:
        await self.coordinator.async_sleep()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LulisConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    c = entry.runtime_data
    async_add_entities([LulisWakeButton(c), LulisSleepButton(c), LulisRestartButton(c)])
