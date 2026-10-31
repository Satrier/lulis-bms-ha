"""Charge / discharge MOS switches for LULIS BMS."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import LulisConfigEntry
from .const import DOMAIN
from .coordinator import LulisCoordinator
from .protocol import CTL_CHARGE, CTL_DISCHARGE

SWITCHES = (
    ("charge_mos", "Charging", CTL_CHARGE, "mdi:battery-charging"),
    ("discharge_mos", "Discharging", CTL_DISCHARGE, "mdi:battery-arrow-down"),
)


class LulisMosSwitch(CoordinatorEntity[LulisCoordinator], SwitchEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator: LulisCoordinator, key: str, name: str, slot: int, icon: str) -> None:
        super().__init__(coordinator)
        self._key = key
        self._slot = slot
        self._attr_name = name
        self._attr_icon = icon
        self._attr_unique_id = f"{coordinator.address}_{key}"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, coordinator.address)})

    @property
    def is_on(self) -> bool | None:
        return (self.coordinator.data or {}).get(self._key)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.coordinator.async_control(self._slot, True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.coordinator.async_control(self._slot, False)


async def async_setup_entry(
    hass: HomeAssistant, entry: LulisConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    c = entry.runtime_data
    async_add_entities(LulisMosSwitch(c, *s) for s in SWITCHES)
