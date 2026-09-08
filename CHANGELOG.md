# Changelog

All notable changes to ThermoPilot are documented in this file.

The project follows [Semantic Versioning](https://semver.org/).

## [0.3.0] - 2026-09-08

### Changed

- Consolidated controller health, physical state and command progress into one
  always-present, translated Status sensor.
- Preserved the former Diagnostics sensor unique ID so existing installations
  keep the entity instead of receiving another one.
- Added `thermopilot_role: status` as a stable discovery marker for dashboards.
- Removed creation of the separate power-feedback status sensor; power,
  confirmation quality and command progress now belong to the unified entity.

### Migration

- Existing dashboards using the former power-feedback sensor should select the
  unified Status entity. The old registry entry may remain unavailable until it
  is removed manually after dashboard migration.

## [0.2.1] - 2026-09-08

### Added

- Added compact command-operation phases to the existing power-feedback status
  sensor, without creating another entity or replacing its physical state.
- Exposed the requested physical state, current and maximum attempt, and pending
  confirmation for dashboards and diagnostics.
- Added native English and Italian translations for the power classification
  enum shown by Home Assistant.

### Changed

- Documented stable language-independent phase codes for localized clients such
  as ThermoMatrix.

## [0.2.0] - 2026-09-08

### Changed

- Reworked Dry mode as a dew-point controller with a native, temperature-adaptive
  Home Assistant humidity target constrained to configurable limits.
- Added independent Home, Away, Sleep and Comfort dew-point presets for Dry.
- Kept explicit user OFF commands outside Dry hysteresis and minimum-interval
  protection so active hardware is stopped immediately.
- Exposed current and target dew point in diagnostics and replaced the legacy
  fixed Dry ON/OFF humidity thresholds in advanced options.

## [0.1.5] - 2026-08-16

### Fixed

- Sent physical ON/OFF commands immediately without holding the Home Assistant service call open during power confirmation.
- Published target, mode and action updates before background feedback verification completes.
- Replaced fixed feedback sleeps with sensor-event-driven confirmation while retaining the configured timeout as an upper bound.
- Allowed newer physical requests, especially OFF, to cancel obsolete pending confirmations and run immediately.
- Kept alternating recovery attempts serialized without blocking thermostat evaluation or dashboard controls.

## [0.1.4] - 2026-08-16

### Fixed

- Made logical Cool/Heat activation evaluate hysteresis instead of forcing physical ON.
- Coalesced environment updates and serialized thermostat evaluation to prevent duplicate commands.
- Prevented power updates during command confirmation from starting parallel reconciliation.
- Corrected OFF confirmation to require the measured `off` power class below 50 W.
- Added native Home Assistant `climate.turn_on` and `climate.turn_off` support.
- Added selectable `none`/Manual preset behavior without changing the current target.
- Reduced and clamped the initialization guard to 10-15 seconds, with a 15-second default.
- Reported `initializing` throughout the startup guard and `online` for normal diagnostic status.

### Changed

- Made the footer and License destinations HACS-safe with absolute GitHub URLs and added regression tests for their rendering contract.
- Expanded the project motivation around unified Broadlink and comparable IR/RF control while documenting support for any suitable Home Assistant switch entities.
- Delayed power-recovery notifications until reconciliation finishes and added the approved recovery-failure notification.

## [0.1.3] - 2026-08-15

### Changed

- Exposed the README banner and footer with the same HACS-compatible markup used by ThermoMatrix.
- Separated discrete command selection from optional dedicated power feedback.
- Added confirmed discrete-command recovery with alternating commands and three attempts.
- Added a deliberate unavailable initialization state and power-sensor outage handling.
- Added outage and recovery notifications when a notification service is configured.

## [0.1.2] - 2026-08-15

### Changed

- Classified each ThermoPilot configuration as a Home Assistant device so its entities remain grouped with regular integrations.
- Replaced the Home Assistant brand icon with the approved two-arc iSSU signal mark.
- Restored the approved project banner, footer and social-preview artwork without altering their established branding.
- Replaced theme-dependent README picture blocks with direct images compatible with the HACS renderer.
- Reduced the displayed footer size.

## [0.1.1] - 2026-08-15

### Added

- HACS brand icons derived from the approved iSSU GitHub avatar.

## [0.1.0] - 2026-08-15

### Added

- Native Home Assistant climate integration distributed through HACS.
- Guided setup for discrete commands and toggle-with-power-feedback strategies.
- Multiple temperature, humidity and pressure sensors with validation and averaging.
- Per-mode targets, standard presets, perceived temperature and thermal hysteresis.
- Optional humidity-controlled dry mode.
- Persistent physical-command state and guarded startup reconciliation.
- General diagnostics and dedicated power-feedback status.
- English and Italian translations.
- Generic reference profiles and migration documentation for both hardware strategies.

### Status

- Complete initial implementation.
- Local validation required before the first production test.
