"""Auto-sleep delay for LULIS BMS."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import LulisConfigEntry
from .const import MAX_AUTO_SLEEP_MIN
from .coordinator import LulisCoordinator
from .entity import LulisEntity


class LulisAutoSleepNumber(LulisEntity, NumberEntity):
    """Minutes after a wake (or a change of this value) until Sleep is pressed automatically; 0 = off."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 0
    _attr_native_max_value = MAX_AUTO_SLEEP_MIN
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_translation_key = "auto_sleep"

    def __init__(self, coordinator: LulisCoordinator) -> None:
        super().__init__(coordinator, "auto_sleep")

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self) -> float:
        return self.coordinator.auto_sleep_min

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.async_set_auto_sleep(int(value))


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LulisConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([LulisAutoSleepNumber(entry.runtime_data)])
