"""Polling coordinator for LULIS BMS."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging
from typing import Any

from bleak.exc import BleakError
from bleak_retry_connector import (
    BleakClientWithServiceCache,
    establish_connection,
)

from homeassistant.components import bluetooth
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CHAR_RX,
    CHAR_TX,
    CMD_CELLS,
    CMD_CYCLES,
    CMD_MODEL,
    CMD_PACK,
    CMD_SERIAL,
    CMD_TEMPS,
    DOMAIN,
    UPDATE_INTERVAL_S,
)
from homeassistant.exceptions import HomeAssistantError

from .protocol import FrameParser, build_control, build_read, decode

_LOGGER = logging.getLogger(__name__)

REPLY_TIMEOUT = 3.0


class LulisCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.data['address']}",
            update_interval=timedelta(seconds=UPDATE_INTERVAL_S),
        )
        self.address: str = entry.data["address"]
        self._client: BleakClientWithServiceCache | None = None
        self._parser = FrameParser()
        self._waiters: dict[int, asyncio.Future[bytes]] = {}
        self._lock = asyncio.Lock()
        self._static: dict[int, bytes] = {}

    def _on_disconnect(self, _client) -> None:
        _LOGGER.debug("%s disconnected", self.address)
        self._client = None

    def _on_notify(self, _char, data: bytearray) -> None:
        for code, payload in self._parser.feed(bytes(data)):
            fut = self._waiters.pop(code, None)
            if fut and not fut.done():
                fut.set_result(payload)

    async def _ensure_connected(self) -> BleakClientWithServiceCache:
        if self._client and self._client.is_connected:
            return self._client
        device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True
        )
        if device is None:
            raise UpdateFailed(f"{self.address} is not in range of any connectable adapter")
        client = await establish_connection(
            BleakClientWithServiceCache,
            device,
            self.address,
            disconnected_callback=self._on_disconnect,
            ble_device_callback=lambda: bluetooth.async_ble_device_from_address(
                self.hass, self.address, connectable=True
            )
            or device,
            max_attempts=3,
        )
        self._parser = FrameParser()
        await client.start_notify(CHAR_RX, self._on_notify)
        self._client = client
        return client

    async def _request(self, client, code: int) -> bytes | None:
        fut: asyncio.Future[bytes] = self.hass.loop.create_future()
        self._waiters[code] = fut
        await client.write_gatt_char(CHAR_TX, build_read(code), response=False)
        try:
            return await asyncio.wait_for(fut, REPLY_TIMEOUT)
        except TimeoutError:
            self._waiters.pop(code, None)
            return None

    async def _async_update_data(self) -> dict[str, Any]:
        async with self._lock:
            try:
                client = await self._ensure_connected()
                frames: dict[int, bytes] = dict(self._static)
                for code in (CMD_MODEL, CMD_SERIAL):
                    if code not in self._static and (p := await self._request(client, code)) is not None:
                        self._static[code] = frames[code] = p
                for code in (CMD_PACK, CMD_TEMPS, CMD_CELLS, CMD_CYCLES):
                    if (p := await self._request(client, code)) is not None:
                        frames[code] = p
            except (BleakError, TimeoutError) as err:
                await self.async_disconnect()
                raise UpdateFailed(f"BLE error: {err}") from err
            if CMD_PACK not in frames:
                await self.async_disconnect()
                raise UpdateFailed("No reply to pack status request")
            return decode(frames)

    async def async_control(self, slot: int, on: bool) -> None:
        """Send a Control (0x3C) command, then refresh state."""
        async with self._lock:
            try:
                client = await self._ensure_connected()
                fut: asyncio.Future[bytes] = self.hass.loop.create_future()
                self._waiters[0x3C] = fut
                await client.write_gatt_char(CHAR_TX, build_control(slot, on), response=False)
                try:
                    await asyncio.wait_for(fut, REPLY_TIMEOUT)
                except TimeoutError:
                    self._waiters.pop(0x3C, None)
                    _LOGGER.warning("%s: no ack for control slot %s", self.address, slot)
            except (BleakError, TimeoutError) as err:
                await self.async_disconnect()
                raise HomeAssistantError(f"BLE error: {err}") from err
        await asyncio.sleep(1)
        await self.async_request_refresh()

    async def async_disconnect(self) -> None:
        client, self._client = self._client, None
        if client:
            try:
                await client.disconnect()
            except BleakError:
                pass
