"""Constants for LULIS BMS."""

DOMAIN = "lulis_bms"

# Telink SPP characteristics used by the LK86xx BLE module
CHAR_RX = "00010203-0405-0607-0809-0a0b0c0dffe1"  # notify: module -> host
CHAR_TX = "00010203-0405-0607-0809-0a0b0c0dffe2"  # write:  host -> module

NAME_PREFIX = "LK86"
UPDATE_INTERVAL_S = 30

# Read command codes (from LULIS BATTERY app 1.0.6)
CMD_MODEL = 0x02  # BMS model string
CMD_SERIAL = 0x05  # serial number string
CMD_PACK = 0x1E  # pack: voltage, current, SOC, SOH, min/max cell, status
CMD_TEMPS = 0x1F  # temperature sensors
CMD_CELLS = 0x20  # cell voltages + balance bits
CMD_CYCLES = 0x09  # design cycles, cycles, capacities
