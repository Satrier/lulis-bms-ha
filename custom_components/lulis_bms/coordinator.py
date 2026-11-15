"""BLE connection + polling coordinator for LULIS BMS."""

from __future__ import annotations

import asyncio
import contextlib
from datetime import timedelta
import logging
from typing import Any

from bleak.exc import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection
from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ADDRESS
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CHAR_RX,
    CHAR_TX,
    CONF_INVERT_CURRENT,
    CONF_KEEP_CONNECTED,
    CONF_SCAN_INTERVAL,
    DEFAULT_KEEP_CONNECTED,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    REPLY_TIMEOUT_S,
    SLEEP_ASLEEP,
    SLEEP_AWAKE,
    SLEEP_FALLING,
    WAKE_SETTLE_S,
)
from .protocol import (
    CMD_CONTROL,
    CMD_PACK,
    POLL_COMMANDS,
    STATIC_COMMANDS,
    THRESHOLDS,
    FrameParser,
    build_control,
    build_read,
    decode,
    decode_threshold,
    write_accepted,
)

_LOGGER = logging.getLogger(__name__)


class LulisCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Owns the BLE link to one battery and polls it."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        opts = entry.options
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.data[CONF_ADDRESS]}",
            update_interval=timedelta(seconds=opts.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)),
        )
        self.address: str = entry.data[CONF_ADDRESS]
        self.keep_connected: bool = opts.get(CONF_KEEP_CONNECTED, DEFAULT_KEEP_CONNECTED)
        self.invert_current: bool = opts.get(CONF_INVERT_CURRENT, False)
        self.last_frames: dict[int, bytes] = {}
        self._client: BleakClientWithServiceCache | None = None
        self._parser = FrameParser()
        self._waiters: dict[int, asyncio.Future[bytes]] = {}
        self._lock = asyncio.Lock()
        self._static: dict[int, bytes] = {}
        self._device_info_set = False
        self._interval = self.update_interval
        # Any new BLE connection wakes the BMS (discharge MOS on, 79-80 V on the output).
        # It falls asleep by itself (MOS off, ~37 V) ~6-7 min later if idle, also while
        # connected. So to sleep, HA must stop opening new connections.
        self.sleep_state = SLEEP_AWAKE
        self.auto_sleep_min = 0
        self._auto_sleep_unsub: CALLBACK_TYPE | None = None
        self._store: Store[dict[str, Any]] = Store(hass, 1, f"{DOMAIN}.{entry.entry_id}")

    @property
    def asleep(self) -> bool:
        return self.sleep_state == SLEEP_ASLEEP

    async def async_load_state(self) -> None:
        """Restore sleep state and timer, so a HA restart doesn't wake a sleeping pack."""
        stored = await self._store.async_load() or {}
        self.auto_sleep_min = int(stored.get("auto_sleep_min", 0))
        # the link is gone after a restart, so "falling asleep" ends as "asleep"
        if stored.get("asleep") or stored.get("sleep_state") in (SLEEP_ASLEEP, SLEEP_FALLING):
            self._set_state(SLEEP_ASLEEP)
        else:
            self._schedule_auto_sleep()

    async def _async_save(self) -> None:
        await self._store.async_save({"sleep_state": self.sleep_state, "auto_sleep_min": self.auto_sleep_min})

    def _set_state(self, state: str) -> None:
        self.sleep_state = state
        self.update_interval = None if state == SLEEP_ASLEEP else self._interval
        if state != SLEEP_AWAKE:
            self._cancel_auto_sleep()

    async def _async_go_asleep(self, reason: str) -> None:
        _LOGGER.debug("%s asleep: %s", self.address, reason)
        await self.async_disconnect()
        self._set_state(SLEEP_ASLEEP)
        await self._async_save()
        self.async_update_listeners()

    # --- auto sleep timer ---------------------------------------------------

    def _cancel_auto_sleep(self) -> None:
        if self._auto_sleep_unsub:
            self._auto_sleep_unsub()
            self._auto_sleep_unsub = None

    def _schedule_auto_sleep(self) -> None:
        self._cancel_auto_sleep()
        if self.sleep_state == SLEEP_AWAKE and self.auto_sleep_min > 0:
            self._auto_sleep_unsub = async_call_later(self.hass, self.auto_sleep_min * 60, self._auto_sleep_fired)

    @callback
    def _auto_sleep_fired(self, _now: Any) -> None:
        self._auto_sleep_unsub = None
        self.config_entry.async_create_background_task(self.hass, self.async_sleep(), "lulis_bms auto sleep")

    async def async_set_auto_sleep(self, minutes: int) -> None:
        """Set the auto-sleep delay (0 = off); the countdown restarts now."""
        self.auto_sleep_min = minutes
        self._schedule_auto_sleep()
        await self._async_save()
        self.async_update_listeners()

    async def async_shutdown(self) -> None:
        self._cancel_auto_sleep()
        await super().async_shutdown()

    # --- BLE plumbing -------------------------------------------------------

    def _on_disconnect(self, _client: object) -> None:
        _LOGGER.debug("%s disconnected", self.address)
        self._client = None

    def _on_notify(self, _char: object, data: bytearray) -> None:
        for cmd, payload in self._parser.feed(bytes(data)):
            if (fut := self._waiters.pop(cmd, None)) and not fut.done():
                fut.set_result(payload)

    def _ble_device(self):
        return bluetooth.async_ble_device_from_address(self.hass, self.address, connectable=True)

    async def _ensure_connected(self) -> BleakClientWithServiceCache:
        if self._client and self._client.is_connected:
            return self._client
        if (device := self._ble_device()) is None:
            raise UpdateFailed(f"{self.address} is not in range of any connectable adapter")
        client = await establish_connection(
            BleakClientWithServiceCache,
            device,
            self.address,
            disconnected_callback=self._on_disconnect,
            ble_device_callback=lambda: self._ble_device() or device,
            max_attempts=3,
        )
        self._parser = FrameParser()
        await client.start_notify(CHAR_RX, self._on_notify)
        self._client = client
        return client

    async def _transact(self, client: BleakClientWithServiceCache, cmd: int, frame: bytes) -> bytes | None:
        fut: asyncio.Future[bytes] = self.hass.loop.create_future()
        self._waiters[cmd] = fut
        await client.write_gatt_char(CHAR_TX, frame, response=False)
        try:
            return await asyncio.wait_for(fut, REPLY_TIMEOUT_S)
        except TimeoutError:
            self._waiters.pop(cmd, None)
            return None

    async def _release(self) -> None:
        """Drop the link after a transaction unless we keep it open."""
        if not self.keep_connected:
            await self.async_disconnect()

    # --- polling ------------------------------------------------------------

    async def _async_update_data(self) -> dict[str, Any]:
        if self.asleep:
            # e.g. homeassistant.update_entity: connecting would wake the pack
            return self.data or {}
        if self.sleep_state == SLEEP_FALLING and not (self._client and self._client.is_connected):
            # a new connection would wake it again: stop here, it falls asleep on its own
            await self._async_go_asleep("link lost while falling asleep")
            return self.data or {}
        async with self._lock:
            try:
                if self.sleep_state == SLEEP_FALLING:
                    if not (self._client and self._client.is_connected):  # dropped meanwhile
                        raise UpdateFailed("Link lost while falling asleep")
                    client = self._client  # never reconnect: that would wake the pack
                else:
                    client = await self._ensure_connected()
                frames: dict[int, bytes] = dict(self._static)
                for cmd in STATIC_COMMANDS:
                    if cmd not in self._static and (p := await self._transact(client, cmd, build_read(cmd))):
                        self._static[cmd] = frames[cmd] = p
                for cmd in POLL_COMMANDS:
                    if (p := await self._transact(client, cmd, build_read(cmd))) is not None:
                        frames[cmd] = p
            except (BleakError, TimeoutError) as err:
                await self.async_disconnect()
                raise UpdateFailed(f"BLE error: {err}") from err
            finally:
                await self._release()
        if CMD_PACK not in frames:
            await self.async_disconnect()
            raise UpdateFailed("No reply to pack status request")
        self.last_frames = frames
        data = decode(frames)
        if self.invert_current and "current" in data:
            data["current"] = -data["current"]
            data["power"] = -data["power"]
        self._update_device_info(data)
        if self.sleep_state == SLEEP_FALLING and data.get("discharge_mos") is False:
            await self._async_go_asleep("discharge MOS off, output ~37 V")
        return data

    def _update_device_info(self, data: dict[str, Any]) -> None:
        if self._device_info_set or "model" not in data:
            return
        self._device_info_set = True  # cosmetic: never retry, never break polling
        try:
            registry = dr.async_get(self.hass)
            for device in dr.async_entries_for_config_entry(registry, self.config_entry.entry_id):
                if (DOMAIN, self.address) in device.identifiers:
                    registry.async_update_device(device.id, model=data.get("model"), serial_number=data.get("serial"))
        except Exception:
            _LOGGER.debug("Could not update device info", exc_info=True)

    # --- diagnostics --------------------------------------------------------

    async def async_read_thresholds(self) -> dict[str, Any]:
        """Read protection thresholds (read-only, used by diagnostics)."""
        out: dict[str, Any] = {}
        async with self._lock:
            try:
                client = await self._ensure_connected()
                for cmd in THRESHOLDS:
                    payload = await self._transact(client, cmd, build_read(cmd))
                    out[f"0x{cmd:02x}"] = decode_threshold(cmd, payload) if payload is not None else None
            except (BleakError, TimeoutError, UpdateFailed) as err:
                await self.async_disconnect()
                out["error"] = str(err)
            finally:
                await self._release()
        return out

    # --- control ------------------------------------------------------------

    async def async_control(self, slot: int, on: bool, refresh: bool = True, require_ack: bool = True) -> None:
        """Send a Control (0x3C) command, check the ack, then refresh state.

        With require_ack=False a missing reply is only logged: a sleeping or
        rebooting MCU may act on the command without answering it.
        """
        frame = build_control(slot, on)
        async with self._lock:
            try:
                client = await self._ensure_connected()
                ack = await self._transact(client, CMD_CONTROL, frame)
            except (BleakError, TimeoutError, UpdateFailed) as err:
                await self.async_disconnect()
                raise HomeAssistantError(f"Battery not reachable: {err}") from err
            finally:
                await self._release()
        flag = self._parser.flags.get(CMD_CONTROL)
        _LOGGER.debug("%s control TX %s -> ack flag=%s payload=%s", self.address, frame.hex(), flag, ack and ack.hex())
        if ack is None:
            if require_ack:
                raise HomeAssistantError("The battery did not answer the command")
            _LOGGER.debug("%s no ack for control %s (expected while the MCU resets)", self.address, frame.hex())
            return
        if not write_accepted(flag, ack):
            _LOGGER.warning("%s rejected control %s (flag=%s payload=%s)", self.address, frame.hex(), flag, ack.hex())
            raise HomeAssistantError(f"The BMS rejected the command (flag={flag}, reply={ack.hex()})")
        if refresh:
            await asyncio.sleep(1)
            await self.async_refresh()

    # --- sleep / wake -------------------------------------------------------

    async def async_sleep(self) -> None:
        """Let the pack fall asleep without waking it again.

        The sleep slot of 0x3C is acked but ignored, so nothing is sent. If HA holds
        the link, it keeps polling over it (no reconnects) until the BMS turns the
        discharge MOS off, then disconnects. Without a link it just stops polling.
        """
        self._cancel_auto_sleep()
        if self.asleep:
            return
        if self._client and self._client.is_connected:
            self._set_state(SLEEP_FALLING)
            await self._async_save()
            self.async_update_listeners()
        else:
            await self._async_go_asleep("no link, stopped polling")

    async def async_wake(self) -> None:
        """Wake the pack by opening a fresh BLE connection, then resume polling."""
        self._set_state(SLEEP_AWAKE)
        await self._async_save()
        async with self._lock:
            await self.async_disconnect()  # only a *new* connection wakes the BMS
            try:
                await self._ensure_connected()
            except (BleakError, TimeoutError, UpdateFailed) as err:
                await self.async_disconnect()
                self.async_update_listeners()
                raise HomeAssistantError(f"Battery not reachable: {err}") from err
        await asyncio.sleep(WAKE_SETTLE_S)  # the discharge MOS turns on ~3 s after connecting
        await self.async_refresh()
        self._schedule_auto_sleep()

    async def async_disconnect(self) -> None:
        client, self._client = self._client, None
        if client:
            with contextlib.suppress(BleakError):
                await client.disconnect()
