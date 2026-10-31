"""LULIS / LK86xx BMS frame protocol.

Request : 3A 7E 01 01 <code> 00 <sum8>
Response: 3B 7E 01 <flag> <code> <len> <data...len> <sum8>
Integers are little-endian signed int16. Temperatures are 0.1 K.
"""

from __future__ import annotations

from typing import Any

from .const import CMD_CELLS, CMD_CYCLES, CMD_MODEL, CMD_PACK, CMD_SERIAL, CMD_TEMPS


def build_read(code: int) -> bytes:
    b = bytes([0x3A, 0x7E, 0x01, 0x01, code, 0x00])
    return b + bytes([sum(b) & 0xFF])


def build_write(code: int, data: bytes) -> bytes:
    b = bytes([0x3A, 0x7E, 0x01, 0x00, code, len(data)]) + data
    return b + bytes([sum(b) & 0xFF])


# Control (0x3C) slots, from the app's Control tab: 00=off, 01=on, FF=unchanged
CTL_SLEEP, CTL_DISCHARGE, CTL_CHARGE, CTL_RESET, CTL_STORAGE = range(5)


def build_control(slot: int, on: bool) -> bytes:
    data = bytearray(b"\xff" * 5)
    data[slot] = 0x01 if on else 0x00
    return build_write(0x3C, bytes(data))


def _s16(d: bytes, off: int) -> int:
    v = d[off] | (d[off + 1] << 8)
    return v - 0x10000 if v & 0x8000 else v


def _k2c(raw: int) -> float:
    return round((raw - 2731) / 10, 1)


class FrameParser:
    """Reassembles notification chunks into (code, payload) frames."""

    def __init__(self) -> None:
        self._buf = bytearray()

    def feed(self, data: bytes) -> list[tuple[int, bytes]]:
        out: list[tuple[int, bytes]] = []
        self._buf.extend(data)
        while True:
            i = self._buf.find(b"\x3b\x7e")
            if i < 0:
                # keep a possible split header byte
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
            if (sum(frame[:-1]) & 0xFF) == frame[-1]:
                out.append((frame[4], frame[6:-1]))


def _ascii(d: bytes) -> str:
    return d.replace(b"\x00", b"").decode("ascii", "replace").strip()


def decode(frames: dict[int, bytes]) -> dict[str, Any]:
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
        )
        out["power"] = round(out["voltage"] * out["current"], 1)
        sys_low = d[36]
        out["discharge_mos"] = bool(sys_low & 0x80)
        out["charge_mos"] = bool(sys_low & 0x40)
        out["predischarge_mos"] = bool(sys_low & 0x20)
    if (d := frames.get(CMD_TEMPS)) is not None and len(d) >= 2:
        n = _s16(d, 0)
        out["temps"] = [_k2c(_s16(d, 2 + 2 * i)) for i in range(n) if 3 + 2 * i < len(d)]
    if (d := frames.get(CMD_CELLS)) is not None and len(d) >= 2:
        n = _s16(d, 0)
        nb = (n + 7) // 8
        out["cells"] = [
            _s16(d, 2 + nb + 2 * i) / 1000 for i in range(n) if 3 + nb + 2 * i < len(d)
        ]
    if (d := frames.get(CMD_CYCLES)) is not None and len(d) >= 8:
        out.update(
            design_cycles=_s16(d, 0),
            cycles=_s16(d, 2),
            capacity_full=_s16(d, 4) / 100,
            capacity_design=_s16(d, 6) / 100,
        )
    return out
