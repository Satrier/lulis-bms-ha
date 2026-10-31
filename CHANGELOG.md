# Changelog

## 0.2.2

- Fix: all entities were unavailable in 0.2.1 because of a wrong device-registry call (`async_get_device_by_identifier` needs the config entry id in HA 2026.10). Updating the device model/serial can no longer break polling.

## 0.2.1

- Charging / Discharging switches now check the BMS reply. If the BMS rejects the command, or accepts it but keeps the MOS state, an error is shown in the UI and the reply is logged, instead of the switch silently flipping back.
- Use `async_get_device_by_identifier` (the old device registry call is deprecated in HA 2026.x).

## 0.2.0

- **Options**: keep connected vs connect-per-poll (frees the BMS for the phone app between polls), polling interval 10–300 s, invert current.
- **Alarm** and **Protection** enum sensors with decoded BMS reasons (from the app's own labels) and a **Problem** binary sensor.
- **Restart BMS** button (MCU reset, disabled by default).
- Protection thresholds are read on demand into **Download diagnostics** (read-only).
- Alerts **blueprint** and an example **dashboard**.
- New batteries are named after their BLE suffix (e.g. *LULIS C4A386*). Existing entries keep their name.
- Fix: the duplicate *MOS temperature* entity created by 0.1.0 is merged back into the original one, so history is kept.

## 0.1.0

- First release.
- Auto-discovery of LULIS batteries (`LK86*` Telink BLE module).
- Sensors: voltage, current, power, state of charge, remaining Ah, min/max/delta cell voltage, all cell voltages, temperatures (T1, T2, MOS), state of health, cycles, design capacity, status flags.
- Energy sensors for the Energy dashboard: energy charged and energy discharged (kWh).
- Charging and Discharging switches (charge/discharge MOS).
- Diagnostics download with the raw BMS frames.
- English and Ukrainian translations.
