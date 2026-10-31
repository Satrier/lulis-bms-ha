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

from .const import CHAR_RX, CHAR_TX, DOMAIN, REPLY_TIMEOUT_S, UPDATE_INTERVAL_S
from .protocol import (
    CMD_CONTROL,
    CMD_PACK,
    POLL_COMMANDS,
    STATIC_COMMANDS,
    FrameParser,
    build_control,
    build_read,
    decode,
)

_LOGGER = logging.getLogger(__name__)


class LulisCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Keeps one BLE connection open and polls the BMS."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.data[CONF_ADDRESS]}",
            update_interval=timedelta(seconds=UPDATE_INTERVAL_S),
        )
        self.address: str = entry.data[CONF_ADDRESS]
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
        if CMD_PACK not in frames:
            await self.async_disconnect()
            raise UpdateFailed("No reply to pack status request")
        self.last_frames = frames
        data = decode(frames)
        self._update_device_info(data)
        return data

    def _update_device_info(self, data: dict[str, Any]) -> None:
        if self._device_info_set or "model" not in data:
            return
        registry = dr.async_get(self.hass)
        if device := registry.async_get_device(identifiers={(DOMAIN, self.address)}):
            registry.async_update_device(device.id, model=data.get("model"), serial_number=data.get("serial"))
            self._device_info_set = True

    # --- control ------------------------------------------------------------

    async def async_control(self, slot: int, on: bool) -> None:
        """Send a Control (0x3C) command, then refresh state."""
        async with self._lock:
            try:
                client = await self._ensure_connected()
                if await self._transact(client, CMD_CONTROL, build_control(slot, on)) is None:
                    _LOGGER.warning("%s: no ack for control slot %s", self.address, slot)
            except (BleakError, TimeoutError, UpdateFailed) as err:
                await self.async_disconnect()
                raise HomeAssistantError(f"Battery not reachable: {err}") from err
        await asyncio.sleep(1)
        await self.async_request_refresh()

    async def async_disconnect(self) -> None:
        client, self._client = self._client, None
        if client:
            with contextlib.suppress(BleakError):
                await client.disconnect()
