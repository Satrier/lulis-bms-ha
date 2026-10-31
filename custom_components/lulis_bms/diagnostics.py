"""Diagnostics for LULIS BMS (Settings → Devices → ⋮ → Download diagnostics)."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import LulisConfigEntry


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: LulisConfigEntry) -> dict[str, Any]:
    coordinator = entry.runtime_data
    return {
        "entry": {"data": dict(entry.data), "options": dict(entry.options)},
        "last_update_success": coordinator.last_update_success,
        "data": coordinator.data,
        "raw_frames": {f"0x{cmd:02x}": payload.hex() for cmd, payload in coordinator.last_frames.items()},
        # protection thresholds are read on demand only (read-only, never written)
        "protection_thresholds": await coordinator.async_read_thresholds(),
    }
