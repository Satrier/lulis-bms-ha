"""LULIS Battery BMS (LK86xx Telink BLE) integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import LulisCoordinator

PLATFORMS = [Platform.SENSOR, Platform.SWITCH]

type LulisConfigEntry = ConfigEntry[LulisCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: LulisConfigEntry) -> bool:
    coordinator = LulisCoordinator(hass, entry)
    # Weak BLE links fail often; don't block setup, entities go unavailable instead.
    await coordinator.async_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: LulisConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        await entry.runtime_data.async_disconnect()
    return ok
