# Changelog

## 0.5.2

- Fix: changing the options (or unloading) could fail when a Bluetooth proxy timed out on the disconnect request, leaving every entity *Unavailable* until a restart. Disconnecting now never fails and gives up after 10 s.

## 0.5.1

- Polling interval can now be up to **3600 s** (was 300 s). Without a permanent connection, polling every 15–60 minutes lets the BMS go idle between polls and reduces its self-drain (about 0.9 %/day with a permanent connection on the tested pack). See *Reducing self-drain* in the README.
- Energy counters keep integrating across long polling intervals (the gap limit is now 2.5 × the interval, at least 5 min).

## 0.5.0

- **Sleep controls removed.** Measurements on the output terminals showed that the pack can't be put to sleep over Bluetooth: the status bit used by 0.4.0 (*Discharge MOS*) goes off and on while the output stays at 79–80 V. *Sleep BMS*, *Wake BMS* (fresh connection) and *Asleep* from 0.4.0 are removed automatically.
- **Wake BMS** is the only control: it resets the BMS MCU, which is what really wakes a pack whose output is asleep at ~37 V. It keeps the entity id of the former *Restart BMS* button (`button.…_restart_bms`) and is no longer under *Configuration*.
- README: what is known about sleep and wake.

## 0.4.0

> Superseded by 0.5.0: the sleep detection below turned out to be wrong.

- **Sleep / wake that actually work.** Tests on a LULIS pack showed that the BMS ignores the sleep command but wakes up on every new Bluetooth connection, and falls asleep by itself a few minutes later. So:
  - **Sleep BMS** (enabled by default, no longer experimental or under *Configuration*) drops the link and stops polling until you wake the pack. The state survives restarts.
  - New **Wake BMS** button: opens a fresh connection, which wakes the pack, then resumes polling.
  - New **Asleep** binary sensor. While asleep, the other entities are *Unavailable* instead of showing stale values.
  - *Wake / restart BMS* is now **Restart BMS** (MCU reset).
- The old `button.…_sleep_bms_experimental` entity id becomes `button.…_sleep_bms`.
- Example dashboard: sleep / wake controls.

## 0.3.1

- *Restart BMS* is now **Wake / restart BMS** and enabled by default (also on existing installs). It sends the app's *Reset MCU → Open*, which wakes a sleeping pack whose output is stuck at ~37 V.
- The button no longer shows an error when the MCU resets without answering the command.
- **Sleep BMS (experimental)** button, disabled by default: sets the hidden *sleep* slot of the control command. Untested on LULIS packs; please report whether the output turns off.
- README: troubleshooting for a sleeping pack.

## 0.3.0

- **Breaking:** the *Charging* / *Discharging* switches are removed. The LULIS BMS acknowledges the control command but never changes the MOS state. They are replaced by read-only *Charge MOS* / *Discharge MOS* binary sensors, and the old switch entities are removed automatically.

## 0.2.3

- Minimum Home Assistant version is now **2026.10** (HACS won't offer the update on older versions).

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
