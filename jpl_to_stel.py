import os
import platform
import re
import shutil
from pathlib import Path


def get_ssystem_minor_path():
    home = Path.home()

    if platform.system() == "Windows":
        appdata = Path(os.environ.get("APPDATA", home / "AppData" / "Roaming"))
        return appdata / "Stellarium" / "data" / "ssystem_minor.ini"

    if platform.system() == "Darwin":
        return (
            home
            / "Library"
            / "Application Support"
            / "Stellarium"
            / "data"
            / "ssystem_minor.ini"
        )

    return home / ".local" / "share" / "Stellarium" / "data" / "ssystem_minor.ini"


SSYSTEM_MINOR_PATH = get_ssystem_minor_path()


def make_stellarium_section(section_id, display_name, elements, minor_planet_number):
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


def read_objects():
    if not SSYSTEM_MINOR_PATH.exists():
        return []

    text = SSYSTEM_MINOR_PATH.read_text(encoding="utf-8", errors="ignore")
    pattern = r"\[([^\]]+)\]\r?\n(.*?)(?=\r?\n\[|\Z)"
    objects = []

    for match in re.finditer(pattern, text, re.DOTALL):
        section_id = match.group(1).strip()
        section_body = match.group(2)

        number_match = re.search(
            r"^minor_planet_number\s*=\s*(.+)$",
            section_body,
            re.MULTILINE,
        )
        name_match = re.search(
            r"^name\s*=\s*(.+)$",
            section_body,
            re.MULTILINE,
        )

        if number_match is None or name_match is None:
            continue

        objects.append(
            {
                "section_id": section_id,
                "minor_planet_number": number_match.group(1).strip(),
                "name": name_match.group(1).strip(),
            }
        )

    return objects


def is_jpl_object(obj):
    return obj["section_id"].lower().startswith("jpl_")


def find_jpl_object_by_minor_planet_number(minor_planet_number):
    number = str(minor_planet_number).strip()

    for obj in read_objects():
        if obj["minor_planet_number"] == number and is_jpl_object(obj):
            return obj

    return None


def find_standard_object_by_minor_planet_number(minor_planet_number):
    number = str(minor_planet_number).strip()

    for obj in read_objects():
        is_jpl_section = obj["section_id"].lower().startswith("jpl_")
        is_jpl_name = obj["name"].lower().startswith("jpl_")

        if (
            obj["minor_planet_number"] == number
            and not is_jpl_section
            and not is_jpl_name
        ):
            return obj

    return None


def remove_section(text, section_id):
    pattern = rf"\r?\n?\[{re.escape(section_id)}\]\r?\n.*?(?=\r?\n\[|\Z)"
    return re.sub(pattern, "\n", text, flags=re.DOTALL)


def save_to_stellarium(section_id, section_text, old_section_id=None):
    SSYSTEM_MINOR_PATH.parent.mkdir(parents=True, exist_ok=True)

    if SSYSTEM_MINOR_PATH.exists():
        original_text = SSYSTEM_MINOR_PATH.read_text(
            encoding="utf-8",
            errors="ignore",
        )
        backup_path = SSYSTEM_MINOR_PATH.with_suffix(".ini.bak")
        shutil.copy2(SSYSTEM_MINOR_PATH, backup_path)
        print(f"バックアップを作成しました: {backup_path}")
    else:
        original_text = ""

    new_text = original_text

    if old_section_id and old_section_id != section_id:
        new_text = remove_section(new_text, old_section_id)

    pattern = rf"\r?\n?\[{re.escape(section_id)}\]\r?\n.*?(?=\r?\n\[|\Z)"

    if re.search(pattern, new_text, re.DOTALL):
        new_text = re.sub(
            pattern,
            "\n" + section_text.strip() + "\n",
            new_text,
            flags=re.DOTALL,
        )
    else:
        new_text = new_text.rstrip() + "\n\n" + section_text.strip() + "\n"

    SSYSTEM_MINOR_PATH.write_text(new_text, encoding="utf-8")
    print(f"書き込み完了: {SSYSTEM_MINOR_PATH}")