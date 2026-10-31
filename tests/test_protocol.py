"""Protocol tests using frames captured from a real 72V 40Ah LULIS pack."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "lulis_protocol", Path(__file__).parents[1] / "custom_components" / "lulis_bms" / "protocol.py"
)
protocol = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(protocol)

CAPTURE = bytes.fromhex(
    "3b7e010102144c523335395631335f4e303331783630410000002a"
    "3b7e0101051a41454a4342483130414d423131303032000000000000000000009c"
    "3b7e01011e263a1f000060136300040d0000020d0c000200680b0000650b0100000000000000000000009300d3"
    "3b7e01011f080300680b650b6e0b41"
    "3b7e010120351800000000040d040d040d040d040d040d040d040d040d040d040d040d020d020d020d020d020d020d020d020d020d020d020d010da7"
    "3b7e01010908b80b1400a00fa00f01"
)


def _frames(chunk: int) -> dict[int, bytes]:
    parser = protocol.FrameParser()
    out: dict[int, bytes] = {}
    for i in range(0, len(CAPTURE), chunk):
        for cmd, payload in parser.feed(CAPTURE[i : i + chunk]):
            out[cmd] = payload
    return out


def test_requests_match_app() -> None:
    assert protocol.build_read(0x1E).hex() == "3a7e01011e00d8"
    assert protocol.build_read(0x02).hex() == "3a7e01010200bc"
    assert protocol.build_control(protocol.CTL_CHARGE, False).hex() == "3a7e01003c05ffff00fffff6"
    assert protocol.build_control(protocol.CTL_DISCHARGE, True).hex() == "3a7e01003c05ff01fffffff7"


def test_parser_handles_ble_chunking() -> None:
    for chunk in (1, 7, 20, 244):
        assert set(_frames(chunk)) == {0x02, 0x05, 0x1E, 0x1F, 0x20, 0x09}


def test_parser_drops_bad_checksum() -> None:
    bad = bytearray(CAPTURE[:27])
    bad[-1] ^= 0xFF
    assert protocol.FrameParser().feed(bytes(bad)) == []


def test_decode() -> None:
    d = protocol.decode(_frames(20))
    assert d["model"] == "LR359V13_N031x60A"
    assert d["serial"] == "AEJCBH10AMB11002"
    assert d["voltage"] == 79.94
    assert d["current"] == 0.0
    assert d["soc"] == 99.2
    assert d["soh"] == 99
    assert d["cell_diff"] == 0.002
    assert d["temps"] == [18.9, 18.6, 19.5]
    assert len(d["cells"]) == 24
    assert d["cells"][0] == 3.332 and d["cells"][-1] == 3.329
    assert d["cycles"] == 20
    assert d["capacity_design"] == 40.0
    assert d["discharge_mos"] is True
    assert d["charge_mos"] is False
