import re
import requests


HORIZONS_API_URL = "https://ssd.jpl.nasa.gov/api/horizons.api"

#APIから取得
def fetch_orbital_elements_text(
    target_id: str,
    start_time: str = "2026-Jun-18",
    stop_time: str = "2026-Jun-19",
    step_size: str = "1 d",
    center: str = "@sun",
) -> str:
    params = {
        "CSV_FORMAT": "YES",
        "format": "text",
        "COMMAND": f"'{target_id}'",
        "EPHEM_TYPE": "ELEMENTS",
        "CENTER": f"'{center}'",
        "START_TIME": f"'{start_time}'",
        "STOP_TIME": f"'{stop_time}'",
        "STEP_SIZE": f"'{step_size}'",
        "OBJ_DATA": "YES",
        "OUT_UNITS": "AU-D",
    }

    response = requests.get(HORIZONS_API_URL, params=params, timeout=30)
    response.raise_for_status()
    return response.text

#パース
def extract_orbital_elements_from_soe(result_text: str) -> dict:
    lines = result_text.splitlines()

    try:
        soe_index = lines.index("$$SOE")
        eoe_index = lines.index("$$EOE")
    except ValueError:
        raise ValueError("JPL Horizonsの $$SOE ～ $$EOE が無い")

    data_lines = [
        line.strip()
        for line in lines[soe_index + 1 : eoe_index]
        if line.strip()
    ]

    if not data_lines:
        raise ValueError("軌道要素のデータ行が無い")

    values = [v.strip() for v in data_lines[0].split(",")]

    if len(values) < 14:
        raise ValueError(f"軌道要素の列数が足りない: {len(values)}列")

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

#まとめ
def fetch_orbital_elements_from_jpl(
    target_id: str,
    start_time: str = "2026-Jun-18",
    stop_time: str = "2026-Jun-19",
    step_size: str = "1 d",
    center: str = "@sun",
) -> dict:
    result_text = fetch_orbital_elements_text(
        target_id=target_id,
        start_time=start_time,
        stop_time=stop_time,
        step_size=step_size,
        center=center,
    )

    return extract_orbital_elements_from_soe(result_text)