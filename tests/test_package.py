import json
from pathlib import Path
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


if __name__ == "__main__":
    unittest.main()
