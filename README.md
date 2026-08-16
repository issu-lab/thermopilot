![ThermoPilot](assets/thermopilot-banner-light.png)

<div align="center">

[![Status](https://img.shields.io/badge/status-active%20development-F0B429?style=flat-square)](#project-status)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2026.8%2B-41BDF5?style=flat-square&logo=homeassistant&logoColor=white)](https://www.home-assistant.io/)
[![HACS](https://img.shields.io/badge/HACS-custom%20integration-C346F4?style=flat-square)](https://www.hacs.xyz/)
[![License](https://img.shields.io/badge/license-MIT-C346F4?style=flat-square)](LICENSE)

**A configurable native climate controller for Home Assistant.**

ThermoPilot creates native climate entities from existing sensors and hardware commands. It supports reliable discrete ON/OFF commands as well as stateless toggle devices confirmed by a dedicated power sensor.

</div>

---

## Project Status

| Field | Current state |
|---|---|
| **Maturity** | 🟡 Active Development |
| **Used in my homelab** | 🟡 Testing |
| **Recommended for production** | ❌ Not yet |
| **Setup difficulty** | 🟢 Beginner |
| **Documentation** | ✅ Complete for initial testing |
| **Current version** | `0.1.3` |
| **Minimum Home Assistant** | 2026.8.0 |
| **Local tests** | 🟡 Initial suite |
| **Discrete strategy validation** | ❌ Not yet |
| **Power-feedback strategy validation** | ❌ Not yet |

> [!WARNING]
> Version 0.1.3 is an initial testing release. Validate each hardware strategy with the documented rollback procedure before using it in production.

> [!IMPORTANT]
> ThermoPilot intentionally remains unavailable during its default 15-second initialization period. Do not operate it from ThermoMatrix or another dashboard until it is online. Commands received during initialization are discarded to ensure that saved state, sensors and the physical device are synchronized correctly.

---

## Why It Exists

ThermoPilot was created to replace two independent AppDaemon thermostats with one reusable Home Assistant integration:

- **Discrete commands** — separate ON and OFF operations, reliable commands and estimated physical state.
- **Power-feedback toggle** — one stateless command confirmed by measured power, including manual-operation detection and retries.

The integration is configured from the Home Assistant UI. No AppDaemon instance, MQTT broker, YAML production configuration or external Python package is required.

### Home Assistant Integration and Device

ThermoPilot is installed and managed as a HACS custom integration. Each configured thermostat is represented as one Home Assistant device that groups its climate entity, diagnostic sensor and optional power-feedback status sensor. It therefore appears with regular integrations instead of dispersing its configuration among Home Assistant Helpers.

---

## Features

- 🌡️ Native Home Assistant `climate` entity.
- 🧩 Multiple independent thermostat instances.
- 🖥️ Guided configuration and advanced options flows.
- 🌡️ Any number of temperature sensors with filtered averaging.
- 💧 Optional humidity and pressure sensor averaging.
- 🥵 Existing Steadman perceived-temperature calculation.
- ❄️ Independently selectable cool and heat modes.
- 💨 Optional humidity-controlled dry mode for discrete commands.
- 🎯 Separate target and preset state for every thermal mode.
- 🏠 Home, Away, Sleep and Comfort presets.
- ✋ Manual target state compatible with ThermoMatrix (`preset_mode: none`).
- 🔌 Native `climate.turn_on` and `climate.turn_off` actions.
- 💾 Persistent thermostat and last physical-command state.
- ⏱️ Guarded startup and configurable restoration delays.
- ⚡ Dedicated power feedback, manual-operation detection and retry support.
- 🩺 Native diagnostics and optional power-feedback status sensor.
- 🌍 English and Italian UI translations.
- 📦 HACS-ready repository layout.

---

## Recommended Dashboard: ThermoMatrix

ThermoPilot works with standard Home Assistant climate cards and any dashboard that follows the native climate entity model.

For the intended visual experience, we recommend pairing it with [ThermoMatrix Card](https://github.com/issu-lab/thermomatrix-card). Both projects were created from the same requirement: a clear, reliable and reusable Home Assistant climate interface.

ThermoMatrix automatically reads the HVAC modes and presets exposed by ThermoPilot, displays `preset_mode: none` as **Manual**, and can use ThermoPilot's dedicated power-feedback status sensor as its optional extended status entity.

```yaml
type: custom:thermomatrix-card
entity: climate.living_room_thermostat
show_presets: true
temperature_step: 0.1
```

Installations with dedicated power feedback may also assign ThermoPilot's power-feedback status sensor to ThermoMatrix's optional `status_entity` setting.

> [!NOTE]
> ThermoMatrix is optional. ThermoPilot has no dashboard dependency and remains fully usable with native Home Assistant cards.

---

## Installation with HACS

ThermoPilot is not yet published. After the repository is available on GitHub:

1. Open **HACS** in Home Assistant.
2. Open the top-right menu and select **Custom repositories**.
3. Add `https://github.com/issu-lab/thermopilot`.
4. Select **Integration** as the repository type.
5. Download ThermoPilot.
6. Restart Home Assistant.
7. Open **Settings → Devices & services → Add integration**.
8. Search for **ThermoPilot**.

For local validation before publication, copy `custom_components/thermopilot` into the Home Assistant `custom_components` directory and restart Home Assistant.

---

## Guided Setup

### 1. Identity

Enter the thermostat name and choose a command strategy:

- `Discrete ON and OFF commands`
- `Toggle with dedicated power feedback`

### 2. Modes

Select cool, heat or both. Dry mode is optional and appears only for the discrete strategy.

### 3. Environment sensors

Select at least one temperature sensor. Humidity and pressure are optional. Dry mode requires humidity.

Every selected family is averaged after excluding unavailable, unknown, non-numeric, non-finite and out-of-range readings.

### 4. Hardware

Discrete installations select one momentary switch for each enabled mode. Toggle installations select one command switch and one dedicated power sensor.

The initial wizard intentionally hides thresholds, delays and preset temperatures. They remain available from the integration's **Configure** action.

---

## Default Thermostat Settings

| Setting | Default |
|---|---:|
| Minimum target | 16.0 °C |
| Maximum target | 30.0 °C |
| Temperature step | 0.1 °C |
| Thermal hysteresis | 0.2 °C |
| Startup command delay | 15 seconds |

### Presets

| Preset | Cool | Heat |
|---|---:|---:|
| Home | 26.0 °C | 21.0 °C |
| Away | 28.0 °C | 17.0 °C |
| Sleep | 26.2 °C | 18.0 °C |
| Comfort | 24.0 °C | 20.0 °C |

Changing the target temperature sets the preset state to `none`. When the thermostat is off, target and preset changes apply to the last selected thermal mode.

Selecting Cool or Heat activates only the logical thermostat. ThermoPilot sends a physical ON command only after the aggregated perceived temperature crosses the configured hysteresis boundary. Until then, the climate entity remains in `idle`.

---

## Discrete Command Strategy

This strategy is designed for momentary Broadlink entities where `switch.turn_on` sends an explicit ON command and `switch.turn_off` sends an explicit OFF command. Their Home Assistant state is not used as physical feedback.

ThermoPilot persists whether it last commanded the device ON. After a restart:

1. sensors and entities become available immediately;
2. physical commands remain blocked for 15 seconds;
3. if the saved physical state was ON, ThermoPilot sends OFF;
4. it waits 10 seconds;
5. normal thermostat evaluation resumes;
6. it sends ON only if current temperature and hysteresis still request physical operation.

State quality is reported as `estimated`.

### Dry mode

Dry mode is active only when selected by the user:

- ON above 60% humidity;
- OFF below 55% humidity;
- state retained between both thresholds;
- at least five minutes between physical changes;
- suspended when no real humidity reading is available.

---

## Toggle with Power Feedback

This strategy uses validated three-state power thresholds:

| Power | Classification |
|---:|---|
| Below 50 W | Off |
| 50-200 W | Starting |
| Above 200 W | On |

Crossing 50 W confirms an ON command. An OFF command is confirmed only below 50 W; the 50-200 W starting range never confirms OFF. Defaults use a two-second pulse, a 60-second feedback timeout and at most three attempts.

Dedicated power feedback is independent of the command strategy. It can also validate discrete ON/OFF commands. In every profile it confirms physical state and detects manual operation; it does not replace the thermal decision.

Unexpected stable power changes are evaluated after 30 seconds. A manual activation is inferred as cool or heat only when current perceived temperature clearly crosses that mode's target and hysteresis. Ambiguous manual activation is reported as unknown and never triggers an automatic command.

State quality is reported as `confirmed`.

---

## Diagnostics

Each thermostat creates one diagnostic sensor containing:

- integration and configuration versions;
- hardware strategy;
- startup state;
- sensor health and valid/invalid counts;
- last command and timestamp;
- latest error;
- physical-state estimate and quality.

Power-feedback installations also create a dedicated status sensor with power classification and measured power. Downloadable integration diagnostics exclude command entity IDs and notification targets.

---

## Reference Profiles

The files in `examples/` document the values used by the original installations. They are not loaded by Home Assistant:

- `examples/discrete-command-profile.yaml`
- `examples/power-feedback-profile.yaml`

The production source of truth is the Home Assistant config entry created by the setup wizard.

---

## Development

Run the dependency-free model tests:

```shell
python3 -m unittest discover -s tests -v
```

Validate Python and JSON syntax:

```shell
python3 -m compileall custom_components tests
python3 -m json.tool custom_components/thermopilot/manifest.json
```

The GitHub workflow also runs HACS validation and Hassfest.

---

## Migration

Start with the discrete ON/OFF strategy when both command types are available, because it provides the most predictable cutover. Stop the existing thermostat controller before adding ThermoPilot. The old and new implementations must never control the same hardware simultaneously.

Detailed steps are available in:

- `docs/MIGRATION_DISCRETE_COMMANDS.md`
- `docs/MIGRATION_POWER_FEEDBACK.md`

Historical site-specific folders may be deleted from production only after the corresponding migration checklist passes. Local reference copies remain until the final repository audit confirms that no unique behavior was lost.

---

## Future Integrations

### Network UPS Tools

A future optional NUT integration may distinguish an integration restart from a confirmed power outage while Home Assistant remains powered by a UPS. It may persist outage and restoration timestamps and trigger discrete-command reconciliation only after mains power returns.

NUT support is not implemented in version 0.1.3.

---

## Known Limitations

- Production validation has not started.
- Discrete commands cannot provide physical feedback.
- Power feedback cannot identify an ambiguous manually selected HVAC mode.
- Four standard presets are supported; arbitrary custom presets are planned for a later version.
- The initial compatibility baseline is Home Assistant 2026.8 or newer.

---

## License

Released under the [MIT License](LICENSE).

---

<div align="center">

This project is part of the **iSSU Open Homelab ecosystem**.

<a href="https://github.com/issu-lab/Open-Homelab">
  <img src="assets/issu-open-homelab-badge.png"
       alt="Explore iSSU Open Homelab"
       width="480">
</a>

</div>
