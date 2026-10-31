"""LULIS / LK86xx BMS frame protocol (no Home Assistant imports).

Read request : 3A 7E 01 01 <cmd> 00 <sum8>
Write request: 3A 7E 01 00 <cmd> <len> <data...> <sum8>
Response     : 3B 7E 01 <flag> <cmd> <len> <data...> <sum8>

sum8 = sum of all preceding bytes & 0xFF.
Integers are little-endian signed int16, temperatures are 0.1 K.
Reverse-engineered from the LULIS BATTERY app v1.0.6.
"""

from __future__ import annotations

from typing import Any

CMD_MODEL = 0x02  # BMS model (ASCII)
CMD_SERIAL = 0x05  # serial number (ASCII)
CMD_CYCLES = 0x09  # design cycles, cycles, full / design capacity
CMD_PACK = 0x1E  # voltage, current, SOC, SOH, cell min/max, status bits
CMD_TEMPS = 0x1F  # temperature sensors
CMD_CELLS = 0x20  # balance bitmap + cell voltages
CMD_CONTROL = 0x3C  # write: sleep / discharge / charge / reset / storage

STATIC_COMMANDS = (CMD_MODEL, CMD_SERIAL)
POLL_COMMANDS = (CMD_PACK, CMD_TEMPS, CMD_CELLS, CMD_CYCLES)

# Control (0x3C) slots, as on the app's Control tab: 00=off, 01=on, FF=unchanged
CTL_SLEEP, CTL_DISCHARGE, CTL_CHARGE, CTL_RESET, CTL_STORAGE = range(5)


def _sum8(b: bytes) -> int:
    return sum(b) & 0xFF


def build_read(cmd: int) -> bytes:
    b = bytes([0x3A, 0x7E, 0x01, 0x01, cmd, 0x00])
    return b + bytes([_sum8(b)])


def build_write(cmd: int, data: bytes) -> bytes:
    b = bytes([0x3A, 0x7E, 0x01, 0x00, cmd, len(data)]) + data
    return b + bytes([_sum8(b)])


def build_control(slot: int, on: bool) -> bytes:
    data = bytearray(b"\xff" * 5)
    data[slot] = 0x01 if on else 0x00
    return build_write(CMD_CONTROL, bytes(data))


def _s16(d: bytes, off: int) -> int:
    v = d[off] | (d[off + 1] << 8)
    return v - 0x10000 if v & 0x8000 else v


def _k2c(raw: int) -> float:
    return round((raw - 2731) / 10, 1)


def _ascii(d: bytes) -> str:
    return d.replace(b"\x00", b"").decode("ascii", "replace").strip()


class FrameParser:
    """Reassemble BLE notification chunks into (cmd, payload) frames."""

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> list[tuple[int, bytes]]:
        out: list[tuple[int, bytes]] = []
        self._buf.extend(data)
        while True:
            i = self._buf.find(b"\x3b\x7e")
            if i < 0:
                # keep a possibly split header byte
                self._buf[:] = self._buf[-1:] if self._buf[-1:] == b"\x3b" else b""
                return out
            del self._buf[:i]
            if len(self._buf) < 6:
                return out
            total = 6 + self._buf[5] + 1
            if len(self._buf) < total:
                return out
            frame = bytes(self._buf[:total])
            del self._buf[:total]
            if _sum8(frame[:-1]) == frame[-1]:
                out.append((frame[4], frame[6:-1]))


def decode(frames: dict[int, bytes]) -> dict[str, Any]:
    """Decode payloads keyed by command into a flat dict."""
    out: dict[str, Any] = {}
    if (d := frames.get(CMD_MODEL)) is not None:
        out["model"] = _ascii(d)
    if (d := frames.get(CMD_SERIAL)) is not None:
        out["serial"] = _ascii(d)
    if (d := frames.get(CMD_PACK)) is not None and len(d) >= 38:
        out.update(
            voltage=_s16(d, 0) / 100,
            current=_s16(d, 2) / 100,
            soc=round(_s16(d, 4) / 50, 1),
            soh=_s16(d, 6),
            cell_max=_s16(d, 8) / 1000,
            cell_max_idx=_s16(d, 10),
            cell_min=_s16(d, 12) / 1000,
            cell_min_idx=_s16(d, 14),
            cell_diff=_s16(d, 16) / 1000,
            temp_max=_k2c(_s16(d, 18)),
            temp_min=_k2c(_s16(d, 22)),
            alarm_flags=d[26:30].hex(),
            protect_flags=d[30:34].hex(),
            fault_flags=d[34:36].hex(),
            system_flags=d[36:38].hex(),
            discharge_mos=bool(d[36] & 0x80),
            charge_mos=bool(d[36] & 0x40),
            predischarge_mos=bool(d[36] & 0x20),
        )
        out["power"] = round(out["voltage"] * out["current"], 1)
    if (d := frames.get(CMD_TEMPS)) is not None and len(d) >= 2:
        n = _s16(d, 0)
        out["temps"] = [_k2c(_s16(d, 2 + 2 * i)) for i in range(n) if 3 + 2 * i < len(d)]
    if (d := frames.get(CMD_CELLS)) is not None and len(d) >= 2:
        n = _s16(d, 0)
        nb = (n + 7) // 8
        out["cells"] = [_s16(d, 2 + nb + 2 * i) / 1000 for i in range(n) if 3 + nb + 2 * i < len(d)]
    if (d := frames.get(CMD_CYCLES)) is not None and len(d) >= 8:
        out.update(
            design_cycles=_s16(d, 0),
            cycles=_s16(d, 2),
            capacity_full=_s16(d, 4) / 100,
            capacity_design=_s16(d, 6) / 100,
        )
    return out
