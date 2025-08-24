from __future__ import annotations
import voluptuous as vol
import logging
from datetime import timedelta

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers import aiohttp_client
from homeassistant.exceptions import HomeAssistantError
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN,
    CONF_DEVICE_ID, CONF_MODULE_IDX, CONF_MODEL_ID,
    CONF_USERNAME, CONF_PASSWORD, CONF_CLIENT_ID, CONF_REGION,
    PRESSURE_MAP, VENT_MAP,
)
from .api import KitchenOSClient, CognitoTokenManager

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list = []

async def async_get_options_flow(config_entry: ConfigEntry):
    """Return the options flow handler."""
    from .config_flow import OptionsFlowHandler
    return OptionsFlowHandler(config_entry)

SERVICE_CANCEL = "cancel"
SERVICE_START_KEEP_WARM = "start_keep_warm"
SERVICE_UPDATE_KEEP_WARM = "update_keep_warm"
SERVICE_START_PRESSURE_COOK = "start_pressure_cook"
SERVICE_UPDATE_PRESSURE_COOK = "update_pressure_cook"


def _duration_to_seconds(v) -> int | None:
    """Support HA duration selector (dict) or string or seconds int."""
    if v is None:
        return None
    # HA's duration selector typically yields dict {hours, minutes, seconds}
    if isinstance(v, dict):
        h = int(v.get("hours", 0) or 0)
        m = int(v.get("minutes", 0) or 0)
        s = int(v.get("seconds", 0) or 0)
        return int(timedelta(hours=h, minutes=m, seconds=s).total_seconds())
    if isinstance(v, (int, float)):
        return int(v)
    if isinstance(v, str):
        # Accept "HH:MM:SS" or "MM:SS"
        parts = [int(x) for x in v.split(":")]
        if len(parts) == 3:
            h, m, s = parts
        elif len(parts) == 2:
            h, m, s = 0, parts[0], parts[1]
        else:
            return int(v)
        return int(timedelta(hours=h, minutes=m, seconds=s).total_seconds())
    return None

SCHEMA_CANCEL = vol.Schema({}, extra=vol.ALLOW_EXTRA)

SCHEMA_START_KEEP_WARM = vol.Schema({
    vol.Optional("temp_c"): vol.All(int, vol.Range(min=25, max=95)),
    vol.Optional("preset"): vol.In(["Low", "High"]),
    vol.Optional("duration"): object,
    vol.Optional("duration_seconds"): vol.All(int, vol.Range(min=1, max=24*60*60)),
}, extra=vol.ALLOW_EXTRA)

SCHEMA_UPDATE_KEEP_WARM = vol.Schema({
    vol.Optional("temp_c"): vol.All(int, vol.Range(min=25, max=95)),
    vol.Optional("preset"): vol.In(["Low", "High"]),
    vol.Optional("duration"): object,
    vol.Optional("duration_seconds"): vol.All(int, vol.Range(min=1, max=24*60*60)),
}, extra=vol.ALLOW_EXTRA)

SCHEMA_START_PRESSURE = vol.Schema({
    vol.Optional("pressure"): vol.In(list(PRESSURE_MAP.keys())),
    vol.Optional("cook_time"): object,
    vol.Optional("cook_time_seconds"): vol.All(int, vol.Range(min=1, max=5*60*60)),
    vol.Optional("venting"): vol.In(list(VENT_MAP.keys())),
    vol.Optional("vent_time"): object,
    vol.Optional("vent_time_seconds"): vol.All(int, vol.Range(min=1, max=60*60)),
    vol.Optional("nutriboost", default=False): cv.boolean,
}, extra=vol.ALLOW_EXTRA)

SCHEMA_UPDATE_PRESSURE = vol.Schema({
    vol.Optional("pressure"): vol.In(list(PRESSURE_MAP.keys())),
    vol.Optional("cook_time"): object,
    vol.Optional("cook_time_seconds"): vol.All(int, vol.Range(min=1, max=5*60*60)),
    vol.Optional("venting"): vol.In(list(VENT_MAP.keys())),
    vol.Optional("vent_time"): object,
    vol.Optional("vent_time_seconds"): vol.All(int, vol.Range(min=1, max=60*60)),
    vol.Optional("nutriboost"): cv.boolean,
}, extra=vol.ALLOW_EXTRA)

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = aiohttp_client.async_get_clientsession(hass)

    tm = CognitoTokenManager(
        session=session,
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        client_id=entry.data[CONF_CLIENT_ID],
        region=entry.data[CONF_REGION],
    )
    client = KitchenOSClient(
        session=session,
        token_mgr=tm,
        device_id=entry.data[CONF_DEVICE_ID],
        module_idx=entry.data.get(CONF_MODULE_IDX, 0),
    )
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "client": client,
        "token_mgr": tm,
        "model_id": entry.data.get(CONF_MODEL_ID),
    }

    async def _wrap(call: ServiceCall, coro_factory):
        try:
            result = await coro_factory()
            _LOGGER.debug("Service %s succeeded: %s", call.service, result)
        except Exception as e:
            _LOGGER.exception("Service %s failed", call.service)
            # Show the real cause in UI instead of “Unknown error”
            raise HomeAssistantError(str(e)) from e

    async def _cancel(call: ServiceCall):
        await _wrap(call, lambda: client.execute("kitchenos:Command:Cancel"))

    async def _start_keep_warm(call: ServiceCall):
        data = call.data
        temp_c = data.get("temp_c")
        preset = data.get("preset")
        dur_sec = data.get("duration_seconds") or _duration_to_seconds(data.get("duration"))

        if (temp_c is None and preset is None) or (temp_c is not None and preset is not None):
            raise HomeAssistantError("Provide either 'temp_c' OR 'preset' (not both).")
        if not dur_sec:
            raise HomeAssistantError("Provide a valid 'duration'.")

        settings = []
        if temp_c is not None:
            settings.append({
                "reference_setting_id": "kitchenos:InstantBrands:TemperatureSetting",
                "value": {"type": "numeric", "value": int(temp_c), "reference_unit_id": "cckg:Celsius", "reference_value_id": None}
            })
        else:
            preset_id = "kitchenos:InstantBrands:TemperatureHigh" if preset == "High" else "kitchenos:InstantBrands:TemperatureLow"
            settings.append({
                "reference_setting_id": "kitchenos:InstantBrands:TemperatureSetting",
                "value": {"type": "nominal", "reference_value_id": preset_id, "reference_unit_id": None}
            })
        settings.append({
            "reference_setting_id": "kitchenos:InstantBrands:TimeSetting",
            "value": {"type": "numeric", "value": int(dur_sec), "reference_unit_id": "cckg:Second", "reference_value_id": None}
        })
        capability = {"reference_capability_id": "kitchenos:InstantBrands:KeepWarm", "settings": settings}
        await _wrap(call, lambda: client.execute("kitchenos:Command:Start", capability=capability))

    async def _update_keep_warm(call: ServiceCall):
        data = call.data
        temp_c = data.get("temp_c")
        preset = data.get("preset")
        dur_sec = data.get("duration_seconds") or _duration_to_seconds(data.get("duration"))

        settings = []
        if temp_c is not None and preset is not None:
            raise HomeAssistantError("Provide either 'temp_c' OR 'preset', not both.")
        if temp_c is not None:
            settings.append({
                "reference_setting_id": "kitchenos:InstantBrands:TemperatureSetting",
                "value": {"type": "numeric", "value": int(temp_c), "reference_unit_id": "cckg:Celsius", "reference_value_id": None}
            })
        elif preset is not None:
            preset_id = "kitchenos:InstantBrands:TemperatureHigh" if preset == "High" else "kitchenos:InstantBrands:TemperatureLow"
            settings.append({
                "reference_setting_id": "kitchenos:InstantBrands:TemperatureSetting",
                "value": {"type": "nominal", "reference_value_id": preset_id, "reference_unit_id": None}
            })
        if dur_sec:
            settings.append({
                "reference_setting_id": "kitchenos:InstantBrands:TimeSetting",
                "value": {"type": "numeric", "value": int(dur_sec), "reference_unit_id": "cckg:Second", "reference_value_id": None}
            })
        if not settings:
            raise HomeAssistantError("Provide at least one of temp_c/preset/duration.")
        capability = {"reference_capability_id": "kitchenos:InstantBrands:KeepWarm", "settings": settings}
        await _wrap(call, lambda: client.execute("kitchenos:Command:Update", capability=capability))

    async def _start_pressure(call: ServiceCall):
        data = call.data
        cook_sec = data.get("cook_time_seconds") or _duration_to_seconds(data.get("cook_time"))
        vent_sec = data.get("vent_time_seconds") or _duration_to_seconds(data.get("vent_time"))
        pressure = data.get("pressure")
        venting = data.get("venting", "Natural")
        nutriboost = bool(data.get("nutriboost", False))

        if pressure not in PRESSURE_MAP:
            raise HomeAssistantError("Select a valid 'pressure' level.")
        if not cook_sec:
            raise HomeAssistantError("Provide a valid 'cook_time'.")

        settings = [
            {
                "reference_setting_id": "kitchenos:InstantBrands:PressureSetting",
                "value": {"type": "nominal", "reference_value_id": PRESSURE_MAP[pressure], "reference_unit_id": None}
            },
            {
                "reference_setting_id": "kitchenos:InstantBrands:TimeSetting",
                "value": {"type": "numeric", "value": int(cook_sec), "reference_unit_id": "cckg:Second", "reference_value_id": None}
            },
            {
                "reference_setting_id": "kitchenos:InstantBrands:VentingSetting",
                "value": {"type": "nominal", "reference_value_id": VENT_MAP.get(venting, VENT_MAP["Natural"]), "reference_unit_id": None}
            },
            {
                "reference_setting_id": "kitchenos:InstantBrands:NutriBoostSetting",
                "value": {"type": "boolean", "value": nutriboost, "reference_unit_id": None, "reference_value_id": None}
            }
        ]
        if vent_sec:
            settings.append({
                "reference_setting_id": "kitchenos:InstantBrands:VentingTimeSetting",
                "value": {"type": "numeric", "value": int(vent_sec), "reference_unit_id": "cckg:Second", "reference_value_id": None}
            })

        capability = {"reference_capability_id": "kitchenos:InstantBrands:PressureCook", "settings": settings}
        await _wrap(call, lambda: client.execute("kitchenos:Command:Start", capability=capability))

    async def _update_pressure(call: ServiceCall):
        data = call.data
        cook_sec = data.get("cook_time_seconds") or _duration_to_seconds(data.get("cook_time"))
        vent_sec = data.get("vent_time_seconds") or _duration_to_seconds(data.get("vent_time"))

        settings = []
        if "pressure" in data and data["pressure"] in PRESSURE_MAP:
            settings.append({
                "reference_setting_id": "kitchenos:InstantBrands:PressureSetting",
                "value": {"type": "nominal", "reference_value_id": PRESSURE_MAP[data["pressure"]], "reference_unit_id": None}
            })
        if cook_sec:
            settings.append({
                "reference_setting_id": "kitchenos:InstantBrands:TimeSetting",
                "value": {"type": "numeric", "value": int(cook_sec), "reference_unit_id": "cckg:Second", "reference_value_id": None}
            })
        if "venting" in data and data["venting"] in VENT_MAP:
            settings.append({
                "reference_setting_id": "kitchenos:InstantBrands:VentingSetting",
                "value": {"type": "nominal", "reference_value_id": VENT_MAP[data["venting"]], "reference_unit_id": None}
            })
        if vent_sec:
            settings.append({
                "reference_setting_id": "kitchenos:InstantBrands:VentingTimeSetting",
                "value": {"type": "numeric", "value": int(vent_sec), "reference_unit_id": "cckg:Second", "reference_value_id": None}
            })
        if "nutriboost" in data:
            settings.append({
                "reference_setting_id": "kitchenos:InstantBrands:NutriBoostSetting",
                "value": {"type": "boolean", "value": bool(data["nutriboost"]), "reference_unit_id": None, "reference_value_id": None}
            })
        if not settings:
            raise HomeAssistantError("Provide at least one setting to update.")

        capability = {"reference_capability_id": "kitchenos:InstantBrands:PressureCook", "settings": settings}
        await _wrap(call, lambda: client.execute("kitchenos:Command:Update", capability=capability))

    hass.services.async_register(DOMAIN, SERVICE_CANCEL, _cancel, schema=SCHEMA_CANCEL)
    hass.services.async_register(DOMAIN, SERVICE_START_KEEP_WARM, _start_keep_warm, schema=SCHEMA_START_KEEP_WARM)
    hass.services.async_register(DOMAIN, SERVICE_UPDATE_KEEP_WARM, _update_keep_warm, schema=SCHEMA_UPDATE_KEEP_WARM)
    hass.services.async_register(DOMAIN, SERVICE_START_PRESSURE_COOK, _start_pressure, schema=SCHEMA_START_PRESSURE)
    hass.services.async_register(DOMAIN, SERVICE_UPDATE_PRESSURE_COOK, _update_pressure, schema=SCHEMA_UPDATE_PRESSURE)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data[DOMAIN].pop(entry.entry_id, None)
    return True

