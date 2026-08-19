import json
import math
from dataclasses import dataclass
import platform
import subprocess
import time
from datetime import datetime, timezone

import requests

from observer import ObserverLocation

BASE_URL = "http://localhost:8090/api"


class StellariumError(RuntimeError):
    pass


class StellariumApiError(StellariumError):
    pass


def get_stellarium_exe_path() -> str:
    if platform.system() == "Windows":
        return r"C:\Program Files\Stellarium\stellarium.exe"
    if platform.system() == "Darwin":
        return "/Applications/Stellarium.app/Contents/MacOS/Stellarium"
    return "stellarium"


STELLARIUM_PATH = get_stellarium_exe_path()


MARKER_TYPES = frozenset({
    "cross",
    "circle",
    "ellipse",
    "square",
    "dotted-circle",
    "circled-cross",
    "circled-plus",
    "dashed-square",
    "squared-dotted-circle",
    "squared-dcircle",
    "crossed-circle",
    "target",
    "gear",
    "disk",
})

LABEL_SIDES = frozenset({"N", "S", "E", "W", "NE", "NW", "SE", "SW"})


@dataclass(frozen=True)
class RaDecMarkerStyle:
    marker_type: str = "circled-cross"
    marker_size_px: float = 14.0
    color: str = "#ffcc00"
    label_font_size_px: float = 16.0
    label_side: str = "NE"
    label_distance_px: float = 36.0

    def __post_init__(self) -> None:
        marker_type = self.marker_type.strip().lower()
        label_side = self.label_side.strip().upper()
        color = self.color.strip()

        if marker_type not in MARKER_TYPES:
            raise ValueError(
                f"未対応のマーカー形状です: {self.marker_type}"
            )

        if label_side not in LABEL_SIDES:
            raise ValueError(
                f"未対応のラベル方向です: {self.label_side}"
            )

        if not color.startswith("#") or len(color) != 7:
            raise ValueError(
                "色は #RRGGBB 形式で指定してください。"
            )

        numeric_values = {
            "マーカーサイズ": self.marker_size_px,
            "ラベル文字サイズ": self.label_font_size_px,
            "ラベル距離": self.label_distance_px,
        }
        for label, value in numeric_values.items():
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{label}は正の有限値で指定してください。")

        object.__setattr__(self, "marker_type", marker_type)
        object.__setattr__(self, "label_side", label_side)
        object.__setattr__(self, "color", color)


@dataclass(frozen=True)
class StellariumTimeState:
    datetime_utc: datetime
    julian_day: float
    timerate: float
    is_time_now: bool


def to_julian_day(dt: datetime) -> float:
    if dt.tzinfo is None:
        raise ValueError("日時にはUTCまたはJSTのタイムゾーンが必要です。")

    dt = dt.astimezone(timezone.utc)
    y = dt.year
    m = dt.month
    d = dt.day
    h = (
        dt.hour
        + dt.minute / 60
        + (dt.second + dt.microsecond / 1_000_000) / 3600
    )

    if m <= 2:
        y -= 1
        m += 12

    a = y // 100
    b = 2 - a + a // 4

    return (
        int(365.25 * (y + 4716))
        + int(30.6001 * (m + 1))
        + d
        + h / 24
        + b
        - 1524.5
    )


def julian_day_to_datetime_utc(julian_day: float) -> datetime:
    if not math.isfinite(julian_day):
        raise ValueError("ユリウス日は有限の数値で指定してください。")

    unix_epoch_jd = 2440587.5
    unix_seconds = (julian_day - unix_epoch_jd) * 86400.0

    try:
        return datetime.fromtimestamp(unix_seconds, tz=timezone.utc)
    except (OverflowError, OSError, ValueError) as error:
        raise ValueError(
            f"ユリウス日をUTC日時へ変換できませんでした: {julian_day}"
        ) from error


def radec_to_unit_vector(ra_deg: float, dec_deg: float) -> tuple[float, float, float]:
    if not 0.0 <= ra_deg < 360.0:
        raise ValueError("RAは 0以上360未満の度数で指定してください。")
    if not -90.0 <= dec_deg <= 90.0:
        raise ValueError("DECは -90～90 度で指定してください。")

    ra_rad = math.radians(ra_deg)
    dec_rad = math.radians(dec_deg)
    cos_dec = math.cos(dec_rad)

    return (
        cos_dec * math.cos(ra_rad),
        cos_dec * math.sin(ra_rad),
        math.sin(dec_rad),
    )


def is_stellarium_running() -> bool:
    try:
        response = requests.get(f"{BASE_URL}/main/status", timeout=2)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False


def stop_stellarium() -> None:
    if not is_stellarium_running():
        return

    if platform.system() == "Windows":
        subprocess.run(
            ["taskkill", "/IM", "stellarium.exe", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        subprocess.run(
            ["pkill", "-f", STELLARIUM_PATH],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )

    for _ in range(20):
        if not is_stellarium_running():
            return
        time.sleep(0.5)

    raise StellariumError("Stellariumを終了できませんでした。")


def start_stellarium() -> None:
    if is_stellarium_running():
        return

    try:
        subprocess.Popen([STELLARIUM_PATH])
    except OSError as error:
        raise StellariumError(
            f"Stellariumを起動できませんでした: {STELLARIUM_PATH}"
        ) from error

    for _ in range(40):
        if is_stellarium_running():
            return
        time.sleep(0.5)

    raise StellariumError(
        "StellariumのRemote Control APIに接続できませんでした。"
    )


def restart_stellarium() -> None:
    stop_stellarium()
    start_stellarium()


def _post_with_retry(
    endpoint: str,
    data: dict,
    retry: int,
    interval: float,
) -> None:
    last_detail = "応答なし"

    for _ in range(retry):
        try:
            response = requests.post(
                f"{BASE_URL}{endpoint}",
                data=data,
                timeout=5,
            )
            last_detail = f"status={response.status_code}, body={response.text}"

            if (
                response.status_code == 200
                and response.text.strip().lower() != "false"
            ):
                return
        except requests.exceptions.RequestException as error:
            last_detail = str(error)

        time.sleep(interval)

    raise StellariumApiError(
        f"Stellarium API {endpoint} の実行に失敗しました: {last_detail}"
    )


def get_status() -> dict:
    try:
        response = requests.get(f"{BASE_URL}/main/status", timeout=5)
        response.raise_for_status()
        payload = response.json()
    except requests.exceptions.RequestException as error:
        raise StellariumApiError(
            f"Stellariumの状態取得に失敗しました: {error}"
        ) from error
    except ValueError as error:
        raise StellariumApiError(
            "Stellariumの状態応答をJSONとして読み取れませんでした。"
        ) from error

    if not isinstance(payload, dict):
        raise StellariumApiError("Stellariumの状態応答が不正です。")

    return payload


def _parse_stellarium_utc_text(value: str) -> datetime:
    text = value.strip()

    if not text:
        raise ValueError("UTC日時が空です。")

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    dt = datetime.fromisoformat(text)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt.astimezone(timezone.utc)


def get_stellarium_time_state() -> StellariumTimeState:
    time_info = get_status().get("time")

    if not isinstance(time_info, dict):
        raise StellariumApiError(
            "Stellariumの状態応答に時刻情報がありません。"
        )

    try:
        julian_day = float(time_info["jday"])
        timerate = float(time_info.get("timerate", 0.0))
        is_time_now = bool(time_info.get("isTimeNow", False))
    except (KeyError, TypeError, ValueError) as error:
        raise StellariumApiError(
            "Stellariumの時刻情報を数値として読み取れませんでした。"
        ) from error

    utc_text = time_info.get("utc")
    datetime_utc: datetime

    if isinstance(utc_text, str):
        try:
            datetime_utc = _parse_stellarium_utc_text(utc_text)
        except ValueError:
            datetime_utc = julian_day_to_datetime_utc(julian_day)
    else:
        datetime_utc = julian_day_to_datetime_utc(julian_day)

    return StellariumTimeState(
        datetime_utc=datetime_utc,
        julian_day=julian_day,
        timerate=timerate,
        is_time_now=is_time_now,
    )


def get_stellarium_datetime_utc() -> datetime:
    return get_stellarium_time_state().datetime_utc


def get_observer_location() -> dict:
    location = get_status().get("location")

    if not isinstance(location, dict):
        raise StellariumApiError(
            "Stellariumの状態応答に観測地点がありません。"
        )

    return location


def _longitude_difference_deg(first: float, second: float) -> float:
    return abs((first - second + 180.0) % 360.0 - 180.0)


def verify_observer_location(
    observer: ObserverLocation,
    horizontal_tolerance_deg: float = 1e-5,
    altitude_tolerance_m: float = 1.0,
    retry: int = 10,
    interval: float = 0.2,
) -> dict:
    last_location: dict | None = None
    expected_altitude = round(observer.altitude_m)

    for _ in range(retry):
        location = get_observer_location()
        last_location = location

        try:
            latitude = float(location["latitude"])
            longitude = float(location["longitude"])
            altitude = float(location["altitude"])
        except (KeyError, TypeError, ValueError) as error:
            raise StellariumApiError(
                "Stellariumの観測地点情報を"
                "数値として読み取れませんでした。"
            ) from error

        latitude_ok = (
            abs(latitude - observer.latitude_deg)
            <= horizontal_tolerance_deg
        )

        longitude_ok = (
            _longitude_difference_deg(
                longitude,
                observer.longitude_deg,
            )
            <= horizontal_tolerance_deg
        )

        altitude_ok = (
            abs(altitude - expected_altitude)
            <= altitude_tolerance_m
        )

        if latitude_ok and longitude_ok and altitude_ok:
            return location

        time.sleep(interval)

    raise StellariumApiError(
        "Stellariumへ設定した観測地点を確認できませんでした。"
        f" 入力地点=({observer.latitude_deg}, "
        f"{observer.longitude_deg}, "
        f"{observer.altitude_m} m), "
        f"Stellarium地点={last_location}"
    )


def set_time(dt: datetime, retry: int = 20, interval: float = 1.0) -> None:
    _post_with_retry(
        endpoint="/main/time",
        data={"time": to_julian_day(dt), "timerate": 0},
        retry=retry,
        interval=interval,
    )


def set_observer_location(
    observer: ObserverLocation,
    retry: int = 10,
    interval: float = 0.5,
) -> None:
    _post_with_retry(
        endpoint="/location/setlocationfields",
        data={
            "latitude": observer.latitude_deg,
            "longitude": observer.longitude_deg,
            "altitude": round(observer.altitude_m),
            "name": observer.name,
            "planet": "Earth",
        },
        retry=retry,
        interval=interval,
    )


def focus_object(
    target: str,
    retry: int = 20,
    interval: float = 1.0,
) -> None:
    _post_with_retry(
        endpoint="/main/focus",
        data={"target": target, "mode": "zoom"},
        retry=retry,
        interval=interval,
    )


def set_view_radec_icrf(
    ra_deg: float,
    dec_deg: float,
    retry: int = 20,
    interval: float = 0.5,
) -> None:
    vector = radec_to_unit_vector(ra_deg, dec_deg)
    _post_with_retry(
        endpoint="/main/view",
        data={"j2000": json.dumps(vector)},
        retry=retry,
        interval=interval,
    )


def set_fov_deg(
    fov_deg: float,
    retry: int = 10,
    interval: float = 0.5,
) -> None:
    _post_with_retry(
        endpoint="/main/fov",
        data={"fov": fov_deg},
        retry=retry,
        interval=interval,
    )

def degrees_to_ra_text(ra_deg: float) -> str:
    if not 0.0 <= ra_deg < 360.0:
        raise ValueError("RAは 0以上360未満の度数で指定してください。")

    microseconds_per_second = 1_000_000
    microseconds_per_hour = 3600 * microseconds_per_second
    microseconds_per_minute = 60 * microseconds_per_second
    microseconds_per_day = 24 * microseconds_per_hour

    total_microseconds = round(
        ra_deg / 15.0 * 3600.0 * microseconds_per_second
    ) % microseconds_per_day

    hours, remainder = divmod(total_microseconds, microseconds_per_hour)
    minutes, remainder = divmod(remainder, microseconds_per_minute)
    seconds = remainder / microseconds_per_second

    return f"{hours}h{minutes:02d}m{seconds:09.6f}s"


def degrees_to_dec_text(dec_deg: float) -> str:
    if not -90.0 <= dec_deg <= 90.0:
        raise ValueError("DECは -90～90 度で指定してください。")

    sign = "-" if dec_deg < 0 else "+"
    microseconds_per_second = 1_000_000
    microseconds_per_degree = 3600 * microseconds_per_second
    microseconds_per_minute = 60 * microseconds_per_second

    total_microseconds = round(
        abs(dec_deg) * 3600.0 * microseconds_per_second
    )
    degrees, remainder = divmod(total_microseconds, microseconds_per_degree)
    minutes, remainder = divmod(remainder, microseconds_per_minute)
    seconds = remainder / microseconds_per_second

    return f"{sign}{degrees}d{minutes:02d}m{seconds:09.6f}s"


def run_stellarium_script(
    script_code: str,
    retry: int = 3,
    interval: float = 0.2,
) -> str:
    if not script_code.strip():
        raise ValueError("実行するStellariumスクリプトが空です。")

    last_detail = "応答なし"

    for _ in range(retry):
        try:
            response = requests.post(
                f"{BASE_URL}/scripts/direct",
                data={"code": script_code},
                timeout=5,
            )
            body = response.text.strip()
            lower_body = body.lower()
            last_detail = f"status={response.status_code}, body={body}"

            if (
                response.status_code == 200
                and lower_body != "false"
                and not lower_body.startswith("error")
            ):
                return body
        except requests.exceptions.RequestException as error:
            last_detail = str(error)

        time.sleep(interval)

    raise StellariumApiError(
        "Stellariumスクリプトの実行に失敗しました: "
        f"{last_detail}"
    )


def build_radec_marker_script(
    ra_deg: float,
    dec_deg: float,
    label: str,
    style: RaDecMarkerStyle | None = None,
) -> str:
    marker_label = label.strip()

    if not marker_label:
        raise ValueError("マーカーの表示名が空です。")

    marker_style = style or RaDecMarkerStyle()
    ra_text = degrees_to_ra_text(ra_deg)
    dec_text = degrees_to_dec_text(dec_deg)
    label_literal = json.dumps(marker_label, ensure_ascii=False)
    marker_type_literal = json.dumps(marker_style.marker_type)
    color_literal = json.dumps(marker_style.color)
    label_side_literal = json.dumps(marker_style.label_side)

    return "\n".join(
        [
            "MarkerMgr.deleteAllMarkers();",
            "LabelMgr.deleteAllLabels();",
            (
                "var markerId = MarkerMgr.markerEquatorial("
                f'"{ra_text}", "{dec_text}", '
                f"true, true, {marker_type_literal}, {color_literal}, "
                f"{marker_style.marker_size_px}, false, 0, false);"
            ),
            (
                "var labelId = LabelMgr.labelEquatorial("
                f"{label_literal}, "
                f'"{ra_text}", "{dec_text}", '
                f"true, {marker_style.label_font_size_px}, "
                f"{color_literal}, {label_side_literal}, "
                f"{marker_style.label_distance_px}, false, 0, true);"
            ),
            (
                "if (markerId < 0 || labelId < 0) { "
                'throw new Error("RA/DEC marker creation failed"); }'
            ),
        ]
    )


def show_radec_marker(
    ra_deg: float,
    dec_deg: float,
    label: str,
    style: RaDecMarkerStyle | None = None,
) -> None:
    script_code = build_radec_marker_script(
        ra_deg=ra_deg,
        dec_deg=dec_deg,
        label=label,
        style=style,
    )
    run_stellarium_script(script_code)


def clear_radec_markers() -> None:
    run_stellarium_script(
        "MarkerMgr.deleteAllMarkers();\n"
        "LabelMgr.deleteAllLabels();"
    )
