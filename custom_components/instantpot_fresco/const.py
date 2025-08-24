DOMAIN = "instantpot_fresco"
CONF_TOKEN = "access_token"
CONF_DEVICE_ID = "device_id"
CONF_MODULE_IDX = "module_idx"
CONF_MODEL_ID = "model_id"

DEFAULT_MODULE_IDX = 0
DEFAULT_MODEL_ID = "kitchenos:InstantBrands:InstantPotProPlus"

BASE_API = "https://api.fresco-kitchenos.com"

# Mapped IDs based on your capture
PRESSURE_MAP = {
    "Low":  "kitchenos:InstantBrands:PressureLow",
    "High": "kitchenos:InstantBrands:PressureHigh",
    "Max":  "kitchenos:InstantBrands:PressureMax",
}
VENT_MAP = {
    "Natural":       "kitchenos:InstantBrands:VentingNatural",
    "Pulse":         "kitchenos:InstantBrands:VentingPulse",
    "Quick":         "kitchenos:InstantBrands:VentingQuick",
    "NaturalQuick":  "kitchenos:InstantBrands:VentingNaturalQuick",
}
