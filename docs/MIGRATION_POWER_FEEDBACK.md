# Power Feedback Migration

## Preconditions

- The discrete strategy has already been validated when applicable.
- ThermoPilot is installed but not yet configured for this device.
- Home Assistant is running version 2026.8 or newer.
- The previous AppDaemon source remains available locally for rollback.
- Current mode, target, preset and power have been recorded.

## Cutover

1. Stop the existing thermostat controller.
2. Confirm it no longer pulses the Broadlink command.
3. Add ThermoPilot from **Settings → Devices & services**.
4. Enter `Whole Home Thermostat` or another descriptive English name.
5. Select **Toggle with dedicated power feedback**.
6. Enable cool and heat.
7. Select the entities documented in `examples/power-feedback-profile.yaml`.
8. Confirm that the entity is created as `climate.whole_home_thermostat`; rename it before continuing if necessary.
9. Add the optional notification action in advanced settings.
10. Wait through the 15-second command guard.
11. Confirm adoption of an already-running device from power feedback.
12. Validate one natural cool ON/OFF cycle.
13. Validate one natural heat ON/OFF cycle when seasonally appropriate.
14. Validate stable manual ON and OFF detection.
15. Confirm ambiguous manual activation produces unknown state without a command.
16. Validate retry exhaustion, notification and diagnostics without changing field-validated thresholds.

## Rollback

1. Disable or delete the ThermoPilot config entry.
2. Confirm it no longer pulses the Broadlink command.
3. Restore the previous AppDaemon app.
4. Never run both implementations together.

Delete the old production folder only after every applicable check passes.
