"""Base entity for LULIS BMS."""

from __future__ import annotations

from homeassistant.const import CONF_NAME
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import LulisCoordinator


class LulisEntity(CoordinatorEntity[LulisCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: LulisCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.address}_{key}"
        data = coordinator.data or {}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address)},
            connections={(dr.CONNECTION_BLUETOOTH, coordinator.address)},
            manufacturer="LULIS",
            # entries created before v0.2.0 have no stored name: keep "LULIS Battery"
            name=coordinator.config_entry.data.get(CONF_NAME, "LULIS Battery"),
            model=data.get("model"),
            serial_number=data.get("serial"),
        )
