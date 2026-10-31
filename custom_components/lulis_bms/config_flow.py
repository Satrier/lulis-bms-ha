"""Config and options flow for LULIS BMS."""

from __future__ import annotations

from typing import Any

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import CONF_ADDRESS, CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers import selector
import voluptuous as vol

from .const import (
    CONF_INVERT_CURRENT,
    CONF_KEEP_CONNECTED,
    CONF_SCAN_INTERVAL,
    DEFAULT_KEEP_CONNECTED,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL_DISCONNECTED,
    NAME_PREFIX,
)


def device_name(ble_name: str | None, address: str) -> str:
    """'LK8625-C4A386' -> 'LULIS C4A386'."""
    suffix = (ble_name or "").rsplit("-", 1)[-1] or address.replace(":", "")[-6:]
    return f"LULIS {suffix}"


class LulisConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._discovery: BluetoothServiceInfoBleak | None = None
        self._found: dict[str, str] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> LulisOptionsFlow:
        return LulisOptionsFlow()

    async def async_step_bluetooth(self, discovery_info: BluetoothServiceInfoBleak) -> ConfigFlowResult:
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._discovery = discovery_info
        self.context["title_placeholders"] = {"name": discovery_info.name}
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        assert self._discovery
        if user_input is not None:
            return self._create(self._discovery.address, self._discovery.name)
        self._set_confirm_only()
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={"name": self._discovery.name},
        )

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self._create(address, self._found.get(address))

        current = self._async_current_ids(include_ignore=False)
        for info in async_discovered_service_info(self.hass, connectable=True):
            if (info.name or "").startswith(NAME_PREFIX) and info.address not in current:
                self._found[info.address] = info.name
        if not self._found:
            return self.async_abort(reason="no_devices_found")
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {vol.Required(CONF_ADDRESS): vol.In({a: f"{n} ({a})" for a, n in self._found.items()})}
            ),
        )

    def _create(self, address: str, ble_name: str | None) -> ConfigFlowResult:
        name = device_name(ble_name, address)
        return self.async_create_entry(title=name, data={CONF_ADDRESS: address, CONF_NAME: name})


class LulisOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input[CONF_KEEP_CONNECTED] and user_input[CONF_SCAN_INTERVAL] < MIN_SCAN_INTERVAL_DISCONNECTED:
                errors[CONF_SCAN_INTERVAL] = "interval_too_short"
            else:
                return self.async_create_entry(data=user_input)

        opts = {**self.config_entry.options, **(user_input or {})}
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_KEEP_CONNECTED, default=opts.get(CONF_KEEP_CONNECTED, DEFAULT_KEEP_CONNECTED)
                ): selector.BooleanSelector(),
                vol.Required(
                    CONF_SCAN_INTERVAL, default=opts.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=MIN_SCAN_INTERVAL,
                        max=MAX_SCAN_INTERVAL,
                        step=5,
                        unit_of_measurement="s",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Required(
                    CONF_INVERT_CURRENT, default=opts.get(CONF_INVERT_CURRENT, False)
                ): selector.BooleanSelector(),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
