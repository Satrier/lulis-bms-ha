"""Problem binary sensor for LULIS BMS."""

from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import LulisConfigEntry
from .coordinator import LulisCoordinator
from .entity import LulisEntity


class LulisProblemSensor(LulisEntity, BinarySensorEntity):
    """On when the BMS reports any alarm, protection or fault."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_translation_key = "problem"

    def __init__(self, coordinator: LulisCoordinator) -> None:
        super().__init__(coordinator, "problem")

    def _active(self) -> list[str]:
        d = self.coordinator.data or {}
        return [*d.get("alarms", ()), *d.get("protections", ()), *d.get("faults", ())]

    @property
    def is_on(self) -> bool | None:
        if not self.coordinator.data or "alarms" not in self.coordinator.data:
            return None
        return bool(self._active())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        d = self.coordinator.data or {}
        return {k: d.get(k, []) for k in ("alarms", "protections", "faults")}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LulisConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([LulisProblemSensor(entry.runtime_data)])
