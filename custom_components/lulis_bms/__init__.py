"""LULIS Battery BMS (LK86xx Telink BLE) integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import LulisCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.SWITCH]

type LulisConfigEntry = ConfigEntry[LulisCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: LulisConfigEntry) -> bool:
    coordinator = LulisCoordinator(hass, entry)
    # BLE links to batteries are often weak: don't block setup on the first poll,
    # entities simply stay unavailable until the battery answers.
    await coordinator.async_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: LulisConfigEntry) -> bool:
    if unloaded := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.async_disconnect()
    return unloaded
