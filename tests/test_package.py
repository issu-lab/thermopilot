import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
INTEGRATION = ROOT / "custom_components" / "thermopilot"


def key_shape(value):
    if isinstance(value, dict):
        return {key: key_shape(child) for key, child in value.items()}
    return None


class PackageTests(unittest.TestCase):
    def test_manifest_and_version_match(self):
        manifest = json.loads((INTEGRATION / "manifest.json").read_text())
        version = (ROOT / "VERSION").read_text().strip()
        constants = (INTEGRATION / "const.py").read_text()
        self.assertEqual(manifest["domain"], "thermopilot")
        self.assertEqual(manifest["version"], version)
        self.assertIn(f'INTEGRATION_VERSION: Final = "{version}"', constants)
        self.assertTrue(manifest["config_flow"])

    def test_hacs_minimum_home_assistant_version(self):
        hacs = json.loads((ROOT / "hacs.json").read_text())
        self.assertEqual(hacs["homeassistant"], "2026.8.0")

    def test_english_and_italian_translations_have_identical_keys(self):
        translations = INTEGRATION / "translations"
        english = json.loads((translations / "en.json").read_text())
        italian = json.loads((translations / "it.json").read_text())
        self.assertEqual(key_shape(english), key_shape(italian))

    def test_site_entities_are_not_hard_coded_in_python(self):
        source = "\n".join(path.read_text() for path in INTEGRATION.glob("*.py"))
        self.assertNotIn("sensor.living_room_temperature", source)
        self.assertNotIn("sensor.air_conditioner_power", source)
        self.assertNotIn("switch.climatizzatore", source)
        self.assertNotIn("notify.my_phone", source)

    def test_reference_profiles_remain_documentation_only(self):
        discrete = (ROOT / "examples" / "discrete-command-profile.yaml").read_text()
        power_feedback = (ROOT / "examples" / "power-feedback-profile.yaml").read_text()
        self.assertIn("Reference only", discrete)
        self.assertIn("Reference only", power_feedback)

    def test_discrete_setup_supports_optional_power_feedback(self):
        flow = (INTEGRATION / "config_flow.py").read_text()
        self.assertIn(
            'fields[vol.Optional(CONF_POWER_SENSOR)] = _entity_selector("sensor")',
            flow,
        )

    def test_climate_advertises_native_on_off_and_manual_preset(self):
        climate = (INTEGRATION / "climate.py").read_text()
        self.assertIn("ClimateEntityFeature.TURN_ON", climate)
        self.assertIn("ClimateEntityFeature.TURN_OFF", climate)
        self.assertIn("async def async_turn_on", climate)
        self.assertIn("async def async_turn_off", climate)
        self.assertIn("PRESET_NONE", climate)

    def test_mode_selection_does_not_force_physical_on(self):
        controller = (INTEGRATION / "controller.py").read_text()
        start = controller.index("    async def async_set_hvac_mode")
        end = controller.index("    async def async_set_temperature", start)
        method = controller[start:end]
        self.assertNotIn("_async_set_physical(True)", method)
        self.assertIn("await self.async_evaluate()", method)

    def test_environment_control_is_coalesced_and_serialized(self):
        controller = (INTEGRATION / "controller.py").read_text()
        self.assertIn("_environment_evaluation_cancel", controller)
        self.assertIn("_evaluation_lock", controller)

    def test_initialization_discards_user_commands_and_reports_initializing(self):
        controller = (INTEGRATION / "controller.py").read_text()
        sensor = (INTEGRATION / "sensor.py").read_text()
        for method_name in (
            "async_set_hvac_mode",
            "async_set_temperature",
            "async_set_preset",
        ):
            start = controller.index(f"    async def {method_name}")
            next_method = controller.find("\n    async def ", start + 10)
            method = controller[start:next_method]
            self.assertIn("if self.commands_blocked:", method)
        self.assertIn("return self.controller.diagnostic_status", sensor)
        self.assertIn('self.last_error == "power_sensor_degraded"', controller)

    def test_existing_startup_delay_is_clamped_to_new_safe_range(self):
        controller = (INTEGRATION / "controller.py").read_text()
        self.assertIn("if key == OPT_STARTUP_DELAY:", controller)
        self.assertIn("min(15.0, max(10.0", controller)

    def test_power_updates_do_not_reconcile_during_command_confirmation(self):
        controller = (INTEGRATION / "controller.py").read_text()
        start = controller.index("    def _power_changed")
        end = controller.index("    async def _async_finish_startup", start)
        method = controller[start:end]
        self.assertIn("recovered_from_feedback_loss", method)
        self.assertIn("if self._command_pending:", method)

    def test_readme_uses_hacs_safe_footer_and_license_destinations(self):
        readme = (ROOT / "README.md").read_text()
        self.assertIn(
            "https://raw.githubusercontent.com/issu-lab/thermopilot/main/"
            "assets/issu-open-homelab-badge.png",
            readme,
        )
        self.assertIn(
            "](https://github.com/issu-lab/thermopilot/blob/main/LICENSE)",
            readme,
        )
        self.assertIsNone(re.search(r'<img\s+src="assets/', readme))

    def test_readme_explains_generic_ir_rf_switch_origin(self):
        readme = (ROOT / "README.md").read_text()
        for phrase in ("real-world need", "IR/RF", "standard Home Assistant `switch`"):
            self.assertIn(phrase, readme)
        self.assertIn("not requirements", readme)

    def test_recovery_notification_waits_for_reconciliation_result(self):
        controller = (INTEGRATION / "controller.py").read_text()
        self.assertIn("_async_recover_after_feedback_return", controller)
        self.assertIn("reconciliation_succeeded", controller)
        self.assertIn("ThermoPilot recovery failed", controller)

    def test_power_feedback_is_event_driven_and_non_blocking(self):
        controller = (INTEGRATION / "controller.py").read_text()
        self.assertIn("_power_feedback_event = asyncio.Event()", controller)
        self.assertIn("self._power_feedback_event.set()", controller)
        self.assertIn("asyncio.wait_for", controller)
        self.assertIn("_async_confirm_physical_state", controller)
        start = controller.index("    async def _async_confirm_physical_state")
        end = controller.index("    def _toggle_target_reached", start)
        self.assertNotIn("asyncio.sleep", controller[start:end])

    def test_new_physical_request_preempts_pending_confirmation(self):
        controller = (INTEGRATION / "controller.py").read_text()
        self.assertIn("_confirmation_generation", controller)
        self.assertIn("_cancel_pending_confirmation", controller)
        self.assertIn("self._confirmation_task.cancel()", controller)

    def test_target_and_mode_are_published_before_feedback_confirmation(self):
        controller = (INTEGRATION / "controller.py").read_text()
        for method_name in ("async_set_hvac_mode", "async_set_temperature"):
            start = controller.index(f"    async def {method_name}")
            end = controller.find("\n    async def ", start + 10)
            method = controller[start:end]
            self.assertIn("self._notify_update()", method)


if __name__ == "__main__":
    unittest.main()
