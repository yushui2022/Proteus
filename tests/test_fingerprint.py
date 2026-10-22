"""Tests for the fingerprint engine.

Run with no third-party dependencies::

    python -m unittest discover -s tests -v
"""

from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

from proteus.fingerprint import (  # noqa: E402
    FATAL,
    OS_FAMILIES,
    RULE_CODES,
    GeoProfile,
    check,
    derive,
    derive_for_country,
    index_of,
    is_consistent,
)

SEED = 20250922


def mutate(fp, **changes):
    import dataclasses

    return dataclasses.replace(fp, **changes)


class TestDeterminism(unittest.TestCase):
    def test_same_seed_same_fingerprint(self):
        a = derive_for_country(SEED, "DE")
        b = derive_for_country(SEED, "DE")
        self.assertEqual(a, b)

    def test_index_of_is_fixed(self):
        # Pinned values guard against an accidental change of the derivation
        # formula, which would silently re-roll every existing profile.
        self.assertEqual(index_of(20250922, "canvas_noise", 256), 80)
        self.assertEqual(index_of(0, "canvas_noise", 256), 212)

    def test_index_of_rejects_bad_modulus(self):
        with self.assertRaises(ValueError):
            index_of(1, "x", 0)

    def test_different_seeds_differ(self):
        prints = {derive_for_country(seed, "US") for seed in range(50)}
        self.assertGreater(len(prints), 5)

    def test_geo_is_carried_through_not_derived(self):
        de = derive_for_country(SEED, "DE")
        jp = derive_for_country(SEED, "JP")
        self.assertEqual(de.timezone, "Europe/Berlin")
        self.assertEqual(jp.timezone, "Asia/Tokyo")
        self.assertEqual(de.languages[0], "de-DE")
        # Only the geo-derived fields may differ between the two.
        self.assertEqual(de.os_family, jp.os_family)
        self.assertEqual(de.ua, jp.ua)

    def test_seed_validation(self):
        geo = GeoProfile.for_country("US")
        with self.assertRaises(ValueError):
            derive(-1, geo)
        with self.assertRaises(TypeError):
            derive("42", geo)
        with self.assertRaises(ValueError):
            derive(1, geo, os_family="beos")


class TestGeneratedIsConsistent(unittest.TestCase):
    def test_500_seeds_across_all_os(self):
        geo = GeoProfile.for_country("DE")
        for os_family in OS_FAMILIES:
            for seed in range(500):
                fp = derive(seed, geo, os_family=os_family)
                violations = check(fp)
                self.assertEqual(
                    violations, [], f"seed={seed} os={os_family}: {violations}"
                )

    def test_every_country_sample_is_consistent(self):
        for country in ("US", "GB", "DE", "FR", "NL", "JP", "SG", "CN", "BR"):
            fp = derive_for_country(SEED, country)
            self.assertEqual(check(fp), [], country)

    def test_unknown_country_rejected(self):
        with self.assertRaises(ValueError):
            GeoProfile.for_country("ZZ")


class TestRulesCatchContradictions(unittest.TestCase):
    def setUp(self):
        self.fp = derive_for_country(SEED, "US", os_family="windows")

    def codes(self, fp):
        return {v.code for v in check(fp)}

    def test_rule_codes_are_unique(self):
        self.assertEqual(len(RULE_CODES), len(set(RULE_CODES)))

    def test_platform_swap_is_caught(self):
        broken = mutate(self.fp, platform="MacIntel")
        self.assertIn("os.platform_mismatch", self.codes(broken))

    def test_ua_os_swap_is_caught(self):
        broken = mutate(self.fp, ua=self.fp.ua.replace("Windows NT 10.0", "X11; Linux"))
        self.assertIn("os.ua_mismatch", self.codes(broken))

    def test_font_profile_swap_is_caught(self):
        broken = mutate(self.fp, font_profile="macos-sonoma")
        self.assertIn("os.font_profile_mismatch", self.codes(broken))

    def test_webgl_vendor_swap_is_caught(self):
        broken = mutate(self.fp, webgl_vendor="Google Inc. (Apple)")
        self.assertIn("os.webgl_vendor_mismatch", self.codes(broken))

    def test_mac_dpr1_is_caught(self):
        fp = derive_for_country(SEED, "US", os_family="macos")
        self.assertIn("os.dpr_implausible", self.codes(mutate(fp, device_pixel_ratio=1.0)))

    def test_ua_major_drift_is_caught(self):
        broken = mutate(self.fp, ua_major=self.fp.ua_major + 7)
        self.assertIn("ua.major_mismatch", self.codes(broken))

    def test_odd_core_count_is_caught(self):
        self.assertIn("hardware.concurrency_range", self.codes(mutate(self.fp, hardware_concurrency=3)))

    def test_device_memory_overflow_is_caught(self):
        self.assertIn("hardware.device_memory_range", self.codes(mutate(self.fp, device_memory=16)))

    def test_portrait_screen_is_caught(self):
        broken = mutate(self.fp, screen_width=1080, screen_height=1920)
        self.assertIn("screen.geometry", self.codes(broken))

    def test_language_locale_mismatch_is_caught(self):
        geo = GeoProfile(country="DE", timezone="Europe/Berlin", locale="de-DE", languages=("en-US",))
        broken = mutate(self.fp, geo=geo)
        self.assertIn("locale.language_mismatch", self.codes(broken))

    def test_bad_timezone_is_caught(self):
        geo = GeoProfile(country="DE", timezone="Berlin", locale="de-DE", languages=("de-DE",))
        self.assertIn("geo.timezone_format", self.codes(mutate(self.fp, geo=geo)))

    def test_canvas_noise_band_is_caught(self):
        self.assertIn("noise.canvas_range", self.codes(mutate(self.fp, canvas_noise=900)))

    def test_audio_noise_band_is_caught(self):
        self.assertIn("noise.audio_range", self.codes(mutate(self.fp, audio_noise=0.5)))

    def test_unknown_os_family_is_caught(self):
        broken = mutate(self.fp, os_family="beos")
        self.assertIn("os.platform_mismatch", self.codes(broken))

    def test_mismatches_are_fatal(self):
        broken = mutate(self.fp, platform="MacIntel")
        severities = {v.severity for v in check(broken)}
        self.assertEqual(severities, {FATAL})


class TestPublicSurface(unittest.TestCase):
    def test_consistent_fingerprint_helper(self):
        self.assertTrue(is_consistent(derive_for_country(SEED, "JP")))
        self.assertFalse(is_consistent(mutate(derive_for_country(SEED, "JP"), platform="Win32")))

    def test_fingerprint_is_immutable(self):
        fp = derive_for_country(SEED, "US")
        with self.assertRaises(Exception):
            fp.os_family = "linux"


if __name__ == "__main__":
    unittest.main()
