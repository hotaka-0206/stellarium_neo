import csv
import io
import requests

HORIZONS_API_URL = "https://ssd.jpl.nasa.gov/api/horizons.api"

def fetch_orbital_elements_from_jpl(
    command: str = "99942;",
    start_time: str = "2026-06-18",
    stop_time: str = "2026-06-19",
    step_size: str = "'1 d'",
) -> dict:
    
    params = {
        "format": "json",
        "COMMAND": command,
        "OBJ_DATA": "NO",
        "MAKE_EPHEM": "YES",
        "EPHEM_TYPE": "ELEMENTS",
        "CENTER": "500@10",        # 太陽中心
        "START_TIME": start_time,
        "STOP_TIME": stop_time,
        "STEP_SIZE": step_size,
        "REF_PLANE": "ECLIPTIC",   # 黄道面基準
        "REF_SYSTEM": "ICRF",
        "OUT_UNITS": "AU-D",       # AUと日
        "CSV_FORMAT": "YES",
    }

    response = requests.get(HORIZONS_API_URL, params=params, timeout=20)
    response.raise_for_status()

    data = response.json()

    if "result" not in data:
        raise RuntimeError(f"Horizonsの応答にresultがありません: {data}")

    result_text = data["result"]

    # Horizonsの表は $$SOE と $$EOE の間に出る
    table_text = _extract_horizons_table(result_text)

    # CSVとして読む
    fieldnames = [
    "JDTDB",
    "Calendar Date (TDB)",
    "EC",
    "QR",
    "IN",
    "OM",
    "W",
    "Tp",
    "N",
    "MA",
    "TA",
    "A",
    "AD",
    "PR",
    ]
    rows = list(csv.DictReader(io.StringIO(table_text), fieldnames=fieldnames))

    if not rows:
        raise RuntimeError("軌道要素の表を読み取れませんでした。")

    # 今回は最初の1行だけ使う
    row = rows[0]

    # HorizonsのELEMENTSでよく出る列:
    # JDTDB, Calendar Date (TDB), EC, QR, IN, OM, W, Tp, N, MA, TA, A, AD, PR
    elements = {
        "epoch_jd_tdb": float(row["JDTDB"]),
        "calendar_date_tdb": row["Calendar Date (TDB)"].strip(),

        # 軌道要素
        "eccentricity": float(row["EC"]),          # e
        "perihelion_distance_au": float(row["QR"]), # q
        "inclination_deg": float(row["IN"]),       # i
        "ascending_node_deg": float(row["OM"]),    # Ω
        "argument_of_perihelion_deg": float(row["W"]), # ω
        "time_of_perihelion_jd_tdb": float(row["Tp"]),
        "mean_motion_deg_per_day": float(row["N"]),
        "mean_anomaly_deg": float(row["MA"]),
        "true_anomaly_deg": float(row["TA"]),
        "semi_major_axis_au": float(row["A"]),
        "aphelion_distance_au": float(row["AD"]),
        "period_days": float(row["PR"]),
    }

    return elements


def _extract_horizons_table(result_text: str) -> str:
    """
    Horizons出力の $$SOE ～ $$EOE の間だけ取り出す。
    """
    start_marker = "$$SOE"
    end_marker = "$$EOE"

    if start_marker not in result_text or end_marker not in result_text:
        raise RuntimeError(
            "Horizons出力から $$SOE ～ $$EOE の表を見つけられませんでした。\n"
            "天体指定が曖昧、またはAPI応答がエラーの可能性があります。"
        )

    table_part = result_text.split(start_marker, 1)[1].split(end_marker, 1)[0]
    table_part = table_part.strip()

    return table_part