# Architecture

## Integration boundary

ThermoPilot is a Home Assistant helper integration. It consumes states from existing sensor entities and sends commands through existing switch entities. It does not communicate directly with Broadlink hardware.

Each config entry owns one controller, one climate entity, one diagnostic sensor and an optional power-feedback sensor.

## Runtime components

- `config_flow.py` collects the minimal installation contract and validates advanced options.
- `controller.py` owns listeners, decisions, physical commands, startup reconciliation and persistence.
- `models.py` contains dependency-light state models and pure thermostat decisions.
- `climate.py` exposes the native Home Assistant climate API.
- `sensor.py` exposes general and power-feedback diagnostics.
- `diagnostics.py` provides downloadable non-sensitive diagnostics.

## State separation

ThermoPilot separates:

- logical HVAC mode;
- target and preset per thermal mode;
- last selected thermal mode;
- last physical command state;
- current HVAC action;
- observed or estimated physical state;
- sensor health.

This distinction prevents an active climate mode in `idle` from being mistaken for a physically running device during startup restoration.

## Safety invariants

- No physical command is sent during the startup guard.
- Invalid or missing temperature suspends automatic heat/cool commands.
- Selecting a logical thermal mode never forces a physical ON command.
- Heat/cool commands are derived only from the aggregated perceived temperature and hysteresis.
- Environment-source updates are coalesced and thermostat evaluations are serialized.
- Missing humidity suspends dry commands.
- Only one physical command transaction runs at a time.
- Power-feedback retries always re-read power before pulsing the toggle.
- Power changes observed during command confirmation never start a parallel reconciliation.
- Ambiguous manual power activation never selects a mode automatically.
- Persistent writes use Home Assistant's versioned storage helper.
- Unloading the integration cancels timers and listeners before final persistence.

## Future NUT boundary

NUT support will be an optional power-event provider. It must not be coupled to either hardware strategy. A future provider may report `outage_started` and `power_restored`, while the discrete strategy decides whether saved physical state requires reconciliation.
