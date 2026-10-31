"""Sensors for LULIS BMS."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import LulisConfigEntry
from .const import DOMAIN
from .coordinator import LulisCoordinator


@dataclass(frozen=True, kw_only=True)
class LulisSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], Any]


def _key(k: str) -> Callable[[dict[str, Any]], Any]:
    return lambda d: d.get(k)


def _idx(k: str, i: int) -> Callable[[dict[str, Any]], Any]:
    return lambda d: d[k][i] if len(d.get(k) or []) > i else None


V = dict(
    native_unit_of_measurement=UnitOfElectricPotential.VOLT,
    device_class=SensorDeviceClass.VOLTAGE,
    state_class=SensorStateClass.MEASUREMENT,
)
T = dict(
    native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    device_class=SensorDeviceClass.TEMPERATURE,
    state_class=SensorStateClass.MEASUREMENT,
)

SENSORS: tuple[LulisSensorDescription, ...] = (
    LulisSensorDescription(key="voltage", name="Voltage", suggested_display_precision=2, value_fn=_key("voltage"), **V),
    LulisSensorDescription(
        key="current", name="Current", value_fn=_key("current"), suggested_display_precision=2,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT, state_class=SensorStateClass.MEASUREMENT,
    ),
    LulisSensorDescription(
        key="power", name="Power", value_fn=_key("power"), suggested_display_precision=0,
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER, state_class=SensorStateClass.MEASUREMENT,
    ),
    LulisSensorDescription(
        key="soc", name="Battery", value_fn=_key("soc"), suggested_display_precision=1,
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY, state_class=SensorStateClass.MEASUREMENT,
    ),
    LulisSensorDescription(
        key="soh", name="State of health", value_fn=_key("soh"),
        native_unit_of_measurement=PERCENTAGE, state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    LulisSensorDescription(key="cell_max", name="Cell voltage max", suggested_display_precision=3, value_fn=_key("cell_max"), **V),
    LulisSensorDescription(key="cell_min", name="Cell voltage min", suggested_display_precision=3, value_fn=_key("cell_min"), **V),
    LulisSensorDescription(key="cell_diff", name="Cell voltage delta", suggested_display_precision=3, value_fn=_key("cell_diff"), **V),
    LulisSensorDescription(
        key="cycles", name="Cycles", value_fn=_key("cycles"),
        state_class=SensorStateClass.TOTAL_INCREASING, entity_category=EntityCategory.DIAGNOSTIC,
    ),
    LulisSensorDescription(
        key="capacity_design", name="Design capacity", value_fn=_key("capacity_design"),
        native_unit_of_measurement="Ah", entity_category=EntityCategory.DIAGNOSTIC,
    ),
    LulisSensorDescription(
        key="remaining", name="Remaining capacity", suggested_display_precision=1,
        value_fn=lambda d: round(d["soc"] * d["capacity_design"] / 100, 2)
        if d.get("soc") is not None and d.get("capacity_design") else None,
        native_unit_of_measurement="Ah", state_class=SensorStateClass.MEASUREMENT,
    ),
    LulisSensorDescription(
        key="flags", name="Status flags", value_fn=lambda d: "-".join(
            d.get(k, "") for k in ("alarm_flags", "protect_flags", "fault_flags", "system_flags")
        ) if d.get("alarm_flags") is not None else None,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)

TEMP_NAMES = ["Temperature 1", "Temperature 2", "MOS temperature"]


class LulisSensor(CoordinatorEntity[LulisCoordinator], SensorEntity):
    _attr_has_entity_name = True
    entity_description: LulisSensorDescription

    def __init__(self, coordinator: LulisCoordinator, desc: LulisSensorDescription) -> None:
        super().__init__(coordinator)
        self.entity_description = desc
        self._attr_unique_id = f"{coordinator.address}_{desc.key}"
        data = coordinator.data or {}
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.address)},
            connections={(dr.CONNECTION_BLUETOOTH, coordinator.address)},
            manufacturer="LULIS",
            name="LULIS Battery",
            model=data.get("model"),
            serial_number=data.get("serial"),
        )

    @property
    def native_value(self) -> Any:
        if not self.coordinator.data:
            return None
        return self.entity_description.value_fn(self.coordinator.data)


async def async_setup_entry(
    hass: HomeAssistant, entry: LulisConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    coordinator = entry.runtime_data
    data = coordinator.data or {}
    n_temps = len(data.get("temps") or []) or 3
    n_cells = len(data.get("cells") or []) or 24

    descs = list(SENSORS)
    for i in range(n_temps):
        descs.append(LulisSensorDescription(
            key=f"temp_{i + 1}", name=TEMP_NAMES[i] if i < len(TEMP_NAMES) else f"Temperature {i + 1}",
            value_fn=_idx("temps", i), **T,
        ))
    for i in range(n_cells):
        descs.append(LulisSensorDescription(
            key=f"cell_{i + 1}", name=f"Cell {i + 1} voltage", suggested_display_precision=3,
            value_fn=_idx("cells", i), entity_category=EntityCategory.DIAGNOSTIC, **V,
        ))
    async_add_entities(LulisSensor(coordinator, d) for d in descs)
