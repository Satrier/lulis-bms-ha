"""Base entity for LULIS BMS."""

from __future__ import annotations

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
            name="LULIS Battery",
            model=data.get("model"),
            serial_number=data.get("serial"),
        )
