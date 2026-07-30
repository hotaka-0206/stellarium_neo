from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
import time

from get_orbit import (
    TargetIdentity,
    fetch_orbital_elements_from_jpl,
    resolve_small_body,
)
from jpl_to_stel import (
    SaveResult,
    StellariumObject,
    find_object_by_section_id,
    find_standard_object_by_minor_planet_number,
    make_stellarium_section,
    save_to_stellarium,
)
from stellarium_service import (
    focus_object,
    restart_stellarium,
    set_fov_deg,
    set_time,
    start_stellarium,
)


class FetchMode(str, Enum):
    AUTO = "auto"
    FORCE = "force"
    NEVER = "never"


class OrbitServiceError(RuntimeError):
    pass


class UnsupportedTargetTypeError(OrbitServiceError):
    pass


class TargetNotRegisteredError(OrbitServiceError):
    pass


@dataclass(frozen=True)
class JplTargetStatus:
    identity: TargetIdentity
    existing_object: StellariumObject | None

    @property
    def is_registered(self) -> bool:
        return self.existing_object is not None


@dataclass(frozen=True)
class PreparedTarget:
    source: str
    focus_target: str
    display_name: str
    catalog_changed: bool
    identity: TargetIdentity | None = None
    save_result: SaveResult | None = None


@dataclass(frozen=True)
class DisplayResult:
    source: str
    focus_target: str
    display_name: str
    datetime_utc: datetime
    catalog_changed: bool
    section_id: str | None


def to_horizons_time(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise ValueError("日時にはUTCまたはJSTのタイムゾーンが必要です。")

    return dt.astimezone(timezone.utc).strftime("%Y-%b-%d %H:%M")


def inspect_jpl_target(identifier: str) -> JplTargetStatus:
    identity = resolve_small_body(identifier)

    if not identity.is_asteroid:
        raise UnsupportedTargetTypeError(
            f"{identity.full_name} は小惑星ではありません。"
            "現在のStellarium登録形式は小惑星のみ対応しています。"
        )

    return JplTargetStatus(
        identity=identity,
        existing_object=find_object_by_section_id(identity.section_id),
    )


def prepare_jpl_target(
    identifier: str,
    dt: datetime,
    fetch_mode: FetchMode | str = FetchMode.AUTO,
    display_name: str | None = None,
) -> PreparedTarget:
    if dt.tzinfo is None:
        raise ValueError("日時にはUTCまたはJSTのタイムゾーンが必要です。")

    mode = FetchMode(fetch_mode)
    status = inspect_jpl_target(identifier)
    identity = status.identity
    existing = status.existing_object

    if mode is FetchMode.NEVER and existing is None:
        raise TargetNotRegisteredError(
            f"{identity.full_name} のJPL版はまだ登録されていません。"
        )

    should_fetch = mode is FetchMode.FORCE or (
        mode is FetchMode.AUTO and existing is None
    )
    selected_name = (
        display_name.strip()
        if display_name is not None and display_name.strip()
        else existing.name if existing is not None
        else identity.default_display_name
    )
    save_result = None

    if should_fetch:
        dt_utc = dt.astimezone(timezone.utc)
        elements = fetch_orbital_elements_from_jpl(
            horizons_command=identity.horizons_command,
            start_time=to_horizons_time(dt_utc),
            stop_time=to_horizons_time(dt_utc + timedelta(minutes=1)),
            step_size="1 m",
        )
        section_text = make_stellarium_section(
            section_id=identity.section_id,
            display_name=selected_name,
            elements=elements,
            minor_planet_number=identity.minor_planet_number,
            iau_designation=identity.iau_designation,
            absolute_magnitude=identity.absolute_magnitude,
            albedo=identity.albedo,
            slope_parameter=identity.slope_parameter,
        )
        save_result = save_to_stellarium(
            section_id=identity.section_id,
            section_text=section_text,
            old_section_id=existing.section_id if existing else None,
        )

    if identity.minor_planet_number:
        focus_target = f"({identity.minor_planet_number}) {selected_name}"
    else:
        focus_target = selected_name

    return PreparedTarget(
        source="jpl",
        focus_target=focus_target,
        display_name=selected_name,
        catalog_changed=should_fetch,
        identity=identity,
        save_result=save_result,
    )


def prepare_standard_target(target: str) -> PreparedTarget:
    value = target.strip()

    if not value:
        raise ValueError("Stellarium標準天体の入力が空です。")

    if not value.isdigit():
        return PreparedTarget(
            source="standard",
            focus_target=value,
            display_name=value,
            catalog_changed=False,
        )

    standard_object = find_standard_object_by_minor_planet_number(value)

    if standard_object is None:
        raise TargetNotRegisteredError(
            f"天体番号 {value} のStellarium標準版が見つかりません。"
        )

    return PreparedTarget(
        source="standard",
        focus_target=f"({value}) {standard_object.name}",
        display_name=standard_object.name,
        catalog_changed=False,
    )


def display_prepared_target(
    prepared: PreparedTarget,
    dt: datetime,
    fov_deg: float = 30,
) -> DisplayResult:
    if prepared.catalog_changed:
        restart_stellarium()
    else:
        start_stellarium()

    set_time(dt)
    time.sleep(1)
    focus_object(prepared.focus_target)
    time.sleep(1)
    set_fov_deg(fov_deg)

    return DisplayResult(
        source=prepared.source,
        focus_target=prepared.focus_target,
        display_name=prepared.display_name,
        datetime_utc=dt.astimezone(timezone.utc),
        catalog_changed=prepared.catalog_changed,
        section_id=(
            prepared.identity.section_id
            if prepared.identity is not None
            else None
        ),
    )


def show_jpl_target(
    identifier: str,
    dt: datetime,
    fetch_mode: FetchMode | str = FetchMode.AUTO,
    display_name: str | None = None,
    fov_deg: float = 30,
) -> DisplayResult:
    prepared = prepare_jpl_target(
        identifier=identifier,
        dt=dt,
        fetch_mode=fetch_mode,
        display_name=display_name,
    )
    return display_prepared_target(prepared, dt, fov_deg)


def show_standard_target(
    target: str,
    dt: datetime,
    fov_deg: float = 30,
) -> DisplayResult:
    prepared = prepare_standard_target(target)
    return display_prepared_target(prepared, dt, fov_deg)
