from datetime import datetime, timezone
import unittest
from unittest.mock import patch

from get_orbit import (
    build_horizons_command,
    normalize_user_identifier,
    resolve_small_body,
)
from jpl_to_stel import make_stellarium_section
from stellarium_service import to_julian_day


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


APOPHIS_PAYLOAD = {
    "object": {
        "shortname": "99942 Apophis",
        "fullname": "99942 Apophis (2004 MN4)",
        "spkid": "2099942",
        "kind": "an",
        "des": "99942",
    },
    "phys_par": [
        {"name": "H", "value": "19.7"},
        {"name": "albedo", "value": "0.23"},
    ],
}


class IdentifierTests(unittest.TestCase):
    def test_japanese_alias(self):
        self.assertEqual(normalize_user_identifier("アポフィス"), "Apophis")

    def test_semicolon_and_des_are_removed(self):
        self.assertEqual(normalize_user_identifier("DES=2004 MN4;"), "2004 MN4")

    def test_numbered_asteroid_command(self):
        self.assertEqual(build_horizons_command("99942", "99942"), "99942;")

    def test_provisional_designation_command(self):
        self.assertEqual(
            build_horizons_command("2004 MN4", None),
            "DES=2004 MN4;",
        )

    @patch("get_orbit.requests.get", return_value=FakeResponse(APOPHIS_PAYLOAD))
    def test_name_resolves_to_numbered_asteroid(self, mock_get):
        identity = resolve_small_body("Apophis")
        self.assertEqual(identity.minor_planet_number, "99942")
        self.assertEqual(identity.horizons_command, "99942;")
        self.assertEqual(identity.section_id, "jpl_99942")
        self.assertEqual(identity.default_display_name, "JPL_Apophis")
        self.assertEqual(mock_get.call_args.kwargs["params"]["sstr"], "Apophis")

    @patch("get_orbit.requests.get", return_value=FakeResponse(APOPHIS_PAYLOAD))
    def test_spk_id_uses_spk_query(self, mock_get):
        identity = resolve_small_body("2099942")
        self.assertEqual(identity.primary_designation, "99942")
        self.assertEqual(mock_get.call_args.kwargs["params"]["spk"], "2099942")


class StellariumSectionTests(unittest.TestCase):
    def test_unnumbered_asteroid_uses_iau_designation(self):
        elements = {
            "argument_of_perihelion_deg": 1,
            "ascending_node_deg": 2,
            "eccentricity": 0.1,
            "epoch_jd_tdb": 2460000.5,
            "inclination_deg": 3,
            "mean_anomaly_deg": 4,
            "mean_motion_deg_per_day": 5,
            "semi_major_axis_au": 1.2,
        }
        text = make_stellarium_section(
            section_id="jpl_2004_mn4",
            display_name="JPL_Test",
            elements=elements,
            iau_designation="2004 MN4",
        )
        self.assertIn("iau_designation               = 2004 MN4", text)
        self.assertNotIn("minor_planet_number", text)


class JulianDayTests(unittest.TestCase):
    def test_j2000(self):
        dt = datetime(2000, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(to_julian_day(dt), 2451545.0)


if __name__ == "__main__":
    unittest.main()
