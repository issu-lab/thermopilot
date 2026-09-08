import math
import unittest

from _load_pure import const, models


class SensorAggregationTests(unittest.TestCase):
    def test_averages_only_finite_numeric_values_inside_range(self):
        average, valid, invalid = models.valid_average(
            ["20", 22, "unknown", "bad", None, 100, math.nan], -20, 60
        )
        self.assertEqual(average, 21)
        self.assertEqual(valid, 2)
        self.assertEqual(invalid, 5)

    def test_returns_none_when_every_configured_sensor_is_invalid(self):
        average, valid, invalid = models.valid_average(
            [None, "unknown", "unavailable", "bad"], 0, 100
        )
        self.assertIsNone(average)
        self.assertEqual(valid, 0)
        self.assertEqual(invalid, 4)

    def test_pressure_uses_the_same_average_contract(self):
        average, _, _ = models.valid_average([1000, 1020], 800, 1200)
        self.assertEqual(average, 1010)


class PerceivedTemperatureTests(unittest.TestCase):
    def test_missing_optional_inputs_uses_temperature(self):
        self.assertEqual(models.perceived_temperature(25), 25)

    def test_pressure_correction_matches_existing_behavior(self):
        self.assertEqual(models.perceived_temperature(25, pressure=993.25), 25.1)

    def test_high_heat_and_humidity_uses_heat_index(self):
        self.assertGreater(models.perceived_temperature(30, humidity=70), 30)


class DewPointTests(unittest.TestCase):
    def test_calculates_known_room_dew_point(self):
        self.assertAlmostEqual(models.dew_point_celsius(24, 44), 11, delta=0.15)

    def test_converts_dew_point_back_to_relative_humidity(self):
        self.assertAlmostEqual(
            models.relative_humidity_for_dew_point(24, 11), 44, delta=0.2
        )

    def test_rejects_missing_or_invalid_humidity(self):
        self.assertIsNone(models.dew_point_celsius(24, None))
        self.assertIsNone(models.dew_point_celsius(24, 0))

    def test_dew_point_target_is_bounded_by_advertised_humidity(self):
        low = models.bounded_dew_point(32, 9, 30, 45)
        high = models.bounded_dew_point(18, 13, 30, 45)
        self.assertAlmostEqual(
            models.relative_humidity_for_dew_point(32, low), 30, delta=0.2
        )
        self.assertAlmostEqual(
            models.relative_humidity_for_dew_point(18, high), 45, delta=0.2
        )


class ThermalDecisionTests(unittest.TestCase):
    def test_cool_is_idle_below_target(self):
        decision = models.thermal_decision("cool", 25, 26, 0.2, False)
        self.assertEqual((decision.action, decision.command), ("idle", None))

    def test_cool_turns_on_above_upper_boundary(self):
        decision = models.thermal_decision("cool", 26.3, 26, 0.2, False)
        self.assertEqual((decision.action, decision.command), ("cooling", "on"))

    def test_cool_turns_off_at_lower_boundary(self):
        decision = models.thermal_decision("cool", 25.8, 26, 0.2, True)
        self.assertEqual((decision.action, decision.command), ("idle", "off"))

    def test_heat_turns_on_below_lower_boundary(self):
        decision = models.thermal_decision("heat", 20.7, 21, 0.2, False)
        self.assertEqual((decision.action, decision.command), ("heating", "on"))

    def test_heat_activation_at_twenty_six_with_target_twenty_three_stays_idle(self):
        decision = models.thermal_decision("heat", 26, 23, 0.2, False)
        self.assertEqual((decision.action, decision.command), ("idle", None))

    def test_heat_turns_off_at_upper_boundary(self):
        decision = models.thermal_decision("heat", 21.2, 21, 0.2, True)
        self.assertEqual((decision.action, decision.command), ("idle", "off"))

    def test_missing_temperature_never_generates_command(self):
        decision = models.thermal_decision("cool", None, 26, 0.2, False)
        self.assertEqual((decision.action, decision.command), ("unknown", None))


class DryDecisionTests(unittest.TestCase):
    def test_turns_on_above_target_dew_point_and_hysteresis(self):
        decision = models.dry_decision(26, 50, False, 11, 1, True)
        self.assertEqual((decision.action, decision.command), ("drying", "on"))

    def test_turns_off_at_target_dew_point(self):
        target_humidity = models.relative_humidity_for_dew_point(24, 11)
        decision = models.dry_decision(24, target_humidity, True, 11, 1, True)
        self.assertEqual((decision.action, decision.command), ("idle", "off"))

    def test_respects_minimum_interval(self):
        decision = models.dry_decision(26, 70, False, 11, 1, False)
        self.assertIsNone(decision.command)

    def test_suspends_without_real_humidity(self):
        decision = models.dry_decision(26, None, False, 11, 1, True)
        self.assertEqual((decision.action, decision.command), ("unknown", None))

    def test_suspends_without_temperature(self):
        decision = models.dry_decision(None, 50, False, 11, 1, True)
        self.assertEqual((decision.action, decision.command), ("unknown", None))


class PowerFeedbackTests(unittest.TestCase):
    def test_validated_three_state_thresholds(self):
        self.assertEqual(models.classify_power(49.9, 50, 200), "off")
        self.assertEqual(models.classify_power(50, 50, 200), "starting")
        self.assertEqual(models.classify_power(200, 50, 200), "starting")
        self.assertEqual(models.classify_power(200.1, 50, 200), "on")

    def test_invalid_power_is_unknown(self):
        self.assertEqual(models.classify_power("unavailable", 50, 200), "unknown")

    def test_starting_or_on_confirms_an_on_command(self):
        self.assertTrue(models.power_target_reached("starting", True))
        self.assertTrue(models.power_target_reached("on", True))

    def test_only_off_confirms_an_off_command(self):
        self.assertTrue(models.power_target_reached("off", False))
        self.assertFalse(models.power_target_reached("starting", False))
        self.assertFalse(models.power_target_reached("on", False))
        self.assertFalse(models.power_target_reached("unknown", False))


class PersistenceTests(unittest.TestCase):
    def test_first_start_is_off_with_home_targets(self):
        defaults = {
            "cool": models.ModeState(26, "home"),
            "heat": models.ModeState(21, "home"),
        }
        state = models.PersistedState.from_dict({}, defaults, "cool")
        self.assertEqual(state.hvac_mode, "off")
        self.assertFalse(state.physical_on)
        self.assertEqual(state.modes["cool"].target, 26)
        self.assertEqual(state.modes["heat"].target, 21)

    def test_invalid_saved_mode_falls_back_to_off(self):
        defaults = {"heat": models.ModeState(21, "home")}
        state = models.PersistedState.from_dict(
            {"hvac_mode": "unsupported", "last_thermal_mode": "cool"},
            defaults,
            "heat",
        )
        self.assertEqual(state.hvac_mode, "off")
        self.assertEqual(state.last_thermal_mode, "heat")


class DefaultsTests(unittest.TestCase):
    def test_agreed_shared_defaults(self):
        self.assertEqual(const.DEFAULTS[const.OPT_HYSTERESIS], 0.2)
        self.assertEqual(const.DEFAULTS[const.OPT_TEMP_STEP], 0.1)
        self.assertEqual(const.DEFAULTS["preset_sleep_cool"], 26.2)
        self.assertEqual(const.DEFAULTS[const.OPT_POWER_OFF_BELOW], 50)
        self.assertEqual(const.DEFAULTS[const.OPT_POWER_ON_ABOVE], 200)
        self.assertEqual(const.DEFAULTS[const.OPT_STARTUP_DELAY], 15)
        self.assertEqual(const.DEFAULTS[const.OPT_MIN_HUMIDITY], 30)
        self.assertEqual(const.DEFAULTS[const.OPT_MAX_HUMIDITY], 45)
        self.assertEqual(const.DEFAULTS["preset_comfort_dry"], 9)
        self.assertEqual(const.DEFAULTS["preset_home_dry"], 11)


if __name__ == "__main__":
    unittest.main()
