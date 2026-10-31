"""Constants for the LULIS Battery BMS integration."""

DOMAIN = "lulis_bms"

# Telink SPP characteristics exposed by the LK86xx BLE module
CHAR_RX = "00010203-0405-0607-0809-0a0b0c0dffe1"  # notify: module -> host
CHAR_TX = "00010203-0405-0607-0809-0a0b0c0dffe2"  # write:  host -> module

NAME_PREFIX = "LK86"
REPLY_TIMEOUT_S = 3.0

# Options
CONF_KEEP_CONNECTED = "keep_connected"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_INVERT_CURRENT = "invert_current"

DEFAULT_KEEP_CONNECTED = True
DEFAULT_SCAN_INTERVAL = 30
MIN_SCAN_INTERVAL = 10
MIN_SCAN_INTERVAL_DISCONNECTED = 60
MAX_SCAN_INTERVAL = 300
