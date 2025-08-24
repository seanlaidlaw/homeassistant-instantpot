from __future__ import annotations
from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers import entity_platform
from homeassistant.const import STATE_UNAVAILABLE

from .const import DOMAIN, CONF_DEVICE_ID, CONF_MODEL_ID
from .api import NotificationsManager

async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][entry.entry_id]
    notif: NotificationsManager = data["notifications"]
    device_id: str = entry.data[CONF_DEVICE_ID]
    model_id: str = entry.data.get(CONF_MODEL_ID, "Instant Pot")

    entity = InstantPotStateSensor(device_id, model_id, notif)
    async_add_entities([entity])


class InstantPotStateSensor(SensorEntity):
    """Live state of the Instant Pot from notifications WS."""
    _attr_has_entity_name = True
    _attr_name = "State"
    _attr_icon = "mdi:pot-steam"

    def __init__(self, device_id: str, model_id: str, notif: NotificationsManager):
        self._device_id = device_id
        self._model_id = model_id
        self._notif = notif
        self._remove_listener = None
        self._state = None

        # unique_id makes it a stable sensor in HA
        self._attr_unique_id = f"{DOMAIN}_{device_id}_state"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            manufacturer="Instant Brands",
            model=self._model_id,
            name=f"Instant Pot ({self._device_id})",
        )

    @property
    def native_value(self):
        # Map to a friendly top-level value: Ready / Preheating / Cooking / KeepWarm / Venting …
        if not self.available:
            return None
        cap = None
        if self._state:
            cap = (self._state.get("capability") or {}).get("name")
            dev_state = self._state.get("device_state")
            # Prefer capability name if present, else device_state suffix
            if cap:
                return cap
            if dev_state:
                return dev_state.split(":")[-1]  # kitchenos:DeviceState:Running -> Running
        return None

    @property
    def extra_state_attributes(self):
        return self._state or {}

    @property
    def available(self) -> bool:
        return self._notif.is_available(self._device_id)

    async def async_added_to_hass(self):
        @callback
        def _on_update(state: dict):
            self._state = state
            self.async_write_ha_state()

        self._remove_listener = self._notif.add_listener(self._device_id, _on_update)

    async def async_will_remove_from_hass(self):
        if self._remove_listener:
            self._remove_listener()
            self._remove_listener = None
