"""Sensors for LULIS BMS."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import time
from typing import Any

from homeassistant.components.sensor import (
    RestoreSensor,
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
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import LulisConfigEntry
from .coordinator import LulisCoordinator
from .entity import LulisEntity
from .protocol import ALARM_STATES, PROTECTION_STATES

AH = "Ah"
MAX_INTEGRATION_GAP_S = 300  # don't integrate energy across longer outages


@dataclass(frozen=True, kw_only=True)
class LulisSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict[str, Any]], Any]


def _get(key: str) -> Callable[[dict[str, Any]], Any]:
    return lambda d: d.get(key)


def _item(key: str, i: int) -> Callable[[dict[str, Any]], Any]:
    return lambda d: d[key][i] if len(d.get(key) or ()) > i else None


def _remaining(d: dict[str, Any]) -> float | None:
    if d.get("soc") is None or not d.get("capacity_design"):
        return None
    return round(d["soc"] * d["capacity_design"] / 100, 2)


def _flags(d: dict[str, Any]) -> str | None:
    if d.get("alarm_flags") is None:
        return None
    return "-".join(d[k] for k in ("alarm_flags", "protect_flags", "fault_flags", "system_flags"))


_VOLT: dict[str, Any] = {
    "native_unit_of_measurement": UnitOfElectricPotential.VOLT,
    "device_class": SensorDeviceClass.VOLTAGE,
    "state_class": SensorStateClass.MEASUREMENT,
}
_CELL_VOLT: dict[str, Any] = {**_VOLT, "suggested_display_precision": 3}
_TEMP: dict[str, Any] = {
    "native_unit_of_measurement": UnitOfTemperature.CELSIUS,
    "device_class": SensorDeviceClass.TEMPERATURE,
    "state_class": SensorStateClass.MEASUREMENT,
}

SENSORS: tuple[LulisSensorDescription, ...] = (
    LulisSensorDescription(
        key="voltage", translation_key="voltage", suggested_display_precision=2, value_fn=_get("voltage"), **_VOLT
    ),
    LulisSensorDescription(
        key="current",
        translation_key="current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=_get("current"),
    ),
    LulisSensorDescription(
        key="power",
        translation_key="power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=_get("power"),
    ),
    LulisSensorDescription(
        key="soc",
        translation_key="soc",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=_get("soc"),
    ),
    LulisSensorDescription(
        key="remaining",
        translation_key="remaining",
        native_unit_of_measurement=AH,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=_remaining,
    ),
    LulisSensorDescription(key="cell_max", translation_key="cell_max", value_fn=_get("cell_max"), **_CELL_VOLT),
    LulisSensorDescription(key="cell_min", translation_key="cell_min", value_fn=_get("cell_min"), **_CELL_VOLT),
    LulisSensorDescription(key="cell_diff", translation_key="cell_diff", value_fn=_get("cell_diff"), **_CELL_VOLT),
    LulisSensorDescription(
        key="soh",
        translation_key="soh",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_get("soh"),
    ),
    LulisSensorDescription(
        key="cycles",
        translation_key="cycles",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_get("cycles"),
    ),
    LulisSensorDescription(
        key="capacity_design",
        translation_key="capacity_design",
        native_unit_of_measurement=AH,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=_get("capacity_design"),
    ),
    LulisSensorDescription(
        key="flags",
        translation_key="flags",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=_flags,
    ),
)

TEMP_KEYS = ("temp_1", "temp_2", "temp_mos")


class LulisSensor(LulisEntity, SensorEntity):
    entity_description: LulisSensorDescription

    def __init__(self, coordinator: LulisCoordinator, description: LulisSensorDescription) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        if not self.coordinator.data:
            return None
        return self.entity_description.value_fn(self.coordinator.data)


class LulisIndexedSensor(LulisSensor):
    """Cell voltage / extra temperature sensor with an {index} placeholder."""

    def __init__(self, coordinator: LulisCoordinator, description: LulisSensorDescription, index: int) -> None:
        super().__init__(coordinator, description)
        self._attr_translation_placeholders = {"index": str(index)}


class LulisStatusSensor(LulisEntity, SensorEntity):
    """Enum sensor: 'ok' or the first active alarm / protection; full list in attributes."""

    _attr_device_class = SensorDeviceClass.ENUM

    def __init__(self, coordinator: LulisCoordinator, key: str, sources: tuple[str, ...], options: tuple[str, ...]):
        super().__init__(coordinator, key)
        self._attr_translation_key = key
        self._sources = sources
        self._attr_options = ["ok", *options]

    def _active(self) -> list[str] | None:
        d = self.coordinator.data or {}
        if "alarms" not in d:
            return None
        return [x for src in self._sources for x in d.get(src, ())]

    @property
    def native_value(self) -> str | None:
        active = self._active()
        if active is None:
            return None
        return active[0] if active else "ok"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"active": self._active() or []}


class LulisEnergySensor(LulisEntity, RestoreSensor):
    """Integrates pack power into charged / discharged kWh for the Energy dashboard."""

    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 3

    def __init__(self, coordinator: LulisCoordinator, key: str, sign: int) -> None:
        super().__init__(coordinator, key)
        self._attr_translation_key = key
        self._sign = sign
        self._attr_native_value = 0.0
        self._last: tuple[float, float] | None = None  # (monotonic s, power W)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        if (last := await self.async_get_last_sensor_data()) and last.native_value is not None:
            self._attr_native_value = float(last.native_value)

    @callback
    def _handle_coordinator_update(self) -> None:
        power = (self.coordinator.data or {}).get("power")
        now = time.monotonic()
        if power is not None and self.coordinator.last_update_success:
            if self._last is not None and (dt := now - self._last[0]) <= MAX_INTEGRATION_GAP_S:
                p0 = max(self._sign * self._last[1], 0.0)
                p1 = max(self._sign * power, 0.0)
                total = float(self._attr_native_value or 0) + (p0 + p1) / 2 * dt / 3_600_000
                self._attr_native_value = round(total, 6)
            self._last = (now, power)
        else:
            self._last = None
        super()._handle_coordinator_update()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LulisConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    data = coordinator.data or {}
    n_temps = len(data.get("temps") or ()) or len(TEMP_KEYS)
    n_cells = len(data.get("cells") or ()) or 24

    entities: list[SensorEntity] = [LulisSensor(coordinator, d) for d in SENSORS]
    for i in range(n_temps):
        named = i < len(TEMP_KEYS)
        key = TEMP_KEYS[i] if named else f"temp_{i + 1}"
        desc = LulisSensorDescription(
            key=key, translation_key=key if named else "temp_n", value_fn=_item("temps", i), **_TEMP
        )
        entities.append(LulisIndexedSensor(coordinator, desc, i + 1))
    for i in range(n_cells):
        desc = LulisSensorDescription(
            key=f"cell_{i + 1}",
            translation_key="cell_voltage",
            entity_category=EntityCategory.DIAGNOSTIC,
            value_fn=_item("cells", i),
            **_CELL_VOLT,
        )
        entities.append(LulisIndexedSensor(coordinator, desc, i + 1))
    entities.append(LulisStatusSensor(coordinator, "alarm", ("alarms",), ALARM_STATES))
    entities.append(LulisStatusSensor(coordinator, "protection", ("protections", "faults"), PROTECTION_STATES))
    # BMS convention: positive current = charging (option "invert current" flips it)
    entities.append(LulisEnergySensor(coordinator, "energy_charged", +1))
    entities.append(LulisEnergySensor(coordinator, "energy_discharged", -1))
    async_add_entities(entities)
