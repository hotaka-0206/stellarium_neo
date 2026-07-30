from dataclasses import dataclass
import os
import platform
import re
import shutil
from pathlib import Path


@dataclass(frozen=True)
class StellariumObject:
    section_id: str
    name: str
    minor_planet_number: str | None
    iau_designation: str | None


@dataclass(frozen=True)
class SaveResult:
    path: Path
    backup_path: Path | None
    replaced: bool


def get_ssystem_minor_path() -> Path:
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


def make_stellarium_section(
    section_id: str,
    display_name: str,
    elements: dict,
    minor_planet_number: str | None = None,
    iau_designation: str | None = None,
    absolute_magnitude: float | None = None,
    albedo: float | None = None,
    slope_parameter: float | None = None,
) -> str:
    lines = [
        f"[{section_id}]",
        f"absolute_magnitude             = {absolute_magnitude if absolute_magnitude is not None else 20.0}",
        f"albedo                         = {albedo if albedo is not None else 0.15}",
    ]

    if iau_designation:
        lines.append(f"iau_designation               = {iau_designation}")

    if minor_planet_number:
        lines.append(f"minor_planet_number            = {minor_planet_number}")

    lines.extend(
        [
            f"name                           = {display_name}",
            f"orbit_ArgOfPericenter          = {elements['argument_of_perihelion_deg']}",
            f"orbit_AscendingNode            = {elements['ascending_node_deg']}",
            f"orbit_Eccentricity             = {elements['eccentricity']}",
            f"orbit_Epoch                    = {elements['epoch_jd_tdb']}",
            f"orbit_Inclination              = {elements['inclination_deg']}",
            f"orbit_MeanAnomaly              = {elements['mean_anomaly_deg']}",
            f"orbit_MeanMotion               = {elements['mean_motion_deg_per_day']}",
            f"orbit_SemiMajorAxis            = {elements['semi_major_axis_au']}",
            "radius                         = 1",
            f"slope_parameter                = {slope_parameter if slope_parameter is not None else 0.15}",
            "type                           = asteroid",
        ]
    )

    return "\n".join(lines) + "\n"


def _read_value(section_body: str, key: str) -> str | None:
    match = re.search(
        rf"^{re.escape(key)}\s*=\s*(.+)$",
        section_body,
        re.MULTILINE,
    )
    return match.group(1).strip() if match else None


def read_objects() -> list[StellariumObject]:
    if not SSYSTEM_MINOR_PATH.exists():
        return []

    text = SSYSTEM_MINOR_PATH.read_text(encoding="utf-8", errors="ignore")
    pattern = r"\[([^\]]+)\]\r?\n(.*?)(?=\r?\n\[|\Z)"
    objects = []

    for match in re.finditer(pattern, text, re.DOTALL):
        section_id = match.group(1).strip()
        section_body = match.group(2)
        name = _read_value(section_body, "name")

        if name is None:
            continue

        objects.append(
            StellariumObject(
                section_id=section_id,
                name=name,
                minor_planet_number=_read_value(
                    section_body,
                    "minor_planet_number",
                ),
                iau_designation=_read_value(section_body, "iau_designation"),
            )
        )

    return objects


def is_jpl_object(obj: StellariumObject) -> bool:
    return obj.section_id.lower().startswith("jpl_")


def find_object_by_section_id(section_id: str) -> StellariumObject | None:
    target = section_id.strip().lower()

    for obj in read_objects():
        if obj.section_id.lower() == target:
            return obj

    return None


def find_jpl_object_by_minor_planet_number(
    minor_planet_number: str,
) -> StellariumObject | None:
    number = str(minor_planet_number).strip()

    for obj in read_objects():
        if obj.minor_planet_number == number and is_jpl_object(obj):
            return obj

    return None


def find_standard_object_by_minor_planet_number(
    minor_planet_number: str,
) -> StellariumObject | None:
    number = str(minor_planet_number).strip()

    for obj in read_objects():
        if (
            obj.minor_planet_number == number
            and not is_jpl_object(obj)
            and not obj.name.lower().startswith("jpl_")
        ):
            return obj

    return None


def remove_section(text: str, section_id: str) -> str:
    pattern = rf"\r?\n?\[{re.escape(section_id)}\]\r?\n.*?(?=\r?\n\[|\Z)"
    return re.sub(pattern, "\n", text, flags=re.DOTALL)


def save_to_stellarium(
    section_id: str,
    section_text: str,
    old_section_id: str | None = None,
) -> SaveResult:
    SSYSTEM_MINOR_PATH.parent.mkdir(parents=True, exist_ok=True)
    backup_path = None

    if SSYSTEM_MINOR_PATH.exists():
        original_text = SSYSTEM_MINOR_PATH.read_text(
            encoding="utf-8",
            errors="ignore",
        )
        backup_path = SSYSTEM_MINOR_PATH.with_suffix(".ini.bak")
        shutil.copy2(SSYSTEM_MINOR_PATH, backup_path)
    else:
        original_text = ""

    new_text = original_text

    if old_section_id and old_section_id != section_id:
        new_text = remove_section(new_text, old_section_id)

    pattern = rf"\r?\n?\[{re.escape(section_id)}\]\r?\n.*?(?=\r?\n\[|\Z)"
    replaced = bool(re.search(pattern, new_text, re.DOTALL))

    if replaced:
        new_text = re.sub(
            pattern,
            "\n" + section_text.strip() + "\n",
            new_text,
            flags=re.DOTALL,
        )
    else:
        new_text = new_text.rstrip() + "\n\n" + section_text.strip() + "\n"

    SSYSTEM_MINOR_PATH.write_text(new_text, encoding="utf-8")

    return SaveResult(
        path=SSYSTEM_MINOR_PATH,
        backup_path=backup_path,
        replaced=replaced,
    )
