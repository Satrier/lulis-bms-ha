"""Charge / discharge MOS switches for LULIS BMS."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import LulisConfigEntry
from .coordinator import LulisCoordinator
from .entity import LulisEntity
from .protocol import CTL_CHARGE, CTL_DISCHARGE

SWITCHES: tuple[tuple[str, int], ...] = (
    ("charge_mos", CTL_CHARGE),
    ("discharge_mos", CTL_DISCHARGE),
)


class LulisMosSwitch(LulisEntity, SwitchEntity):
    def __init__(self, coordinator: LulisCoordinator, key: str, slot: int) -> None:
        super().__init__(coordinator, key)
        self._key = key
        self._slot = slot
        self._attr_translation_key = key

    @property
    def is_on(self) -> bool | None:
        return (self.coordinator.data or {}).get(self._key)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._set(False)

    async def _set(self, on: bool) -> None:
        await self.coordinator.async_control(self._slot, on)
        state = (self.coordinator.data or {}).get(self._key)
        if state is not None and state != on:
            # BMS acknowledged but kept the MOS state (e.g. its own protection logic)
            raise HomeAssistantError(f"The BMS accepted the command but the MOS is still {'on' if state else 'off'}")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LulisConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities(LulisMosSwitch(entry.runtime_data, key, slot) for key, slot in SWITCHES)
