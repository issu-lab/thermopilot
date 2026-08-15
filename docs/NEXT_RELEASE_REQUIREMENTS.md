# Next Release Requirements

This document records approved behavior for the release following `0.1.2`. It is a planning document only; none of these changes are implemented in `0.1.2`.

## README compatibility

- Expose the header with the same HACS-compatible plain Markdown image used by ThermoMatrix.
- Expose the footer with a direct HTML `img` referencing `assets/issu-open-homelab-badge.png`.
- Avoid theme-dependent `picture` markup in content rendered by Home Assistant.

## Command and feedback separation

- Treat command strategy and state feedback as independent settings.
- Keep the command strategy immutable after entry creation.
- Allow dedicated power feedback to be added, changed or removed through reconfiguration.
- Support discrete ON/OFF commands with or without dedicated power feedback.
- Require dedicated power feedback for a stateless toggle command.

## Confirmed-state recovery

- When dedicated power feedback is enabled, validate every requested physical state through measured power.
- Use a configurable 60-second feedback and alternating-command interval by default.
- For an unconfirmed ON request, recover with `ON -> verify -> OFF -> wait -> ON -> verify`.
- For an unconfirmed OFF request, recover with `OFF -> verify -> ON -> wait -> OFF -> verify`.
- Stop immediately when the requested state is confirmed.
- Allow at most three complete recovery cycles, then publish a diagnostic error and use the configured notification service.

## Manual operation and restoration

- Detect manual ON/OFF changes when dedicated power feedback is configured.
- Infer a manually selected thermal mode from temperature, target and hysteresis; retain `unknown` when inference is ambiguous.
- Treat the last saved logical mode as authoritative after restart.
- If the saved mode is thermal and feedback reports OFF, restore that saved mode even when the current temperature would leave the physical thermostat idle.
- If the saved mode is OFF, keep the device off.
- Automatically reconcile saved and physical state when valid feedback becomes available.

## Initialization guard

- Keep the climate entity `unavailable` during the configurable 60-second initialization period.
- Discard commands received during initialization; do not queue them.
- Preserve saved mode, target and preset.
- Publish an `initializing` diagnostic state with a clear warning not to operate ThermoPilot until it is online.
- Add a prominent README warning explaining that this guard is intentional and required for correct state synchronization.

## Power-sensor availability

- Apply this behavior only when a dedicated power sensor is configured.
- On invalid, unknown, unavailable or non-numeric feedback, start a configurable three-minute grace period.
- During the grace period, expose degraded diagnostics and block hardware commands.
- If invalid feedback persists beyond three minutes, make the climate entity `unavailable` without sending OFF or altering saved mode, target or preset.
- Send one outage notification when the three-minute limit is crossed, but only if a notification service is configured.
- Restore the climate entity immediately on the first valid numeric reading; do not require a recovery stabilization period.
- Reconcile physical and saved state automatically after recovery.
- Send one recovery notification only when a notification service is configured and a corresponding outage notification was previously sent.
- If feedback becomes invalid again, start a new three-minute grace period.

### Notification messages

- Power sensor unavailable:
  - Title: `⚠️ ThermoPilot unavailable`
  - Message: `<thermostat name>: the dedicated power sensor has been unavailable for more than 3 minutes. Hardware commands are blocked.`
- Power sensor restored and reconciliation successful:
  - Title: `✅ ThermoPilot restored`
  - Message: `<thermostat name>: the dedicated power sensor is available again. ThermoPilot is online and physical state reconciliation completed successfully.`
- Power sensor restored but reconciliation failed:
  - Title: `❌ ThermoPilot recovery failed`
  - Message: `<thermostat name>: power feedback is available again, but the requested physical state could not be restored after 3 recovery cycles.`
- Send these as normal, non-critical notifications. Keep diagnostic details on the diagnostic entity rather than expanding the user-facing message.

## Initial activation correction

- Selecting a thermal mode must activate the physical thermostat even when current conditions imply `idle`; the physical thermostat remains responsible for compressor demand.
- Verify this behavior from ThermoMatrix, native Home Assistant climate controls and the device page.
