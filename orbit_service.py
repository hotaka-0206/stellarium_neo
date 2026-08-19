from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from threading import Event
from collections.abc import Callable
import time

from get_orbit import (
    RADEC_STEP_SECONDS,
    TargetIdentity,
    TopocentricRaDec,
    TopocentricRaDecSeries,
    calculate_radec_point_count,
    fetch_orbital_elements_from_jpl,
    fetch_topocentric_radec,
    fetch_topocentric_radec_series,
    resolve_small_body,
    validate_radec_time_range,
)
from jpl_to_stel import (
    SaveResult,
    StellariumObject,
    find_object_by_section_id,
    find_standard_object_by_minor_planet_number,
    make_stellarium_section,
    save_to_stellarium,
)
from observer import ObserverLocation
from stellarium_service import (
    RaDecMarkerStyle,
    clear_radec_markers,
    focus_object,
    get_stellarium_datetime_utc,
    restart_stellarium,
    set_fov_deg,
    set_observer_location,
    set_time,
    set_view_radec_icrf,
    show_radec_marker,
    start_stellarium,
    verify_observer_location,
)


DEFAULT_RADEC_TRACK_UPDATE_INTERVAL_SECONDS = 0.1
TRACKING_TIME_TOLERANCE_SECONDS = 0.002
TRACKING_TIME_CHANGE_EPSILON_SECONDS = 0.001


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


class TrackingEndReason(str, Enum):
    RANGE_END = "range_end"
    STOP_REQUESTED = "stop_requested"


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


@dataclass(frozen=True)
class PreparedRaDecTarget:
    identity: TargetIdentity
    position: TopocentricRaDec


@dataclass(frozen=True)
class RaDecDisplayResult:
    source: str
    identity: TargetIdentity
    position: TopocentricRaDec
    datetime_utc: datetime
    observer: ObserverLocation


@dataclass(frozen=True)
class RaDecRequestSummary:
    start_datetime_utc: datetime
    end_datetime_utc: datetime
    duration_seconds: float
    step_seconds: float
    point_count: int


@dataclass(frozen=True)
class PreparedRaDecSeriesTarget:
    identity: TargetIdentity
    series: TopocentricRaDecSeries


@dataclass(frozen=True)
class RaDecSeriesDisplayResult:
    source: str
    identity: TargetIdentity
    series: TopocentricRaDecSeries
    datetime_utc: datetime
    observer: ObserverLocation


@dataclass(frozen=True)
class RaDecTrackingResult:
    source: str
    identity: TargetIdentity
    reason: TrackingEndReason
    update_count: int
    last_datetime_utc: datetime | None
    observer: ObserverLocation


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


def prepare_jpl_radec_target(
    identifier: str,
    dt: datetime,
    observer: ObserverLocation,
) -> PreparedRaDecTarget:
    if dt.tzinfo is None:
        raise ValueError("日時にはUTCまたはJSTのタイムゾーンが必要です。")

    identity = resolve_small_body(identifier)

    if not identity.is_asteroid:
        raise UnsupportedTargetTypeError(
            f"{identity.full_name} は小惑星ではありません。"
        )

    position = fetch_topocentric_radec(
        horizons_command=identity.horizons_command,
        dt=dt,
        observer=observer,
    )

    return PreparedRaDecTarget(
        identity=identity,
        position=position,
    )


def get_radec_request_summary(
    start_dt: datetime,
    end_dt: datetime,
) -> RaDecRequestSummary:
    start_utc, end_utc, _ = validate_radec_time_range(start_dt, end_dt)

    return RaDecRequestSummary(
        start_datetime_utc=start_utc,
        end_datetime_utc=end_utc,
        duration_seconds=(end_utc - start_utc).total_seconds(),
        step_seconds=RADEC_STEP_SECONDS,
        point_count=calculate_radec_point_count(start_utc, end_utc),
    )


def prepare_jpl_radec_series_target(
    identifier: str,
    start_dt: datetime,
    end_dt: datetime,
    observer: ObserverLocation,
) -> PreparedRaDecSeriesTarget:
    if start_dt.tzinfo is None or end_dt.tzinfo is None:
        raise ValueError("開始日時と終了日時にはUTCまたはJSTのタイムゾーンが必要です。")

    identity = resolve_small_body(identifier)

    if not identity.is_asteroid:
        raise UnsupportedTargetTypeError(
            f"{identity.full_name} は小惑星ではありません。"
        )

    series = fetch_topocentric_radec_series(
        horizons_command=identity.horizons_command,
        start_dt=start_dt,
        end_dt=end_dt,
        observer=observer,
    )

    return PreparedRaDecSeriesTarget(
        identity=identity,
        series=series,
    )


def _display_radec_marker_position(
    identity: TargetIdentity,
    ra_deg: float,
    dec_deg: float,
    dt: datetime,
    observer: ObserverLocation,
    fov_deg: float,
    marker_style: RaDecMarkerStyle | None,
) -> None:
    start_stellarium()
    set_observer_location(observer)
    verify_observer_location(observer)
    set_time(dt)
    time.sleep(0.5)
    set_view_radec_icrf(ra_deg, dec_deg)
    set_fov_deg(fov_deg)
    show_radec_marker(
        ra_deg=ra_deg,
        dec_deg=dec_deg,
        label=identity.default_display_name,
        style=marker_style,
    )


def display_jpl_radec_target(
    prepared: PreparedRaDecTarget,
    fov_deg: float = 30,
    marker_style: RaDecMarkerStyle | None = None,
) -> RaDecDisplayResult:
    position = prepared.position

    _display_radec_marker_position(
        identity=prepared.identity,
        ra_deg=position.ra_deg,
        dec_deg=position.dec_deg,
        dt=position.datetime_utc,
        observer=position.observer,
        fov_deg=fov_deg,
        marker_style=marker_style,
    )

    return RaDecDisplayResult(
        source="jpl_radec",
        identity=prepared.identity,
        position=position,
        datetime_utc=position.datetime_utc,
        observer=position.observer,
    )


def show_jpl_radec_target(
    identifier: str,
    dt: datetime,
    observer: ObserverLocation,
    fov_deg: float = 30,
    marker_style: RaDecMarkerStyle | None = None,
) -> RaDecDisplayResult:
    prepared = prepare_jpl_radec_target(
        identifier=identifier,
        dt=dt,
        observer=observer,
    )
    return display_jpl_radec_target(
        prepared,
        fov_deg=fov_deg,
        marker_style=marker_style,
    )

def display_jpl_radec_series_start(
    prepared: PreparedRaDecSeriesTarget,
    fov_deg: float = 30,
    marker_style: RaDecMarkerStyle | None = None,
) -> RaDecSeriesDisplayResult:
    if not prepared.series.points:
        raise OrbitServiceError("表示するRA/DEC系列が空です。")

    first = prepared.series.points[0]

    _display_radec_marker_position(
        identity=prepared.identity,
        ra_deg=first.ra_deg,
        dec_deg=first.dec_deg,
        dt=first.datetime_utc,
        observer=prepared.series.observer,
        fov_deg=fov_deg,
        marker_style=marker_style,
    )

    return RaDecSeriesDisplayResult(
        source="jpl_radec_series",
        identity=prepared.identity,
        series=prepared.series,
        datetime_utc=first.datetime_utc,
        observer=prepared.series.observer,
    )


def show_jpl_radec_series(
    identifier: str,
    start_dt: datetime,
    end_dt: datetime,
    observer: ObserverLocation,
    fov_deg: float = 30,
    marker_style: RaDecMarkerStyle | None = None,
) -> RaDecSeriesDisplayResult:
    prepared = prepare_jpl_radec_series_target(
        identifier=identifier,
        start_dt=start_dt,
        end_dt=end_dt,
        observer=observer,
    )
    return display_jpl_radec_series_start(
        prepared,
        fov_deg=fov_deg,
        marker_style=marker_style,
    )


def interpolate_radec_series(
    series: TopocentricRaDecSeries,
    dt: datetime,
) -> TopocentricRaDec | None:
    if dt.tzinfo is None:
        raise ValueError(
            "補間時刻にはUTCまたはJSTのタイムゾーンが必要です。"
        )

    if not series.points:
        raise OrbitServiceError("補間するRA/DEC系列が空です。")

    dt_utc = dt.astimezone(timezone.utc)
    start_utc = series.start_datetime_utc
    end_utc = series.end_datetime_utc
    tolerance = timedelta(seconds=TRACKING_TIME_TOLERANCE_SECONDS)

    if dt_utc < start_utc - tolerance or dt_utc > end_utc + tolerance:
        return None

    if dt_utc < start_utc:
        dt_utc = start_utc
    elif dt_utc > end_utc:
        dt_utc = end_utc

    elapsed_seconds = (dt_utc - start_utc).total_seconds()
    duration_seconds = (end_utc - start_utc).total_seconds()

    if elapsed_seconds >= duration_seconds:
        last = series.points[-1]
        return TopocentricRaDec(
            ra_deg=last.ra_deg,
            dec_deg=last.dec_deg,
            datetime_utc=dt_utc,
            observer=series.observer,
            coordinate_frame=series.coordinate_frame,
        )

    position = elapsed_seconds / series.step_seconds
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(series.points) - 1)
    fraction = position - lower_index

    lower = series.points[lower_index]
    upper = series.points[upper_index]

    ra_delta = ((upper.ra_deg - lower.ra_deg + 180.0) % 360.0) - 180.0
    ra_deg = (lower.ra_deg + ra_delta * fraction) % 360.0
    dec_deg = lower.dec_deg + (upper.dec_deg - lower.dec_deg) * fraction

    return TopocentricRaDec(
        ra_deg=ra_deg,
        dec_deg=dec_deg,
        datetime_utc=dt_utc,
        observer=series.observer,
        coordinate_frame=series.coordinate_frame,
    )


def _wait_tracking_interval(
    update_interval_seconds: float,
    stop_event: Event | None,
) -> bool:
    if stop_event is None:
        time.sleep(update_interval_seconds)
        return False

    return stop_event.wait(update_interval_seconds)


def track_jpl_radec_series(
    displayed: RaDecSeriesDisplayResult,
    update_interval_seconds: float = DEFAULT_RADEC_TRACK_UPDATE_INTERVAL_SECONDS,
    marker_style: RaDecMarkerStyle | None = None,
    follow_view: bool = False,
    stop_event: Event | None = None,
    clear_marker_on_exit: bool = True,
    on_update: Callable[[int, datetime | None], None] | None = None,
) -> RaDecTrackingResult:
    if update_interval_seconds <= 0:
        raise ValueError("マーカー更新間隔は0より大きい値にしてください。")

    series = displayed.series

    if not series.points:
        raise OrbitServiceError("追尾するRA/DEC系列が空です。")

    last_simulation_time = displayed.datetime_utc
    last_position_time: datetime | None = displayed.datetime_utc
    marker_visible = True
    update_count = 0
    end_reason: TrackingEndReason | None = None

    try:
        while True:
            if stop_event is not None and stop_event.is_set():
                end_reason = TrackingEndReason.STOP_REQUESTED
                break

            current_dt = get_stellarium_datetime_utc()

            # 取得範囲外へ出ても追尾ループ自体は終了しない。
            # マーカーだけを非表示にして監視を続けることで、
            # Stellariumの時刻を取得範囲内へ戻したときに再表示できる。
            position = interpolate_radec_series(series, current_dt)

            if position is None:
                if marker_visible:
                    clear_radec_markers()
                    marker_visible = False
                last_simulation_time = current_dt
            else:
                simulation_time_changed = (
                    last_simulation_time is None
                    or abs(
                        (current_dt - last_simulation_time).total_seconds()
                    )
                    >= TRACKING_TIME_CHANGE_EPSILON_SECONDS
                )

                if simulation_time_changed or not marker_visible:
                    if follow_view:
                        set_view_radec_icrf(
                            position.ra_deg,
                            position.dec_deg,
                        )

                    show_radec_marker(
                        ra_deg=position.ra_deg,
                        dec_deg=position.dec_deg,
                        label=displayed.identity.default_display_name,
                        style=marker_style,
                    )

                    marker_visible = True
                    update_count += 1
                    last_position_time = position.datetime_utc

                    if on_update is not None:
                        on_update(update_count, last_position_time)

                last_simulation_time = current_dt

            if _wait_tracking_interval(update_interval_seconds, stop_event):
                end_reason = TrackingEndReason.STOP_REQUESTED
                break

    except BaseException:
        if clear_marker_on_exit:
            try:
                clear_radec_markers()
            except Exception:
                pass
        raise

    if clear_marker_on_exit:
        clear_radec_markers()

    if end_reason is None:
        end_reason = TrackingEndReason.STOP_REQUESTED

    return RaDecTrackingResult(
        source="jpl_radec_tracking",
        identity=displayed.identity,
        reason=end_reason,
        update_count=update_count,
        last_datetime_utc=last_position_time,
        observer=displayed.observer,
    )

