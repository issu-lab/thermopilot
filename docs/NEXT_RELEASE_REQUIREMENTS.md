# Next Release Requirements

This document records the behavior incorporated through `0.1.5`. Local automated validation is complete; field validation remains required before the release is considered production-ready.

## Non-blocking power confirmation

- Send the requested physical command immediately when the thermostat decision changes.
- Publish target, mode and action without waiting for power confirmation.
- Treat the feedback timeout as a maximum only and wake immediately on power-sensor state changes.
- Keep Home Assistant service calls and thermostat evaluation responsive while confirmation runs in the background.
- Cancel an obsolete pending confirmation when a newer physical request arrives; issue the newer command immediately.
- Preserve alternating recovery and maximum-attempt behavior after a genuine confirmation timeout.

## README compatibility

- Expose the header with the same HACS-compatible plain Markdown image used by ThermoMatrix.
- Expose the footer with a direct HTML `img` referencing `assets/issu-open-homelab-badge.png`.
- Avoid theme-dependent `picture` markup in content rendered by Home Assistant.
- Use an absolute raw GitHub URL for the footer image because HACS does not rewrite relative paths inside HTML `img` tags.
- Use an absolute GitHub destination for the License badge because HACS does not reliably rewrite a relative destination around a nested badge image.
- Add README regression checks for relative HTML image sources and relative badge destinations.

## Project motivation

- Expand the README `Why It Exists` section to reflect the Open Homelab project philosophy: ThermoPilot was created from a real need to provide one consistent thermostat interface for air conditioners and HVAC devices operated through Broadlink or comparable IR/RF remotes.
- Explain that the integration deliberately consumes standard Home Assistant `switch` entities rather than depending on Broadlink-specific APIs.
- State clearly that Broadlink, IR and RF devices are common use cases, not requirements: ThermoPilot works with any integration or hardware that exposes suitable momentary or command `switch` entities.
- Retain the distinction between separate ON/OFF command switches and a stateless toggle switch, with optional or required power feedback according to the selected strategy.

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
- If the saved mode is thermal and feedback reports OFF, keep the logical mode active but send ON only when the current temperature and hysteresis request physical operation.
- If the saved mode is OFF, keep the device off.
- Automatically reconcile saved and physical state when valid feedback becomes available.

## Initialization guard

- Keep the climate entity `unavailable` during the configurable 15-second initialization period by default.
- Discard commands received during initialization; do not queue them.
- Allow the initialization guard to be configured between 10 and 15 seconds; use 15 seconds as the safe default.
- Preserve saved mode, target and preset.
- Publish an `initializing` diagnostic state with a clear warning not to operate ThermoPilot until it is online.
- Add a prominent README warning explaining that this guard is intentional and required for correct state synchronization.
- Make the diagnostic sensor publish `initializing` for the entire initialization guard, regardless of temporary environment-sensor availability.
- After initialization, use the diagnostic state priority `error`, `degraded`, then `online`; use `online` instead of `ok` for normal operation.

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

## Thermostat-owned physical demand

- Selecting a thermal mode activates only the logical thermostat.
- The physical ON command must be sent only when the aggregated perceived temperature crosses the configured heat/cool hysteresis boundary.
- A selected thermal mode with no current demand must remain `idle` without sending a hardware command.
- This behavior is authoritative for command profiles both with and without dedicated power feedback.
- Power feedback validates physical state and detects manual operation; it must never replace the thermostat's thermal decision.
- Verify this behavior from ThermoMatrix, native Home Assistant climate controls and the device page.

## Aggregated environment input

- Temperature, humidity and pressure entities feed one aggregated perceived-temperature input.
- Invalid, unknown, unavailable and non-numeric source values are ignored according to the configured validity ranges.
- Only the aggregated perceived-temperature update may trigger the heat/cool decision.
- Coalesce source updates arriving together and serialize evaluation so one thermal boundary crossing can produce at most one physical command.

## Native climate actions

- Advertise and support Home Assistant `climate.turn_on` and `climate.turn_off` actions.
- `turn_on` restores the last thermal mode and then evaluates demand without forcing a physical ON command.
- `turn_off` selects logical OFF and sends a physical OFF command only when the controlled device is currently active.

## Manual preset

- Advertise `none` among selectable preset modes and translate it as Manual.
- Selecting Manual keeps the current target unchanged.
- Setting a target temperature directly selects Manual automatically.
