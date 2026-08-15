# Changelog

All notable changes to ThermoPilot are documented in this file.

The project follows [Semantic Versioning](https://semver.org/).

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
