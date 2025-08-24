# Home Assistant – Instant Pot (Fresco Cloud)

Control your Instant Pot via the official Fresco KitchenOS cloud endpoints by providing your InstantConnect app login email and password.
This integration exposes Home Assistant services you can call from automations, scripts, or the UI.


## Install (HACS custom repo)
1. In HACS → Integrations → **Custom repositories**, add: `https://github.com/seanlaidlaw/homeassistant-instantpot`
Category: Integration.
2. Install **Instant Pot (Fresco Cloud)** and restart Home Assistant.
3. Settings → Devices & Services → **Add Integration** → *Instant Pot (Fresco Cloud)*.
4. Enter your InstantPot email and password in the configuration dialog - this is used to renew the access token and fetch devices tracked by InstantConnect.

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


## License

GPL v3
