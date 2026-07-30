from dataclasses import dataclass
import re
import unicodedata

import requests

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

    try:
        response = requests.get(HORIZONS_API_URL, params=params, timeout=30)
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as error:
        raise JplApiError(f"JPL Horizons APIへの接続に失敗しました: {error}") from error


def extract_orbital_elements_from_soe(result_text: str) -> dict:
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
        raise ValueError("軌道要素のデータ行がありません。")

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
