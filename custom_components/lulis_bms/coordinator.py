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
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
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
        async with self._lock:
            try:
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

    async def async_control(self, slot: int, on: bool, refresh: bool = True) -> None:
        """Send a Control (0x3C) command, check the ack, then refresh state."""
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
            raise HomeAssistantError("The battery did not answer the command")
        if not write_accepted(flag, ack):
            _LOGGER.warning("%s rejected control %s (flag=%s payload=%s)", self.address, frame.hex(), flag, ack.hex())
            raise HomeAssistantError(f"The BMS rejected the command (flag={flag}, reply={ack.hex()})")
        if refresh:
            await asyncio.sleep(1)
            await self.async_refresh()

    async def async_disconnect(self) -> None:
        client, self._client = self._client, None
        if client:
            with contextlib.suppress(BleakError):
                await client.disconnect()
