from __future__ import annotations
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import (
    DOMAIN, CONF_TOKEN, CONF_DEVICE_ID, CONF_MODULE_IDX, CONF_MODEL_ID,
    DEFAULT_MODULE_IDX, DEFAULT_MODEL_ID
)

STEP_USER_SCHEMA = vol.Schema({
    vol.Required(CONF_TOKEN): str,
    vol.Required(CONF_DEVICE_ID): str,
    vol.Optional(CONF_MODULE_IDX, default=DEFAULT_MODULE_IDX): int,
    vol.Optional(CONF_MODEL_ID, default=DEFAULT_MODEL_ID): str,
})

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None) -> FlowResult:
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=STEP_USER_SCHEMA)

        # Basic uniqueness: one config entry per device_id
        await self.async_set_unique_id(user_input[CONF_DEVICE_ID])
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=f"Instant Pot ({user_input[CONF_DEVICE_ID]})",
            data=user_input
        )

async def async_get_options_flow(config_entry):
    return OptionsFlow(config_entry)

class OptionsFlow(config_entries.OptionsFlow):
    def __init__(self, entry):
        self.config_entry = entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        data = self.config_entry.data
        schema = vol.Schema({
            vol.Required(CONF_TOKEN, default=data.get(CONF_TOKEN)): str,
            vol.Required(CONF_DEVICE_ID, default=data.get(CONF_DEVICE_ID)): str,
            vol.Optional(CONF_MODULE_IDX, default=data.get(CONF_MODULE_IDX, DEFAULT_MODULE_IDX)): int,
            vol.Optional(CONF_MODEL_ID, default=data.get(CONF_MODEL_ID, DEFAULT_MODEL_ID)): str,
        })
        return self.async_show_form(step_id="init", data_schema=schema)
