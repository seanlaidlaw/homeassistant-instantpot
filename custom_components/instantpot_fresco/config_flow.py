from __future__ import annotations
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import aiohttp_client
import logging

from .const import (
    DOMAIN,
    CONF_USERNAME, CONF_PASSWORD, CONF_CLIENT_ID, CONF_REGION,
    CONF_DEVICE_ID, CONF_MODULE_IDX, CONF_MODEL_ID,
    DEFAULT_REGION, DEFAULT_MODULE_IDX, DEFAULT_MODEL_ID,
)
from .api import CognitoTokenManager, KitchenOSClient

_LOGGER = logging.getLogger(__name__)

# Step 1 schema: credentials (no device yet)
STEP_CREDS_SCHEMA = vol.Schema({
    vol.Required(CONF_USERNAME): str,
    vol.Required(CONF_PASSWORD): str,
    vol.Required(CONF_CLIENT_ID): str,  # e.g., 5qucjsjb9i1ahnddonctmp9hba
    vol.Optional(CONF_REGION, default=DEFAULT_REGION): str,  # "us-east-2"
    vol.Optional(CONF_MODULE_IDX, default=DEFAULT_MODULE_IDX): int,
    vol.Optional(CONF_MODEL_ID, default=DEFAULT_MODEL_ID): str,
})

class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for Instant Pot (Fresco Cloud)."""
    VERSION = 3

    def __init__(self) -> None:
        """Initialize the config flow."""
        super().__init__()
        self._creds: dict | None = None
        self._devices: list[tuple[str, str]] = []

    async def async_step_init(self, user_input=None) -> FlowResult:
        """Initialize the config flow."""
        return await self.async_step_user(user_input)

    async def async_step_user(self, user_input=None) -> FlowResult:
        """Collect login creds → login to Cognito → fetch /user/ → pick device."""
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=STEP_CREDS_SCHEMA)

        self._creds = user_input

        # 1) Login to Cognito
        session = aiohttp_client.async_get_clientsession(self.hass)
        tm = CognitoTokenManager(
            session=session,
            username=user_input[CONF_USERNAME],
            password=user_input[CONF_PASSWORD],
            client_id=user_input[CONF_CLIENT_ID],
            region=user_input.get(CONF_REGION, DEFAULT_REGION),
        )
        try:
            await tm.login()
        except Exception as e:
            # Re-open same step with an auth error
            return self.async_show_form(
                step_id="user",
                data_schema=STEP_CREDS_SCHEMA,
                errors={"base": "auth_failed"},
                description_placeholders={"error": str(e)[:120]},
            )

        # 2) Fetch /user/ to discover devices
        client = KitchenOSClient(
            session=session,
            token_mgr=tm,
            device_id="placeholder",
            module_idx=user_input.get(CONF_MODULE_IDX, DEFAULT_MODULE_IDX),
        )
        try:
            profile = await client.get_user_profile()
        except Exception as e:
            _LOGGER.exception("Fetching /user/ failed: %s", e)
            return self.async_show_form(
                step_id="user",
                data_schema=STEP_CREDS_SCHEMA,
                errors={"base": "cannot_fetch_user"},
                description_placeholders={"error": str(e)[:120]},
            )

        devices = []
        for d in (profile.get("devices") or []):
            dev_id = d.get("device_id")
            app = d.get("appliance") or {}
            label = f'{dev_id} — {app.get("name","Appliance")} ({app.get("id","")})' if dev_id else None
            if dev_id and label:
                devices.append((dev_id, label))

        if not devices:
            return self.async_abort(reason="no_devices_found")

        if len(devices) == 1:
            # Single device → create entry immediately
            dev_id = devices[0][0]
            await self.async_set_unique_id(dev_id)
            self._abort_if_unique_id_configured()
            data = {**self._creds, CONF_DEVICE_ID: dev_id}
            return self.async_create_entry(title=f"Instant Pot ({dev_id})", data=data)

        # Multiple devices → store list and go to picker step
        self._devices = devices
        return await self.async_step_pick_device()

    async def async_step_pick_device(self, user_input=None) -> FlowResult:
        """Let user choose a device if multiple are found."""
        if not self._devices:
            return self.async_abort(reason="no_devices_found")
            
        device_map = {dev_id: label for dev_id, label in self._devices}
        schema = vol.Schema({
            vol.Required(CONF_DEVICE_ID): vol.In(device_map)
        })

        if user_input is None:
            return self.async_show_form(step_id="pick_device", data_schema=schema)

        dev_id = user_input[CONF_DEVICE_ID]
        await self.async_set_unique_id(dev_id)
        self._abort_if_unique_id_configured()

        data = {**self._creds, CONF_DEVICE_ID: dev_id}
        return self.async_create_entry(title=f"Instant Pot ({dev_id})", data=data)


class OptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options flow for Instant Pot Fresco integration."""
    
    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self.config_entry = entry

    async def async_step_init(self, user_input=None):
        data = self.config_entry.data
        schema = vol.Schema({
            vol.Required(CONF_USERNAME, default=data.get(CONF_USERNAME, "")): str,
            vol.Required(CONF_PASSWORD, default=data.get(CONF_PASSWORD, "")): str,
            vol.Required(CONF_CLIENT_ID, default=data.get(CONF_CLIENT_ID, "")): str,
            vol.Optional(CONF_REGION, default=data.get(CONF_REGION, DEFAULT_REGION)): str,
            vol.Required(CONF_DEVICE_ID, default=data.get(CONF_DEVICE_ID, "")): str,
            vol.Optional(CONF_MODULE_IDX, default=data.get(CONF_MODULE_IDX, DEFAULT_MODULE_IDX)): int,
            vol.Optional(CONF_MODEL_ID, default=data.get(CONF_MODEL_ID, DEFAULT_MODEL_ID)): str,
        })
        if user_input is not None:
            new = {**data, **user_input}
            self.hass.config_entries.async_update_entry(self.config_entry, data=new)
            return self.async_create_entry(title="", data={})
        return self.async_show_form(step_id="init", data_schema=schema)
