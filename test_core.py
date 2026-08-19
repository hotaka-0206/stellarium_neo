from datetime import datetime, timedelta, timezone
import math
import unittest
from unittest.mock import patch

from get_orbit import (
    RaDecSample,
    TargetIdentity,
    TopocentricRaDecSeries,
    build_horizons_command,
    calculate_radec_point_count,
    extract_radec_from_soe,
    extract_radec_samples_from_soe,
    fetch_topocentric_radec,
    fetch_topocentric_radec_series,
    normalize_user_identifier,
    resolve_small_body,
    validate_radec_time_range,
)
from jpl_to_stel import make_stellarium_section
from observer import ObserverLocation
from orbit_service import (
    RaDecSeriesDisplayResult,
    RaDecTrackingResult,
    TrackingEndReason,
    interpolate_radec_series,
    track_jpl_radec_series,
)
from stellarium_service import (
    build_clear_radec_marker_script,
    build_radec_marker_script,
    get_stellarium_time_state,
    julian_day_to_datetime_utc,
    radec_to_unit_vector,
    set_view_radec_icrf,
    to_julian_day,
)
from app_errors import ApplicationError
from radec_store import MemoryRaDecSessionStore
from tracking_service import RaDecTrackingManager, TrackingState


class FakeResponse:
    def __init__(self, payload=None, text=""):
        self.payload = payload
        self.text = text
        self.status_code = 200

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

RADEC_RESULT = """Target body name: 99942 Apophis
$$SOE
 2029-Apr-13 00:00:00, , , 151.234567890, -23.456789010,
$$EOE
"""

RADEC_SERIES_RESULT = """Target body name: 99942 Apophis
$$SOE
 2029-Apr-13 00:00:00.000, , , 151.000000000, -23.000000000,
 2029-Apr-13 00:00:00.500, , , 151.100000000, -23.100000000,
 2029-Apr-13 00:00:01.000, , , 151.200000000, -23.200000000,
$$EOE
"""


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

    def test_julian_day_round_trip_keeps_subsecond_time(self):
        dt = datetime(
            2029,
            4,
            13,
            0,
            0,
            0,
            500000,
            tzinfo=timezone.utc,
        )

        restored = julian_day_to_datetime_utc(to_julian_day(dt))
        difference = abs((restored - dt).total_seconds())

        self.assertLess(difference, 0.001)


class StellariumTimeTests(unittest.TestCase):
    @patch("stellarium_service.get_status")
    def test_time_state_uses_jday_as_primary_time(self, mock_get_status):
        expected = datetime(
            2029,
            4,
            13,
            0,
            0,
            0,
            250000,
            tzinfo=timezone.utc,
        )
        mock_get_status.return_value = {
            "time": {
                "jday": to_julian_day(expected),
                # utcが異なる値でも追尾基準には使用しない。
                "utc": "2000-01-01T00:00:00Z",
                "timerate": 1.1574074074074073e-05,
                "isTimeNow": False,
            }
        }

        state = get_stellarium_time_state()
        difference = abs((state.datetime_utc - expected).total_seconds())

        self.assertLess(difference, 0.001)
        self.assertAlmostEqual(
            state.timerate,
            1.1574074074074073e-05,
        )


class ObserverTests(unittest.TestCase):
    def test_horizons_site_coord_uses_km(self):
        observer = ObserverLocation(35.47, 133.05, 50.0, "Matsue")
        self.assertEqual(
            observer.to_horizons_site_coord(),
            "133.0500000000,35.4700000000,0.050000",
        )

    def test_invalid_latitude(self):
        with self.assertRaises(ValueError):
            ObserverLocation(91.0, 133.05)


class RaDecTests(unittest.TestCase):
    def test_extract_decimal_degree_radec(self):
        ra_deg, dec_deg = extract_radec_from_soe(RADEC_RESULT)
        self.assertAlmostEqual(ra_deg, 151.234567890)
        self.assertAlmostEqual(dec_deg, -23.456789010)

    def test_radec_vector_axes(self):
        x, y, z = radec_to_unit_vector(0.0, 0.0)
        self.assertAlmostEqual(x, 1.0)
        self.assertAlmostEqual(y, 0.0)
        self.assertAlmostEqual(z, 0.0)

        x, y, z = radec_to_unit_vector(90.0, 0.0)
        self.assertAlmostEqual(x, 0.0, places=12)
        self.assertAlmostEqual(y, 1.0)
        self.assertAlmostEqual(z, 0.0)

        x, y, z = radec_to_unit_vector(0.0, 90.0)
        self.assertAlmostEqual(x, 0.0, places=12)
        self.assertAlmostEqual(y, 0.0)
        self.assertAlmostEqual(z, 1.0)
        self.assertAlmostEqual(math.sqrt(x * x + y * y + z * z), 1.0)

    @patch("get_orbit.requests.get", return_value=FakeResponse(text=RADEC_RESULT))
    def test_fetch_topocentric_radec_parameters(self, mock_get):
        observer = ObserverLocation(35.47, 133.05, 50.0, "Matsue")
        dt = datetime(2029, 4, 13, 0, 0, 0, tzinfo=timezone.utc)

        result = fetch_topocentric_radec("99942;", dt, observer)

        self.assertAlmostEqual(result.ra_deg, 151.234567890)
        self.assertAlmostEqual(result.dec_deg, -23.456789010)
        params = mock_get.call_args.kwargs["params"]
        self.assertEqual(params["CENTER"], "'coord@399'")
        self.assertEqual(params["QUANTITIES"], "'45'")
        self.assertEqual(
            params["SITE_COORD"],
            "'133.0500000000,35.4700000000,0.050000'",
        )
        self.assertEqual(params["TLIST"], "'2029-Apr-13 00:00:00'")

    def test_extract_radec_series_with_half_second_timestamps(self):
        samples = extract_radec_samples_from_soe(RADEC_SERIES_RESULT)

        self.assertEqual(len(samples), 3)
        self.assertEqual(samples[0].datetime_utc.microsecond, 0)
        self.assertEqual(samples[1].datetime_utc.microsecond, 500000)
        self.assertAlmostEqual(samples[2].ra_deg, 151.2)
        self.assertAlmostEqual(samples[2].dec_deg, -23.2)

    def test_twelve_hour_point_count(self):
        start = datetime(2029, 4, 13, 0, 0, 0, tzinfo=timezone.utc)
        end = start + timedelta(hours=12)

        self.assertEqual(calculate_radec_point_count(start, end), 86401)

    def test_radec_range_can_cross_midnight(self):
        start = datetime(
            2029, 4, 13, 23, 59, 59, 500000, tzinfo=timezone.utc
        )
        end = datetime(2029, 4, 14, 0, 0, 0, 500000, tzinfo=timezone.utc)

        start_utc, end_utc, interval_count = validate_radec_time_range(
            start,
            end,
        )

        self.assertEqual(start_utc, start)
        self.assertEqual(end_utc, end)
        self.assertEqual(interval_count, 2)
        self.assertEqual(calculate_radec_point_count(start, end), 3)

    def test_radec_range_longer_than_twelve_hours_is_rejected(self):
        start = datetime(2029, 4, 13, 0, 0, 0, tzinfo=timezone.utc)
        end = start + timedelta(hours=12, seconds=1)

        with self.assertRaises(ValueError):
            validate_radec_time_range(start, end)

    @patch(
        "get_orbit.requests.get",
        return_value=FakeResponse(text=RADEC_SERIES_RESULT),
    )
    def test_fetch_radec_series_uses_unitless_half_second_step(self, mock_get):
        observer = ObserverLocation(35.4978, 133.025, 0.0, "MatsueKosen")
        start = datetime(2029, 4, 13, 0, 0, 0, tzinfo=timezone.utc)
        end = start + timedelta(seconds=1)

        result = fetch_topocentric_radec_series(
            "99942;",
            start,
            end,
            observer,
        )

        self.assertEqual(result.point_count, 3)
        params = mock_get.call_args.kwargs["params"]
        self.assertEqual(params["START_TIME"], "'2029-Apr-13 00:00:00.000'")
        self.assertEqual(params["STOP_TIME"], "'2029-Apr-13 00:00:01.000'")
        self.assertEqual(params["STEP_SIZE"], "'2'")
        self.assertEqual(params["TIME_DIGITS"], "'FRACSEC'")

    @patch("stellarium_service.requests.post")
    def test_set_view_uses_j2000(self, mock_post):
        mock_post.return_value = FakeResponse(text="ok")

        set_view_radec_icrf(90.0, 0.0, retry=1, interval=0.0)

        data = mock_post.call_args.kwargs["data"]
        self.assertIn("j2000", data)
        self.assertNotIn("jNow", data)


class RaDecTrackingTests(unittest.TestCase):
    def setUp(self):
        self.observer = ObserverLocation(
            35.4978,
            133.025,
            0.0,
            "MatsueKosen",
        )
        self.start = datetime(
            2029,
            4,
            13,
            0,
            0,
            0,
            tzinfo=timezone.utc,
        )

    def _make_series(
        self,
        first_ra: float = 10.0,
        second_ra: float = 20.0,
    ) -> TopocentricRaDecSeries:
        end = self.start + timedelta(seconds=0.5)
        return TopocentricRaDecSeries(
            points=(
                RaDecSample(
                    ra_deg=first_ra,
                    dec_deg=30.0,
                    datetime_utc=self.start,
                ),
                RaDecSample(
                    ra_deg=second_ra,
                    dec_deg=40.0,
                    datetime_utc=end,
                ),
            ),
            observer=self.observer,
            start_datetime_utc=self.start,
            end_datetime_utc=end,
        )

    def _make_identity(self) -> TargetIdentity:
        return TargetIdentity(
            user_input="Apophis",
            normalized_input="Apophis",
            primary_designation="99942",
            short_name="99942 Apophis",
            full_name="99942 Apophis (2004 MN4)",
            spk_id="2099942",
            kind="an",
            minor_planet_number="99942",
            iau_designation=None,
            horizons_command="99942;",
            section_id="jpl_99942",
            default_display_name="JPL_Apophis",
            absolute_magnitude=19.7,
            albedo=0.23,
            slope_parameter=None,
        )

    def test_interpolation_between_half_second_points(self):
        series = self._make_series()
        dt = self.start + timedelta(seconds=0.25)

        position = interpolate_radec_series(series, dt)

        self.assertIsNotNone(position)
        self.assertAlmostEqual(position.ra_deg, 15.0)
        self.assertAlmostEqual(position.dec_deg, 35.0)

    def test_interpolation_handles_ra_wraparound(self):
        series = self._make_series(
            first_ra=359.8,
            second_ra=0.2,
        )
        dt = self.start + timedelta(seconds=0.25)

        position = interpolate_radec_series(series, dt)

        self.assertIsNotNone(position)
        self.assertAlmostEqual(position.ra_deg, 0.0, places=10)

    def test_interpolation_returns_none_outside_range(self):
        series = self._make_series()

        self.assertIsNone(
            interpolate_radec_series(
                series,
                self.start - timedelta(seconds=1),
            )
        )

    @patch("orbit_service._wait_tracking_interval")
    @patch("orbit_service.clear_radec_markers")
    @patch("orbit_service.show_radec_marker")
    @patch("orbit_service.get_stellarium_datetime_utc")
    def test_tracking_hides_outside_range_and_reappears_when_time_returns(
        self,
        mock_get_time,
        mock_show_marker,
        mock_clear_marker,
        mock_wait,
    ):
        series = self._make_series()
        identity = self._make_identity()
        displayed = RaDecSeriesDisplayResult(
            source="jpl_radec_series",
            identity=identity,
            series=series,
            datetime_utc=self.start,
            observer=self.observer,
        )

        # 範囲内 → 終了時刻より後 → 範囲内へ戻す
        mock_get_time.side_effect = [
            self.start + timedelta(seconds=0.25),
            self.start + timedelta(seconds=1.0),
            self.start + timedelta(seconds=0.25),
        ]
        mock_wait.side_effect = [False, False, True]

        result = track_jpl_radec_series(
            displayed,
            update_interval_seconds=0.1,
        )

        self.assertIs(result.reason, TrackingEndReason.STOP_REQUESTED)
        self.assertEqual(result.update_count, 2)
        self.assertEqual(mock_show_marker.call_count, 2)

        first_kwargs = mock_show_marker.call_args_list[0].kwargs
        second_kwargs = mock_show_marker.call_args_list[1].kwargs
        self.assertAlmostEqual(first_kwargs["ra_deg"], 15.0)
        self.assertAlmostEqual(first_kwargs["dec_deg"], 35.0)
        self.assertAlmostEqual(second_kwargs["ra_deg"], 15.0)
        self.assertAlmostEqual(second_kwargs["dec_deg"], 35.0)

        # 範囲外へ出たときに1回、追尾終了時に1回消去する。
        self.assertEqual(mock_clear_marker.call_count, 2)



class ManagedMarkerTests(unittest.TestCase):
    def test_marker_script_only_replaces_stellarium_neo_marker(self):
        script = build_radec_marker_script(
            ra_deg=151.0,
            dec_deg=-23.0,
            label="JPL_Apophis",
        )

        self.assertIn("MarkerMgr.deleteMarker", script)
        self.assertIn("LabelMgr.deleteLabel", script)
        self.assertNotIn("deleteAllMarkers", script)
        self.assertNotIn("deleteAllLabels", script)
        self.assertIn("__stellariumNeoRaDecMarkerId", script)
        self.assertIn("__stellariumNeoRaDecLabelId", script)

    def test_clear_marker_script_only_clears_managed_ids(self):
        script = build_clear_radec_marker_script()

        self.assertIn("MarkerMgr.deleteMarker", script)
        self.assertIn("LabelMgr.deleteLabel", script)
        self.assertNotIn("deleteAllMarkers", script)
        self.assertNotIn("deleteAllLabels", script)


class RaDecStoreTests(unittest.TestCase):
    def _identity(self) -> TargetIdentity:
        return TargetIdentity(
            user_input="Apophis",
            normalized_input="Apophis",
            primary_designation="99942",
            short_name="99942 Apophis",
            full_name="99942 Apophis (2004 MN4)",
            spk_id="2099942",
            kind="an",
            minor_planet_number="99942",
            iau_designation=None,
            horizons_command="99942;",
            section_id="jpl_99942",
            default_display_name="JPL_Apophis",
            absolute_magnitude=19.7,
            albedo=0.23,
            slope_parameter=None,
        )

    def _series(self) -> TopocentricRaDecSeries:
        observer = ObserverLocation(35.4978, 133.025, 0.0, "MatsueKosen")
        start = datetime(2029, 4, 13, 0, 0, tzinfo=timezone.utc)
        end = start + timedelta(seconds=0.5)
        return TopocentricRaDecSeries(
            points=(
                RaDecSample(10.0, 20.0, start),
                RaDecSample(11.0, 21.0, end),
            ),
            observer=observer,
            start_datetime_utc=start,
            end_datetime_utc=end,
        )

    def test_memory_store_keeps_only_current_session(self):
        store = MemoryRaDecSessionStore()
        first = store.save(self._identity(), self._series())
        second = store.save(self._identity(), self._series())

        self.assertIsNone(store.get(first.session_id))
        self.assertEqual(store.get_current().session_id, second.session_id)
        self.assertEqual(store.get(second.session_id).point_count, 2)

        store.clear()
        self.assertIsNone(store.get_current())


class TrackingManagerTests(unittest.TestCase):
    def _identity(self) -> TargetIdentity:
        return TargetIdentity(
            user_input="Apophis",
            normalized_input="Apophis",
            primary_designation="99942",
            short_name="99942 Apophis",
            full_name="99942 Apophis (2004 MN4)",
            spk_id="2099942",
            kind="an",
            minor_planet_number="99942",
            iau_designation=None,
            horizons_command="99942;",
            section_id="jpl_99942",
            default_display_name="JPL_Apophis",
            absolute_magnitude=19.7,
            albedo=0.23,
            slope_parameter=None,
        )

    def _series(self) -> TopocentricRaDecSeries:
        observer = ObserverLocation(35.4978, 133.025, 0.0, "MatsueKosen")
        start = datetime(2029, 4, 13, 0, 0, tzinfo=timezone.utc)
        end = start + timedelta(seconds=0.5)
        return TopocentricRaDecSeries(
            points=(
                RaDecSample(10.0, 20.0, start),
                RaDecSample(11.0, 21.0, end),
            ),
            observer=observer,
            start_datetime_utc=start,
            end_datetime_utc=end,
        )

    @patch("tracking_service.track_jpl_radec_series")
    def test_manager_starts_in_background_and_can_stop(self, mock_track):
        store = MemoryRaDecSessionStore()
        session = store.save(self._identity(), self._series())
        manager = RaDecTrackingManager(store)

        def fake_track(
            displayed,
            update_interval_seconds,
            marker_style,
            follow_view,
            stop_event,
            clear_marker_on_exit,
            on_update,
        ):
            on_update(1, displayed.series.start_datetime_utc)
            stop_event.wait(1.0)
            return RaDecTrackingResult(
                source="jpl_radec_tracking",
                identity=displayed.identity,
                reason=TrackingEndReason.STOP_REQUESTED,
                update_count=1,
                last_datetime_utc=displayed.series.start_datetime_utc,
                observer=displayed.observer,
            )

        mock_track.side_effect = fake_track

        started = manager.start(session_id=session.session_id)
        self.assertEqual(started.state, TrackingState.RUNNING)

        stopped = manager.stop(wait_timeout_seconds=1.0)
        self.assertEqual(stopped.state, TrackingState.STOPPED)
        self.assertEqual(stopped.update_count, 1)

    def test_manager_rejects_missing_session(self):
        manager = RaDecTrackingManager(MemoryRaDecSessionStore())

        with self.assertRaises(ApplicationError) as context:
            manager.start()

        self.assertEqual(context.exception.code, "radec_session_not_found")


class ApplicationErrorTests(unittest.TestCase):
    def test_error_is_ready_for_json_response(self):
        error = ApplicationError(
            code="example_error",
            message="表示用メッセージ",
            details={"field": "value"},
        )

        self.assertEqual(
            error.to_dict(),
            {
                "code": "example_error",
                "message": "表示用メッセージ",
                "details": {"field": "value"},
            },
        )


if __name__ == "__main__":
    unittest.main()
