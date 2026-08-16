# Changelog

All notable changes to ThermoPilot are documented in this file.

The project follows [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Fixed

- Made logical Cool/Heat activation evaluate hysteresis instead of forcing physical ON.
- Coalesced environment updates and serialized thermostat evaluation to prevent duplicate commands.
- Prevented power updates during command confirmation from starting parallel reconciliation.
- Corrected OFF confirmation to require the measured `off` power class below 50 W.
- Added native Home Assistant `climate.turn_on` and `climate.turn_off` support.
- Added selectable `none`/Manual preset behavior without changing the current target.
- Reduced and clamped the initialization guard to 10-15 seconds, with a 15-second default.
- Reported `initializing` throughout the startup guard and `online` for normal diagnostic status.

### Planned

- Fix HACS rendering of the footer and License badge by replacing their unresolved relative URLs with absolute GitHub URLs.
- Expand the README project motivation around unified Broadlink and similar IR/RF thermostat control, while documenting compatibility with any suitable Home Assistant switch entities.

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
