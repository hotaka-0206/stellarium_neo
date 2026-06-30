from pathlib import Path
import os
import re
import shutil



# Stellariumの小惑星データ保存先
# C:\Users\huraf\AppData\Roaming\Stellarium\data\ssystem_minor.ini
SSYSTEM_MINOR_PATH = Path(os.environ["APPDATA"]) / "Stellarium" / "data" / "ssystem_minor.ini"


def make_stellarium_section(section_id, display_name, elements, minor_planet_number):
    """
    JPL Horizonsから取得した軌道要素を
    Stellariumの ssystem_minor.ini 用の小惑星形式に変換する
    """

    return f"""
[{section_id}]
absolute_magnitude             = 19.7
albedo                         = 0.23
minor_planet_number            = {minor_planet_number}
name                           = {display_name}
orbit_ArgOfPericenter          = {elements["argument_of_perihelion_deg"]}
orbit_AscendingNode            = {elements["ascending_node_deg"]}
orbit_Eccentricity             = {elements["eccentricity"]}
orbit_Epoch                    = {elements["epoch_jd_tdb"]}
orbit_Inclination              = {elements["inclination_deg"]}
orbit_MeanAnomaly              = {elements["mean_anomaly_deg"]}
orbit_MeanMotion               = {elements["mean_motion_deg_per_day"]}
orbit_SemiMajorAxis            = {elements["semi_major_axis_au"]}
radius                         = 1
slope_parameter                = 0.15
type                           = asteroid
"""


def save_to_stellarium(section_id, section_text):
    """
    ssystem_minor.ini に軌道要素を書き込む。
    同じ section_id が既にあれば置き換える。
    なければ末尾に追加する。
    """

    SSYSTEM_MINOR_PATH.parent.mkdir(parents=True, exist_ok=True)

    if SSYSTEM_MINOR_PATH.exists():
        original_text = SSYSTEM_MINOR_PATH.read_text(encoding="utf-8", errors="ignore")
    else:
        original_text = ""

    # 念のためバックアップを作る
    if SSYSTEM_MINOR_PATH.exists():
        backup_path = SSYSTEM_MINOR_PATH.with_suffix(".ini.bak")
        shutil.copy2(SSYSTEM_MINOR_PATH, backup_path)
        print(f"バックアップを作成しました: {backup_path}")

    # [section_id] から次の [別セクション] の直前までを探す
    pattern = rf"\n?\[{re.escape(section_id)}\]\n.*?(?=\n\[|\Z)"

    if re.search(pattern, original_text, re.DOTALL):
        new_text = re.sub(
            pattern,
            "\n" + section_text.strip() + "\n",
            original_text,
            flags=re.DOTALL
        )
        print(f"既存の [{section_id}] を置き換えました。")
    else:
        new_text = original_text.rstrip() + "\n\n" + section_text.strip() + "\n"
        print(f"新しく [{section_id}] を追加しました。")

    SSYSTEM_MINOR_PATH.write_text(new_text, encoding="utf-8")
    print(f"書き込み完了: {SSYSTEM_MINOR_PATH}")


def make_section_id(display_name):
    """
    Stellariumのセクション名用に、表示名を安全な文字にする。
    例: JPL_Apophis -> jpl_apophis
    """
    return (
        display_name.lower()
        .replace(" ", "_")
        .replace("(", "")
        .replace(")", "")
    )