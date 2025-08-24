DOMAIN = "instantpot_fresco"

# Config keys
CONF_USERNAME = "username"
CONF_PASSWORD = "password"
CONF_CLIENT_ID = "client_id"      # e.g. 5qucjsjb9i1ahnddonctmp9hba
CONF_REGION = "region"            # e.g. us-east-2
CONF_DEVICE_ID = "device_id"      # discovered via /user/
CONF_MODULE_IDX = "module_idx"    # usually 0
CONF_MODEL_ID = "model_id"        # appliance model id

# Defaults
DEFAULT_MODULE_IDX = 0
DEFAULT_MODEL_ID = "kitchenos:InstantBrands:InstantPotProPlus"
DEFAULT_REGION = "us-east-2"

# API base
BASE_API = "https://api.fresco-kitchenos.com"

# ID maps (from capture)
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
