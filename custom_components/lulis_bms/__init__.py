"""LULIS Battery BMS (LK86xx Telink BLE) integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.storage import Store

from .const import DOMAIN
from .coordinator import LulisCoordinator

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.NUMBER, Platform.SENSOR]

# (platform, old unique_id suffix, new suffix) for keys renamed in earlier versions
_RENAMED_KEYS = (("sensor", "temp_3", "temp_mos"),)
# entities removed in later versions: (platform, unique_id suffix)
# 0.3.0: MOS switches dropped, the BMS acknowledges but ignores 0x3C on LULIS packs
# 0.5.0: the "asleep" binary sensor became the three-state "sleep_state" sensor
_REMOVED_KEYS = (("switch", "charge_mos"), ("switch", "discharge_mos"), ("binary_sensor", "asleep"))
# entities that used to be disabled by default and are now needed: (platform, suffix)
# 0.3.1: the restart button is what wakes a sleeping pack
# 0.4.0: sleep works (by leaving the BMS alone) and is a main control
_ENABLED_KEYS = (("button", "restart"), ("button", "sleep"))
# entity_ids that carried a name suffix which is gone: (platform, unique_id suffix, old ending)
_RENAMED_IDS = (("button", "sleep", "_experimental"),)

type LulisConfigEntry = ConfigEntry[LulisCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: LulisConfigEntry) -> bool:
    coordinator = LulisCoordinator(hass, entry)
    await coordinator.async_load_state()
    # BLE links to batteries are often weak: don't block setup on the first poll,
    # entities simply stay unavailable until the battery answers.
    if not coordinator.asleep:  # connecting would wake a sleeping pack
        await coordinator.async_refresh()
    entry.runtime_data = coordinator

    _migrate_renamed_entities(hass, entry, coordinator.address)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


def _migrate_renamed_entities(hass: HomeAssistant, entry: LulisConfigEntry, address: str) -> None:
    """Keep the original entity_id (and its history) when a unique_id key was renamed."""
    registry = er.async_get(hass)
    for platform, old, new in _RENAMED_KEYS:
        old_id = registry.async_get_entity_id(platform, entry.domain, f"{address}_{old}")
        if old_id is None:
            continue
        if new_id := registry.async_get_entity_id(platform, entry.domain, f"{address}_{new}"):
            # both exist (v0.1.0 created a duplicate): drop the duplicate, give its id back
            registry.async_remove(new_id)
        registry.async_update_entity(old_id, new_unique_id=f"{address}_{new}")
    for platform, key in _REMOVED_KEYS:
        if entity_id := registry.async_get_entity_id(platform, entry.domain, f"{address}_{key}"):
            registry.async_remove(entity_id)
    for platform, key in _ENABLED_KEYS:
        entity_id = registry.async_get_entity_id(platform, entry.domain, f"{address}_{key}")
        entry_ = registry.async_get(entity_id) if entity_id else None
        if entry_ and entry_.disabled_by is er.RegistryEntryDisabler.INTEGRATION:
            registry.async_update_entity(entity_id, disabled_by=None)
    for platform, key, ending in _RENAMED_IDS:
        entity_id = registry.async_get_entity_id(platform, entry.domain, f"{address}_{key}")
        if entity_id and entity_id.endswith(ending):
            new_id = entity_id.removesuffix(ending)
            if registry.async_is_registered(new_id):
                continue
            registry.async_update_entity(entity_id, new_entity_id=new_id)


async def _async_options_updated(hass: HomeAssistant, entry: LulisConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_remove_entry(hass: HomeAssistant, entry: LulisConfigEntry) -> None:
    await Store(hass, 1, f"{DOMAIN}.{entry.entry_id}").async_remove()


async def async_unload_entry(hass: HomeAssistant, entry: LulisConfigEntry) -> bool:
    if unloaded := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.async_disconnect()
    return unloaded
