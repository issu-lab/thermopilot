# Architecture

## Integration boundary

ThermoPilot is a Home Assistant helper integration. It consumes states from existing sensor entities and sends commands through existing switch entities. It does not communicate directly with Broadlink hardware.

Each config entry owns one controller, one climate entity and one unified Status
sensor. Power feedback enriches the same Status entity instead of creating a
second sensor.

## Runtime components

- `config_flow.py` collects the minimal installation contract and validates advanced options.
- `controller.py` owns listeners, decisions, physical commands, startup reconciliation and persistence.
- `models.py` contains dependency-light state models and pure thermostat decisions.
- `climate.py` exposes the native Home Assistant climate API.
- `sensor.py` exposes one translated operational and diagnostic state.
- `diagnostics.py` provides downloadable non-sensitive diagnostics.

## State separation

ThermoPilot separates:

- logical HVAC mode;
- target and preset per thermal mode;
- a separate Dry dew-point target exposed as temperature-adaptive relative
  humidity through the native Climate API;
- last selected thermal mode;
- last physical command state;
- current HVAC action;
- observed or estimated physical state;
- command phase, requested physical state, attempt and pending confirmation;
- sensor health.

This distinction prevents an active climate mode in `idle` from being mistaken for a physically running device during startup restoration.

The unified sensor prioritizes controller health, then transient command
progress, then physical state. It exposes `thermopilot_role: status` so a
dashboard can discover it through the device shared with the climate entity.
Transient progress also remains available through the compact `command_phase`
attribute. Its stable values are `idle`, `starting`, `stopping`, `waiting`,
`retrying`, `confirmed`, `failed` and `unknown`.

## Safety invariants

- No physical command is sent during the startup guard.
- Invalid or missing temperature suspends automatic heat/cool commands.
- Selecting a logical thermal mode never forces a physical ON command.
- Heat/cool commands are derived only from the aggregated perceived temperature and hysteresis.
- Environment-source updates are coalesced and thermostat evaluations are serialized.
- Missing humidity suspends dry commands.
- Missing temperature also suspends Dry because dew point requires both inputs.
- Dry starts above its target plus dew-point hysteresis and stops at the target.
- An explicit user OFF bypasses the Dry minimum command interval.
- Only one physical command transaction runs at a time.
- Power-feedback retries always re-read power before pulsing the toggle.
- Power changes observed during command confirmation never start a parallel reconciliation.
- Ambiguous manual power activation never selects a mode automatically.
- Persistent writes use Home Assistant's versioned storage helper.
- Unloading the integration cancels timers and listeners before final persistence.

## Future NUT boundary

NUT support will be an optional power-event provider. It must not be coupled to either hardware strategy. A future provider may report `outage_started` and `power_restored`, while the discrete strategy decides whether saved physical state requires reconciliation.
