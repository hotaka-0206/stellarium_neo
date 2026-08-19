from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import csv
import re
import unicodedata

import requests

from observer import ObserverLocation

HORIZONS_API_URL = "https://ssd.jpl.nasa.gov/api/horizons.api"
SBDB_API_URL = "https://ssd-api.jpl.nasa.gov/sbdb.api"

JAPANESE_ALIASES = {
    "アポフィス": "Apophis",
    "ケレス": "Ceres",
    "セレス": "Ceres",
    "エロス": "Eros",
    "イトカワ": "Itokawa",
    "リュウグウ": "Ryugu",
    "ベンヌ": "Bennu",
}

RADEC_STEP_SECONDS = 0.5
MAX_RADEC_DURATION = timedelta(hours=12)
RADEC_CHUNK_DURATION = timedelta(hours=1)
RADEC_REQUEST_TIMEOUT_SECONDS = 120

_HORIZONS_MONTHS = {
    "Jan": 1,
    "Feb": 2,
    "Mar": 3,
    "Apr": 4,
    "May": 5,
    "Jun": 6,
    "Jul": 7,
    "Aug": 8,
    "Sep": 9,
    "Oct": 10,
    "Nov": 11,
    "Dec": 12,
}


class TargetResolutionError(ValueError):
    pass


class JplApiError(RuntimeError):
    pass


class AmbiguousTargetError(TargetResolutionError):
    def __init__(self, identifier: str, candidates: list[dict]):
        self.identifier = identifier
        self.candidates = candidates
        names = ", ".join(
            candidate.get("name") or candidate.get("pdes", "")
            for candidate in candidates
        )
        super().__init__(f"識別子 '{identifier}' は複数の天体に一致しました: {names}")


@dataclass(frozen=True)
class TargetIdentity:
    user_input: str
    normalized_input: str
    primary_designation: str
    short_name: str
    full_name: str
    spk_id: str
    kind: str
    minor_planet_number: str | None
    iau_designation: str | None
    horizons_command: str
    section_id: str
    default_display_name: str
    absolute_magnitude: float | None
    albedo: float | None
    slope_parameter: float | None

    @property
    def is_asteroid(self) -> bool:
        return self.kind.startswith("a")


@dataclass(frozen=True)
class TopocentricRaDec:
    ra_deg: float
    dec_deg: float
    datetime_utc: datetime
    observer: ObserverLocation
    coordinate_frame: str = "icrf_apparent_airless"


@dataclass(frozen=True)
class RaDecSample:
    ra_deg: float
    dec_deg: float
    datetime_utc: datetime


@dataclass(frozen=True)
class TopocentricRaDecSeries:
    points: tuple[RaDecSample, ...]
    observer: ObserverLocation
    start_datetime_utc: datetime
    end_datetime_utc: datetime
    step_seconds: float = RADEC_STEP_SECONDS
    coordinate_frame: str = "icrf_apparent_airless"

    @property
    def point_count(self) -> int:
        return len(self.points)

    @property
    def duration_seconds(self) -> float:
        return (self.end_datetime_utc - self.start_datetime_utc).total_seconds()


def normalize_user_identifier(identifier: str) -> str:
    value = unicodedata.normalize("NFKC", identifier).strip()

    if not value:
        raise TargetResolutionError("天体の識別子が空です。")

    value = JAPANESE_ALIASES.get(value, value)

    if value.upper().startswith("DES="):
        value = value[4:].strip()

    value = value.rstrip(";").strip()
    value = re.sub(r"\s+", " ", value)

    if not value:
        raise TargetResolutionError("天体の識別子が空です。")

    return value


def _safe_id(value: str) -> str:
    safe = re.sub(r"[^0-9A-Za-z]+", "_", value).strip("_").lower()
    return safe or "unknown"


def _default_display_name(short_name: str, primary_designation: str) -> str:
    name = re.sub(r"^\d+\s+", "", short_name).strip()
    name = name.strip("()")

    if not name:
        name = primary_designation

    name = re.sub(r"\s+", "_", name)
    name = re.sub(r"[^0-9A-Za-z_\-]", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    return f"JPL_{name or _safe_id(primary_designation)}"


def build_horizons_command(
    primary_designation: str,
    minor_planet_number: str | None,
) -> str:
    if minor_planet_number is not None:
        return f"{minor_planet_number};"

    return f"DES={primary_designation};"


def _to_float(value) -> float | None:
    if value in {None, ""}:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _physical_parameters(payload: dict) -> dict[str, float | None]:
    result = {
        "absolute_magnitude": None,
        "albedo": None,
        "slope_parameter": None,
    }

    for item in payload.get("phys_par") or []:
        name = str(item.get("name", "")).lower()
        value = _to_float(item.get("value"))

        if name == "h":
            result["absolute_magnitude"] = value
        elif name == "albedo":
            result["albedo"] = value
        elif name == "g":
            result["slope_parameter"] = value

    return result


def resolve_small_body(identifier: str) -> TargetIdentity:
    normalized = normalize_user_identifier(identifier)

    if normalized.isdigit() and int(normalized) >= 2_000_000:
        params = {"spk": normalized, "phys-par": "1", "no-orbit": "1"}
    else:
        params = {"sstr": normalized, "phys-par": "1", "no-orbit": "1"}

    try:
        response = requests.get(SBDB_API_URL, params=params, timeout=30)
        response.raise_for_status()
        payload = response.json()
    except requests.exceptions.RequestException as error:
        raise JplApiError(f"JPL SBDB APIへの接続に失敗しました: {error}") from error
    except ValueError as error:
        raise JplApiError("JPL SBDB APIのJSONを読み取れませんでした。") from error

    if payload.get("list"):
        raise AmbiguousTargetError(identifier, payload["list"])

    obj = payload.get("object")

    if not obj:
        message = payload.get("message") or payload.get("error") or "天体が見つかりません。"
        raise TargetResolutionError(f"識別子 '{identifier}' を解決できませんでした: {message}")

    primary_designation = str(obj.get("des") or "").strip()
    short_name = str(obj.get("shortname") or primary_designation).strip()
    full_name = str(obj.get("fullname") or short_name).strip()
    spk_id = str(obj.get("spkid") or "").strip()
    kind = str(obj.get("kind") or "").strip().lower()

    if not primary_designation:
        raise TargetResolutionError("JPLから主名称を取得できませんでした。")

    minor_planet_number = (
        primary_designation
        if kind.startswith("a") and primary_designation.isdigit()
        else None
    )
    iau_designation = None if minor_planet_number else primary_designation
    command = build_horizons_command(primary_designation, minor_planet_number)
    section_key = minor_planet_number or primary_designation
    physical = _physical_parameters(payload)

    return TargetIdentity(
        user_input=identifier,
        normalized_input=normalized,
        primary_designation=primary_designation,
        short_name=short_name,
        full_name=full_name,
        spk_id=spk_id,
        kind=kind,
        minor_planet_number=minor_planet_number,
        iau_designation=iau_designation,
        horizons_command=command,
        section_id=f"jpl_{_safe_id(section_key)}",
        default_display_name=_default_display_name(short_name, primary_designation),
        absolute_magnitude=physical["absolute_magnitude"],
        albedo=physical["albedo"],
        slope_parameter=physical["slope_parameter"],
    )


def _request_horizons_text(
    params: dict,
    timeout_seconds: float = 30,
) -> str:
    try:
        response = requests.get(
            HORIZONS_API_URL,
            params=params,
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as error:
        raise JplApiError(f"JPL Horizons APIへの接続に失敗しました: {error}") from error


def fetch_orbital_elements_text(
    horizons_command: str,
    start_time: str,
    stop_time: str,
    step_size: str,
    center: str = "@sun",
) -> str:
    params = {
        "CSV_FORMAT": "YES",
        "format": "text",
        "COMMAND": f"'{horizons_command}'",
        "EPHEM_TYPE": "ELEMENTS",
        "CENTER": f"'{center}'",
        "START_TIME": f"'{start_time}'",
        "STOP_TIME": f"'{stop_time}'",
        "STEP_SIZE": f"'{step_size}'",
        "OBJ_DATA": "YES",
        "OUT_UNITS": "AU-D",
    }
    return _request_horizons_text(params)


def _extract_soe_data_lines(result_text: str) -> list[str]:
    lines = result_text.splitlines()

    try:
        soe_index = lines.index("$$SOE")
        eoe_index = lines.index("$$EOE")
    except ValueError as error:
        detail = next(
            (
                line.strip()
                for line in lines
                if "No matches found" in line
                or "Multiple major-bodies" in line
                or "Matching small-bodies" in line
                or "Cannot interpret date" in line
            ),
            "JPL Horizonsの $$SOE ～ $$EOE がありません。",
        )
        raise ValueError(detail) from error

    data_lines = [
        line.strip()
        for line in lines[soe_index + 1 : eoe_index]
        if line.strip()
    ]

    if not data_lines:
        raise ValueError("JPL Horizonsのデータ行がありません。")

    return data_lines


def extract_orbital_elements_from_soe(result_text: str) -> dict:
    data_lines = _extract_soe_data_lines(result_text)
    values = [value.strip() for value in data_lines[0].split(",")]

    if len(values) < 14:
        raise ValueError(f"軌道要素の列数が足りません: {len(values)}列")

    return {
        "epoch_jd_tdb": float(values[0]),
        "calendar_date_tdb": values[1],
        "eccentricity": float(values[2]),
        "perihelion_distance_au": float(values[3]),
        "inclination_deg": float(values[4]),
        "ascending_node_deg": float(values[5]),
        "argument_of_perihelion_deg": float(values[6]),
        "time_of_perihelion_jd_tdb": float(values[7]),
        "mean_motion_deg_per_day": float(values[8]),
        "mean_anomaly_deg": float(values[9]),
        "true_anomaly_deg": float(values[10]),
        "semi_major_axis_au": float(values[11]),
        "aphelion_distance_au": float(values[12]),
        "period_days": float(values[13]),
    }


def fetch_orbital_elements_from_jpl(
    horizons_command: str,
    start_time: str,
    stop_time: str,
    step_size: str,
    center: str = "@sun",
) -> dict:
    result_text = fetch_orbital_elements_text(
        horizons_command=horizons_command,
        start_time=start_time,
        stop_time=stop_time,
        step_size=step_size,
        center=center,
    )
    return extract_orbital_elements_from_soe(result_text)


def _extract_radec_values_from_data_line(data_line: str) -> tuple[float, float]:
    fields = next(csv.reader([data_line], skipinitialspace=True))
    numeric_values: list[float] = []

    for field in fields[1:]:
        value = field.strip().strip('"')
        try:
            numeric_values.append(float(value))
        except ValueError:
            continue

    if len(numeric_values) < 2:
        raise ValueError("RA/DECの数値列をJPL Horizons出力から取得できませんでした。")

    ra_deg, dec_deg = numeric_values[-2:]

    if not 0.0 <= ra_deg < 360.0:
        raise ValueError(f"RAが範囲外です: {ra_deg}")

    if not -90.0 <= dec_deg <= 90.0:
        raise ValueError(f"DECが範囲外です: {dec_deg}")

    return ra_deg, dec_deg


def _parse_horizons_datetime_utc(value: str) -> datetime:
    text = value.strip().strip('"')

    if text.startswith("A.D."):
        text = text[4:].strip()
    elif text.startswith("B.C."):
        raise ValueError("B.C.のHorizons日時は現在のRA/DEC処理では未対応です。")

    match = re.fullmatch(
        r"(\d{1,4})-([A-Za-z]{3})-(\d{1,2})\s+"
        r"(\d{1,2}):(\d{2}):(\d{2})(?:\.(\d+))?",
        text,
    )

    if match is None:
        raise ValueError(f"Horizonsの日時を読み取れませんでした: {value}")

    year_text, month_text, day_text, hour_text, minute_text, second_text, fraction = (
        match.groups()
    )
    month = _HORIZONS_MONTHS.get(month_text.title())

    if month is None:
        raise ValueError(f"Horizonsの月表記を読み取れませんでした: {month_text}")

    microsecond = int(((fraction or "") + "000000")[:6])

    return datetime(
        year=int(year_text),
        month=month,
        day=int(day_text),
        hour=int(hour_text),
        minute=int(minute_text),
        second=int(second_text),
        microsecond=microsecond,
        tzinfo=timezone.utc,
    )


def _extract_radec_sample_from_data_line(data_line: str) -> RaDecSample:
    fields = next(csv.reader([data_line], skipinitialspace=True))

    if not fields:
        raise ValueError("RA/DECのデータ行が空です。")

    dt_utc = _parse_horizons_datetime_utc(fields[0])
    ra_deg, dec_deg = _extract_radec_values_from_data_line(data_line)

    return RaDecSample(
        ra_deg=ra_deg,
        dec_deg=dec_deg,
        datetime_utc=dt_utc,
    )


def extract_radec_from_soe(result_text: str) -> tuple[float, float]:
    data_line = _extract_soe_data_lines(result_text)[0]
    return _extract_radec_values_from_data_line(data_line)


def extract_radec_samples_from_soe(result_text: str) -> tuple[RaDecSample, ...]:
    return tuple(
        _extract_radec_sample_from_data_line(line)
        for line in _extract_soe_data_lines(result_text)
    )


def fetch_topocentric_radec_text(
    horizons_command: str,
    dt: datetime,
    observer: ObserverLocation,
) -> str:
    if dt.tzinfo is None:
        raise ValueError("日時にはUTCまたはJSTのタイムゾーンが必要です。")

    dt_utc = dt.astimezone(timezone.utc)
    timestamp = dt_utc.strftime("%Y-%b-%d %H:%M:%S")
    params = {
        "format": "text",
        "COMMAND": f"'{horizons_command}'",
        "OBJ_DATA": "NO",
        "MAKE_EPHEM": "YES",
        "EPHEM_TYPE": "OBSERVER",
        "CENTER": "'coord@399'",
        "COORD_TYPE": "'GEODETIC'",
        "SITE_COORD": f"'{observer.to_horizons_site_coord()}'",
        "TLIST": f"'{timestamp}'",
        "TLIST_TYPE": "'CAL'",
        "TIME_TYPE": "'UT'",
        "TIME_DIGITS": "'SECONDS'",
        "QUANTITIES": "'45'",
        "REF_SYSTEM": "'ICRF'",
        "ANG_FORMAT": "'DEG'",
        "APPARENT": "'AIRLESS'",
        "CSV_FORMAT": "'YES'",
        "EXTRA_PREC": "'YES'",
    }
    return _request_horizons_text(params)


def fetch_topocentric_radec(
    horizons_command: str,
    dt: datetime,
    observer: ObserverLocation,
) -> TopocentricRaDec:
    result_text = fetch_topocentric_radec_text(
        horizons_command=horizons_command,
        dt=dt,
        observer=observer,
    )
    ra_deg, dec_deg = extract_radec_from_soe(result_text)

    return TopocentricRaDec(
        ra_deg=ra_deg,
        dec_deg=dec_deg,
        datetime_utc=dt.astimezone(timezone.utc),
        observer=observer,
    )

def _to_horizons_fractional_time(dt: datetime) -> str:
    dt_utc = dt.astimezone(timezone.utc)
    return dt_utc.strftime("%Y-%b-%d %H:%M:%S.%f")[:-3]


def validate_radec_time_range(
    start_dt: datetime,
    end_dt: datetime,
) -> tuple[datetime, datetime, int]:
    if start_dt.tzinfo is None or end_dt.tzinfo is None:
        raise ValueError("開始日時と終了日時にはUTCまたはJSTのタイムゾーンが必要です。")

    start_utc = start_dt.astimezone(timezone.utc)
    end_utc = end_dt.astimezone(timezone.utc)

    if end_utc <= start_utc:
        raise ValueError("終了日時は開始日時より後にしてください。")

    duration = end_utc - start_utc

    if duration > MAX_RADEC_DURATION:
        raise ValueError("RA/DECの取得範囲は最大12時間です。")

    interval_count_float = duration.total_seconds() / RADEC_STEP_SECONDS
    interval_count = round(interval_count_float)

    if abs(interval_count_float - interval_count) > 1e-9:
        raise ValueError("開始日時から終了日時までの長さは0.5秒の倍数にしてください。")

    return start_utc, end_utc, interval_count


def calculate_radec_point_count(start_dt: datetime, end_dt: datetime) -> int:
    _, _, interval_count = validate_radec_time_range(start_dt, end_dt)
    return interval_count + 1


def fetch_topocentric_radec_span_text(
    horizons_command: str,
    start_dt: datetime,
    end_dt: datetime,
    observer: ObserverLocation,
) -> str:
    start_utc, end_utc, interval_count = validate_radec_time_range(
        start_dt,
        end_dt,
    )

    params = {
        "format": "text",
        "COMMAND": f"'{horizons_command}'",
        "OBJ_DATA": "NO",
        "MAKE_EPHEM": "YES",
        "EPHEM_TYPE": "OBSERVER",
        "CENTER": "'coord@399'",
        "COORD_TYPE": "'GEODETIC'",
        "SITE_COORD": f"'{observer.to_horizons_site_coord()}'",
        "START_TIME": f"'{_to_horizons_fractional_time(start_utc)}'",
        "STOP_TIME": f"'{_to_horizons_fractional_time(end_utc)}'",
        # unitless STEP_SIZE = START_TIME～STOP_TIMEを何分割するか。
        # 0.5秒固定なので「区間秒数 / 0.5」を指定する。
        "STEP_SIZE": f"'{interval_count}'",
        "TIME_TYPE": "'UT'",
        "TIME_DIGITS": "'FRACSEC'",
        "QUANTITIES": "'45'",
        "REF_SYSTEM": "'ICRF'",
        "ANG_FORMAT": "'DEG'",
        "APPARENT": "'AIRLESS'",
        "CSV_FORMAT": "'YES'",
        "EXTRA_PREC": "'YES'",
    }
    return _request_horizons_text(
        params,
        timeout_seconds=RADEC_REQUEST_TIMEOUT_SECONDS,
    )


def fetch_topocentric_radec_series(
    horizons_command: str,
    start_dt: datetime,
    end_dt: datetime,
    observer: ObserverLocation,
) -> TopocentricRaDecSeries:
    start_utc, end_utc, _ = validate_radec_time_range(start_dt, end_dt)
    all_points: list[RaDecSample] = []
    chunk_start = start_utc

    while chunk_start < end_utc:
        chunk_end = min(chunk_start + RADEC_CHUNK_DURATION, end_utc)
        result_text = fetch_topocentric_radec_span_text(
            horizons_command=horizons_command,
            start_dt=chunk_start,
            end_dt=chunk_end,
            observer=observer,
        )
        chunk_points = list(extract_radec_samples_from_soe(result_text))

        if not chunk_points:
            raise ValueError("JPL HorizonsからRA/DEC系列を取得できませんでした。")

        if all_points and chunk_points[0].datetime_utc == all_points[-1].datetime_utc:
            chunk_points = chunk_points[1:]

        all_points.extend(chunk_points)
        chunk_start = chunk_end

    expected_count = calculate_radec_point_count(start_utc, end_utc)

    if len(all_points) != expected_count:
        raise ValueError(
            "JPL Horizonsから取得したRA/DEC点数が想定と一致しません。"
            f" 想定={expected_count}, 実際={len(all_points)}"
        )

    if all_points[0].datetime_utc != start_utc:
        raise ValueError(
            "JPL Horizonsの先頭時刻が指定した開始日時と一致しません。"
        )

    if all_points[-1].datetime_utc != end_utc:
        raise ValueError(
            "JPL Horizonsの末尾時刻が指定した終了日時と一致しません。"
        )

    return TopocentricRaDecSeries(
        points=tuple(all_points),
        observer=observer,
        start_datetime_utc=start_utc,
        end_datetime_utc=end_utc,
    )

