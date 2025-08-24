from __future__ import annotations
import voluptuous as vol
import logging

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers import aiohttp_client
from homeassistant.exceptions import HomeAssistantError
import homeassistant.helpers.config_validation as cv

from .const import (
    DOMAIN, CONF_TOKEN, CONF_DEVICE_ID, CONF_MODULE_IDX, CONF_MODEL_ID,
    PRESSURE_MAP, VENT_MAP
)
from .api import KitchenOSClient

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list = []

SERVICE_CANCEL = "cancel"
SERVICE_START_KEEP_WARM = "start_keep_warm"
SERVICE_UPDATE_KEEP_WARM = "update_keep_warm"
SERVICE_START_PRESSURE_COOK = "start_pressure_cook"
SERVICE_UPDATE_PRESSURE_COOK = "update_pressure_cook"

SCHEMA_CANCEL = vol.Schema({})

SCHEMA_START_KEEP_WARM = vol.Schema({
    vol.Exclusive("temp_c", "temp", msg="Provide either temp_c or preset"): vol.All(int, vol.Range(min=25, max=95)),
    vol.Exclusive("preset", "temp", msg="Provide either temp_c or preset"): vol.In(["Low", "High"]),
    vol.Required("duration_seconds"): vol.All(int, vol.Range(min=1, max=24*60*60)),
})

SCHEMA_UPDATE_KEEP_WARM = vol.Schema({
    vol.Exclusive("temp_c", "temp"): vol.All(int, vol.Range(min=25, max=95)),
    vol.Exclusive("preset", "temp"): vol.In(["Low", "High"]),
    vol.Optional("duration_seconds"): vol.All(int, vol.Range(min=1, max=24*60*60)),
})

SCHEMA_START_PRESSURE = vol.Schema({
    vol.Required("pressure"): vol.In(list(PRESSURE_MAP.keys())),
    vol.Required("cook_time_seconds"): vol.All(int, vol.Range(min=1, max=5*60*60)),
    vol.Optional("venting", default="Natural"): vol.In(list(VENT_MAP.keys())),
    vol.Optional("vent_time_seconds"): vol.All(int, vol.Range(min=1, max=60*60)),
    vol.Optional("nutriboost", default=False): cv.boolean,
})

SCHEMA_UPDATE_PRESSURE = vol.Schema({
    vol.Optional("pressure"): vol.In(list(PRESSURE_MAP.keys())),
    vol.Optional("cook_time_seconds"): vol.All(int, vol.Range(min=1, max=5*60*60)),
    vol.Optional("venting"): vol.In(list(VENT_MAP.keys())),
    vol.Optional("vent_time_seconds"): vol.All(int, vol.Range(min=1, max=60*60)),
    vol.Optional("nutriboost"): cv.boolean,
})

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    session = aiohttp_client.async_get_clientsession(hass)

    client = KitchenOSClient(
        session=session,
        access_token=entry.data[CONF_TOKEN],
        device_id=entry.data[CONF_DEVICE_ID],
        module_idx=entry.data.get(CONF_MODULE_IDX, 0),
    )
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "client": client,
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
        settings = []
        if "temp_c" in data:
            settings.append({
                "reference_setting_id": "kitchenos:InstantBrands:TemperatureSetting",
                "value": {"type": "numeric", "value": data["temp_c"], "reference_unit_id": "cckg:Celsius", "reference_value_id": None}
            })
        else:
            preset_id = "kitchenos:InstantBrands:TemperatureHigh" if data["preset"] == "High" else "kitchenos:InstantBrands:TemperatureLow"
            settings.append({
                "reference_setting_id": "kitchenos:InstantBrands:TemperatureSetting",
                "value": {"type": "nominal", "reference_value_id": preset_id, "reference_unit_id": None}
            })
        settings.append({
            "reference_setting_id": "kitchenos:InstantBrands:TimeSetting",
            "value": {"type": "numeric", "value": data["duration_seconds"], "reference_unit_id": "cckg:Second", "reference_value_id": None}
        })
        capability = {"reference_capability_id": "kitchenos:InstantBrands:KeepWarm", "settings": settings}
        await _wrap(call, lambda: client.execute("kitchenos:Command:Start", capability=capability))

    async def _update_keep_warm(call: ServiceCall):
        data = call.data
        settings = []
        if "temp_c" in data:
            settings.append({
                "reference_setting_id": "kitchenos:InstantBrands:TemperatureSetting",
                "value": {"type": "numeric", "value": data["temp_c"], "reference_unit_id": "cckg:Celsius", "reference_value_id": None}
            })
        elif "preset" in data:
            preset_id = "kitchenos:InstantBrands:TemperatureHigh" if data["preset"] == "High" else "kitchenos:InstantBrands:TemperatureLow"
            settings.append({
                "reference_setting_id": "kitchenos:InstantBrands:TemperatureSetting",
                "value": {"type": "nominal", "reference_value_id": preset_id, "reference_unit_id": None}
            })
        if "duration_seconds" in data:
            settings.append({
                "reference_setting_id": "kitchenos:InstantBrands:TimeSetting",
                "value": {"type": "numeric", "value": data["duration_seconds"], "reference_unit_id": "cckg:Second", "reference_value_id": None}
            })
        if not settings:
            raise HomeAssistantError("Provide at least one of temp_c/preset/duration_seconds.")
        capability = {"reference_capability_id": "kitchenos:InstantBrands:KeepWarm", "settings": settings}
        await _wrap(call, lambda: client.execute("kitchenos:Command:Update", capability=capability))

    async def _start_pressure(call: ServiceCall):
        data = call.data
        settings = [
            {
                "reference_setting_id": "kitchenos:InstantBrands:PressureSetting",
                "value": {"type": "nominal", "reference_value_id": PRESSURE_MAP[data["pressure"]], "reference_unit_id": None}
            },
            {
                "reference_setting_id": "kitchenos:InstantBrands:TimeSetting",
                "value": {"type": "numeric", "value": data["cook_time_seconds"], "reference_unit_id": "cckg:Second", "reference_value_id": None}
            },
            {
                "reference_setting_id": "kitchenos:InstantBrands:VentingSetting",
                "value": {"type": "nominal", "reference_value_id": VENT_MAP.get(data.get("venting","Natural")), "reference_unit_id": None}
            },
            {
                "reference_setting_id": "kitchenos:InstantBrands:NutriBoostSetting",
                "value": {"type": "boolean", "value": bool(data.get("nutriboost", False)), "reference_unit_id": None, "reference_value_id": None}
            }
        ]
        if "vent_time_seconds" in data:
            settings.append({
                "reference_setting_id": "kitchenos:InstantBrands:VentingTimeSetting",
                "value": {"type": "numeric", "value": data["vent_time_seconds"], "reference_unit_id": "cckg:Second", "reference_value_id": None}
            })
        capability = {"reference_capability_id": "kitchenos:InstantBrands:PressureCook", "settings": settings}
        await _wrap(call, lambda: client.execute("kitchenos:Command:Start", capability=capability))

    async def _update_pressure(call: ServiceCall):
        data = call.data
        settings = []
        if "pressure" in data:
            settings.append({
                "reference_setting_id": "kitchenos:InstantBrands:PressureSetting",
                "value": {"type": "nominal", "reference_value_id": PRESSURE_MAP[data["pressure"]], "reference_unit_id": None}
            })
        if "cook_time_seconds" in data:
            settings.append({
                "reference_setting_id": "kitchenos:InstantBrands:TimeSetting",
                "value": {"type": "numeric", "value": data["cook_time_seconds"], "reference_unit_id": "cckg:Second", "reference_value_id": None}
            })
        if "venting" in data:
            settings.append({
                "reference_setting_id": "kitchenos:InstantBrands:VentingSetting",
                "value": {"type": "nominal", "reference_value_id": VENT_MAP[data["venting"]], "reference_unit_id": None}
            })
        if "vent_time_seconds" in data:
            settings.append({
                "reference_setting_id": "kitchenos:InstantBrands:VentingTimeSetting",
                "value": {"type": "numeric", "value": data["vent_time_seconds"], "reference_unit_id": "cckg:Second", "reference_value_id": None}
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

    hass.services.async_register(DOMAIN, SERVICE_CANCEL, _cancel)
    hass.services.async_register(DOMAIN, SERVICE_START_KEEP_WARM, _start_keep_warm)
    hass.services.async_register(DOMAIN, SERVICE_UPDATE_KEEP_WARM, _update_keep_warm)
    hass.services.async_register(DOMAIN, SERVICE_START_PRESSURE_COOK, _start_pressure)
    hass.services.async_register(DOMAIN, SERVICE_UPDATE_PRESSURE_COOK, _update_pressure)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data[DOMAIN].pop(entry.entry_id, None)
    return True

