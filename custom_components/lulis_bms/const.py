"""Constants for the LULIS Battery BMS integration."""

DOMAIN = "lulis_bms"

# Telink SPP characteristics exposed by the LK86xx BLE module
CHAR_RX = "00010203-0405-0607-0809-0a0b0c0dffe1"  # notify: module -> host
CHAR_TX = "00010203-0405-0607-0809-0a0b0c0dffe2"  # write:  host -> module

NAME_PREFIX = "LK86"
UPDATE_INTERVAL_S = 30
REPLY_TIMEOUT_S = 3.0
