# Discrete Commands Migration

## Preconditions

- ThermoPilot is installed but not configured.
- Home Assistant is running version 2026.8 or newer.
- The previous AppDaemon source remains available locally for rollback.
- Current mode, target, preset and physical state have been recorded.

## Cutover

1. Stop the existing thermostat controller.
2. Confirm it no longer sends Broadlink commands.
3. Add ThermoPilot from **Settings → Devices & services**.
4. Enter `Living Room Thermostat` or another descriptive English name.
5. Select **Discrete ON and OFF commands**.
6. Enable cool, heat and dry.
7. Select the sensor and command entities documented in `examples/discrete-command-profile.yaml`.
8. Confirm that the entity is created as `climate.living_room_thermostat`; rename it before continuing if necessary.
9. Wait through the 15-second command guard.
10. Test logical idle before any physical ON demand.
11. Validate one cool ON/OFF cycle and one heat ON/OFF cycle.
12. Validate dry ON above 60% and OFF below 55% when naturally testable.
13. Validate Home, Away, Sleep, Comfort and manual targets while off.
14. Restart the integration with saved physical state OFF.
15. Restart it with saved physical state ON and verify OFF, ten seconds, then ON only when thermal demand is present.
16. Confirm ThermoMatrix, automations and load management still reference the expected entity ID.

## Rollback

1. Disable or delete the ThermoPilot config entry.
2. Confirm it no longer sends commands.
3. Restore the previous AppDaemon app.
4. Never run both implementations together.

Delete the old production folder only after every applicable check passes.
