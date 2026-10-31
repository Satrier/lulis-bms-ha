# LULIS Battery BMS for Home Assistant

A Home Assistant integration for LULIS lithium batteries. These batteries use a BMS with an **LK86xx (Telink) Bluetooth module**, which the phone app *LULIS BATTERY* talks to. The integration connects over BLE through Home Assistant's own Bluetooth stack, so it works with local adapters and with ESPHome Bluetooth proxies.

Tested with a 72V 40Ah LiFePO4 pack (24S): BMS model `LR359V13_N031x60A`, BLE name `LK8625-XXXXXX`.

## Features

- Auto-discovery of `LK86*` devices
- Sensors: pack voltage, current, power, SOC, SOH, remaining capacity, min/max/delta cell voltage, every cell voltage, temperatures (T1, T2, MOS), cycle count, design capacity, raw status flags
- Switches: **Charging** (charge MOS) and **Discharging** (discharge MOS)

> ⚠️ Turning **Discharging** off cuts power to the load immediately.

## Installation

### HACS (custom repository)
1. In HACS, open the ⋮ menu, choose **Custom repositories**, add this repository's URL and pick the **Integration** category.
2. Install **LULIS Battery BMS**, then restart Home Assistant.
3. The battery shows up under **Settings → Devices & services → Discovered**. If it doesn't, use **Add integration → LULIS Battery BMS**.

### Manual
Copy `custom_components/lulis_bms` into `<config>/custom_components/` and restart Home Assistant.

## Notes

- The BMS accepts **one BLE connection at a time**. While Home Assistant is connected, the phone app can't connect. To free it, disable the integration entry.
- The integration keeps the connection open and polls every 30 s.
- A weak signal (below about -85 dBm) causes frequent disconnects. An ESP32 running ESPHome Bluetooth Proxy near the battery fixes this.

## Protocol

This was reverse-engineered from the LULIS BATTERY app v1.0.6. Everything goes over Telink SPP:

| Direction | Characteristic UUID |
|---|---|
| notify (BMS → host) | `00010203-0405-0607-0809-0a0b0c0dffe1` |
| write (host → BMS) | `00010203-0405-0607-0809-0a0b0c0dffe2` |

Frame layout:

```
Read request : 3A 7E 01 01 <cmd> 00 <sum8>
Write request: 3A 7E 01 00 <cmd> <len> <data...> <sum8>
Response     : 3B 7E 01 <flag> <cmd> <len> <data...> <sum8>
sum8 = sum of all preceding bytes & 0xFF
Integers: little-endian signed int16. Temperatures: 0.1 K (°C = (raw - 2731) / 10)
```

| Cmd | Content |
|---|---|
| `02` | BMS model (ASCII) |
| `05` | Serial number (ASCII) |
| `09` | design cycles, cycles, full capacity ×0.01 Ah, design capacity ×0.01 Ah |
| `1E` | V ×0.01, I ×0.01, SOC /50, SOH, cell max (mV), idx, cell min (mV), idx, delta (mV), Tmax, idx, Tmin, idx, then status bytes: alarm[4], protect[4], fault[2], system[2]. System low byte: bit7 = discharge MOS, bit6 = charge MOS, bit5 = pre-discharge MOS |
| `1F` | count, then temperatures |
| `20` | count, balance bitmap (ceil(n/8) bytes), then cell voltages (mV) |
| `3C` | control (write, 5 bytes): sleep, discharge MOS, charge MOS, MCU reset, storage mode. `00` = off, `01` = on, `FF` = unchanged |

## License

MIT
