# Home Assistant – Instant Pot (Fresco Cloud)

Control your Instant Pot via the official Fresco KitchenOS cloud endpoints by providing your **Bearer access token** and **device_id** captured from the vendor app. This integration exposes Home Assistant services (no entities) you can call from automations, scripts, or the UI.

> ⚠️ Safety: This only calls the same cloud API your official app uses. It **does not** bypass safety mechanisms or talk to the cooker locally. Use at your own risk and never leave pressure appliances unattended.

## Install (HACS custom repo)
1. In HACS → Integrations → **Custom repositories**, add: `https://github.com/seanlaidlaw/homeassistant-instantpot`
Category: Integration.
2. Install **Instant Pot (Fresco Cloud)** and restart Home Assistant.
3. Settings → Devices & Services → **Add Integration** → *Instant Pot (Fresco Cloud)*.
4. Paste your **Access Token (Bearer JWT)** and **Device ID**. (Module index usually `0`.)

## Services

All services are under domain `instantpot_fresco`:

- `instantpot_fresco.cancel`
- `instantpot_fresco.start_keep_warm`
- `instantpot_fresco.update_keep_warm`
- `instantpot_fresco.start_pressure_cook`
- `instantpot_fresco.update_pressure_cook`

### Examples

**Start Keep Warm** (70°C for 2h):
```yaml
service: instantpot_fresco.start_keep_warm
data:
temp_c: 70
duration_seconds: 7200
```

**Start Pressure Cook** (High, 10 min, NaturalQuick + 5 min vent):
```yaml
service: instantpot_fresco.start_pressure_cook
data:
  pressure: High
  cook_time_seconds: 600
  venting: NaturalQuick
  vent_time_seconds: 300
  nutriboost: false
```

**Cancel** (stop cooking):
```yaml
service: instantpot_fresco.cancel
```

## Getting token & device_id

Use your own capture (e.g., Apple rvictl/Charles). Do not share tokens publicly. Tokens may expire; if commands stop working, update the token in the integration options.

## License

GPL v3
