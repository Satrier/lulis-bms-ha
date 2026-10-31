# LULIS Battery BMS for Home Assistant

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://hacs.xyz/docs/faq/custom_repositories)
[![GitHub Release](https://img.shields.io/github/v/release/Satrier/lulis-bms-ha)](https://github.com/Satrier/lulis-bms-ha/releases)
[![Validate](https://github.com/Satrier/lulis-bms-ha/actions/workflows/validate.yml/badge.svg)](https://github.com/Satrier/lulis-bms-ha/actions/workflows/validate.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Monitor and control **LULIS lithium batteries** (e-motorcycle, golf cart and energy storage packs) from Home Assistant over Bluetooth. You don't need the phone app, the cloud or any extra hardware.

These batteries use a BMS with an **LK86xx (Telink) Bluetooth module** (BLE name `LK86xx-XXXXXX`), the same one the *LULIS BATTERY* app talks to. The integration uses Home Assistant's own Bluetooth stack, so it works with local adapters and with [ESPHome Bluetooth proxies](https://esphome.io/projects/?type=bluetooth).

## Install

[![Open your Home Assistant instance and open this repository inside HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=Satrier&repository=lulis-bms-ha&category=integration)

1. Click the button above, or in **HACS → ⋮ → Custom repositories** add `https://github.com/Satrier/lulis-bms-ha` with the category **Integration**.
2. **Download** LULIS Battery BMS and restart Home Assistant.
3. Close the LULIS BATTERY app on your phone. The BMS accepts only one Bluetooth connection.
4. The battery appears under **Settings → Devices & services → Discovered**. Click **Add**. If it doesn't appear:

[![Open your Home Assistant instance and start setting up LULIS Battery BMS.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=lulis_bms)

<details>
<summary>Manual install</summary>

Download `lulis_bms.zip` from the [latest release](https://github.com/Satrier/lulis-bms-ha/releases/latest), extract it to `<config>/custom_components/lulis_bms/` and restart Home Assistant.
</details>

## Features

- 🔍 **Auto-discovery** of `LK86*` batteries, set up in one click
- 🔋 **Pack**: voltage, current, power, state of charge, remaining Ah
- 🧮 **Cells**: voltage of every cell, plus min, max and delta
- 🌡️ **Temperatures**: T1, T2 and MOS
- ⚡ **Energy dashboard**: *Energy charged* / *Energy discharged* in kWh, kept across restarts
- 🎛️ **Control**: *Charging* and *Discharging* switches (charge/discharge MOS)
- 🩺 **Health**: state of health, cycles, design capacity, raw status flags
- 🧾 **Diagnostics** download with raw BMS frames, for bug reports
- 🌍 English and Ukrainian translations

> ⚠️ Turning **Discharging** off cuts power to the load immediately.

## Supported batteries

| Battery | BMS | BLE name | Status |
|---|---|---|---|
| LULIS 72V 40Ah LiFePO4 (24S) | `LR359V13_N031x60A` | `LK8625-…` | ✅ tested |

Other LULIS packs with an `LK86xx` module will most likely work. If yours does too (or doesn't), please [open an issue](https://github.com/Satrier/lulis-bms-ha/issues/new/choose).

## Energy dashboard

**Settings → Dashboards → Energy → Battery storage → Add battery system**:
- *Energy going in to the battery*: `sensor.lulis_battery_energy_charged`
- *Energy going out of the battery*: `sensor.lulis_battery_energy_discharged`

## Troubleshooting

| Symptom | Fix |
|---|---|
| Entities are *Unavailable* | Close the phone app: only one BLE connection is allowed. Check **Settings → Bluetooth** to see whether an adapter actually hears the battery. |
| Frequent drop-outs | The signal is too weak (below about -85 dBm). Put an [ESPHome Bluetooth proxy](https://esphome.io/projects/?type=bluetooth) (ESP32, ~$5) near the battery. |
| Phone app can't connect | Disable the integration entry while you use the app. |
| Wrong or odd values | Attach **Download diagnostics** (device page → ⋮) to an issue. |

Debug logging:

```yaml
logger:
  logs:
    custom_components.lulis_bms: debug
```

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

## Development

```bash
pip install ruff pytest
ruff check . && ruff format --check . && pytest
```

To release, push a tag (`git tag v0.2.0 && git push --tags`). GitHub Actions sets the manifest version, builds `lulis_bms.zip` and publishes the release that HACS installs.

## Credits

Inspired by [batmon-ha](https://github.com/fl4p/batmon-ha) and [BMS_BLE-HA](https://github.com/patman15/BMS_BLE-HA).

## License

[MIT](LICENSE)
