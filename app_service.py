from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, TypeVar

from app_errors import ApplicationError, application_error_from_exception
from observer import ObserverLocation
from orbit_service import (
    DEFAULT_RADEC_TRACK_UPDATE_INTERVAL_SECONDS,
    DisplayResult,
    FetchMode,
    JplTargetStatus,
    RaDecDisplayResult,
    RaDecRequestSummary,
    display_jpl_radec_series_start,
    get_radec_request_summary,
    inspect_jpl_target,
    prepare_jpl_radec_series_target,
    show_jpl_radec_target,
    show_jpl_target,
    show_standard_target,
)
from radec_store import (
    MemoryRaDecSessionStore,
    RaDecSession,
    RaDecSessionStore,
)
from stellarium_service import RaDecMarkerStyle, clear_radec_marker
from tracking_service import RaDecTrackingManager, TrackingStatus


T = TypeVar("T")


@dataclass(frozen=True)
class RaDecSessionInfo:
    session_id: str
    target_full_name: str
    horizons_command: str
    start_datetime_utc: datetime
    end_datetime_utc: datetime
    step_seconds: float
    point_count: int
    observer: ObserverLocation
    created_at_utc: datetime

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "target_full_name": self.target_full_name,
            "horizons_command": self.horizons_command,
            "start_datetime_utc": self.start_datetime_utc.isoformat(),
            "end_datetime_utc": self.end_datetime_utc.isoformat(),
            "step_seconds": self.step_seconds,
            "point_count": self.point_count,
            "observer": {
                "name": self.observer.name,
                "latitude_deg": self.observer.latitude_deg,
                "longitude_deg": self.observer.longitude_deg,
                "altitude_m": self.observer.altitude_m,
            },
            "created_at_utc": self.created_at_utc.isoformat(),
        }


def _session_to_info(session: RaDecSession) -> RaDecSessionInfo:
    return RaDecSessionInfo(
        session_id=session.session_id,
        target_full_name=session.identity.full_name,
        horizons_command=session.identity.horizons_command,
        start_datetime_utc=session.series.start_datetime_utc,
        end_datetime_utc=session.series.end_datetime_utc,
        step_seconds=session.series.step_seconds,
        point_count=session.series.point_count,
        observer=session.series.observer,
        created_at_utc=session.created_at_utc,
    )


class StellariumNeoService:
    """CLI・将来のローカルAPIの両方から呼ぶアプリケーションサービス。"""

    def __init__(
        self,
        store: RaDecSessionStore | None = None,
        tracking_manager: RaDecTrackingManager | None = None,
    ) -> None:
        self.store = store or MemoryRaDecSessionStore()
        self.tracking_manager = (
            tracking_manager
            if tracking_manager is not None
            else RaDecTrackingManager(self.store)
        )

    @staticmethod
    def _call(func: Callable[..., T], *args, **kwargs) -> T:
        try:
            return func(*args, **kwargs)
        except ApplicationError:
            raise
        except Exception as error:
            raise application_error_from_exception(error) from error

    def inspect_target(self, identifier: str) -> JplTargetStatus:
        return self._call(inspect_jpl_target, identifier)

    def show_jpl_orbit_target(
        self,
        identifier: str,
        dt: datetime,
        fetch_mode: FetchMode | str = FetchMode.AUTO,
        display_name: str | None = None,
        fov_deg: float = 30,
    ) -> DisplayResult:
        return self._call(
            show_jpl_target,
            identifier=identifier,
            dt=dt,
            fetch_mode=fetch_mode,
            display_name=display_name,
            fov_deg=fov_deg,
        )

    def show_standard_target(
        self,
        target: str,
        dt: datetime,
        fov_deg: float = 30,
    ) -> DisplayResult:
        return self._call(
            show_standard_target,
            target=target,
            dt=dt,
            fov_deg=fov_deg,
        )

    def show_single_radec_target(
        self,
        identifier: str,
        dt: datetime,
        observer: ObserverLocation,
        fov_deg: float = 30,
        marker_style: RaDecMarkerStyle | None = None,
    ) -> RaDecDisplayResult:
        return self._call(
            show_jpl_radec_target,
            identifier=identifier,
            dt=dt,
            observer=observer,
            fov_deg=fov_deg,
            marker_style=marker_style,
        )

    def get_radec_request_summary(
        self,
        start_dt: datetime,
        end_dt: datetime,
    ) -> RaDecRequestSummary:
        return self._call(
            get_radec_request_summary,
            start_dt,
            end_dt,
        )

    def fetch_radec_session(
        self,
        identifier: str,
        start_dt: datetime,
        end_dt: datetime,
        observer: ObserverLocation,
        fov_deg: float = 30,
        marker_style: RaDecMarkerStyle | None = None,
        display_start: bool = True,
    ) -> RaDecSessionInfo:
        if self.tracking_manager.get_status().is_active:
            raise ApplicationError(
                code="tracking_active",
                message="RA/DEC追尾中は新しい取得を開始できません。先に追尾を停止してください。",
            )

        try:
            prepared = prepare_jpl_radec_series_target(
                identifier=identifier,
                start_dt=start_dt,
                end_dt=end_dt,
                observer=observer,
            )

            if display_start:
                display_jpl_radec_series_start(
                    prepared,
                    fov_deg=fov_deg,
                    marker_style=marker_style,
                )

            session = self.store.save(
                identity=prepared.identity,
                series=prepared.series,
            )
            return _session_to_info(session)
        except ApplicationError:
            raise
        except Exception as error:
            raise application_error_from_exception(error) from error

    def get_current_radec_session(self) -> RaDecSessionInfo | None:
        session = self.store.get_current()
        return _session_to_info(session) if session is not None else None

    def clear_current_radec_session(self) -> None:
        if self.tracking_manager.get_status().is_active:
            raise ApplicationError(
                code="tracking_active",
                message="RA/DEC追尾中は取得セッションを削除できません。",
            )

        try:
            clear_radec_marker()
        except Exception:
            # Stellariumが未起動でもメモリ上のセッションは消せるようにする。
            pass

        self.store.clear()

    def start_tracking(
        self,
        session_id: str | None = None,
        update_interval_seconds: float = DEFAULT_RADEC_TRACK_UPDATE_INTERVAL_SECONDS,
        marker_style: RaDecMarkerStyle | None = None,
        follow_view: bool = False,
    ) -> TrackingStatus:
        return self._call(
            self.tracking_manager.start,
            session_id=session_id,
            update_interval_seconds=update_interval_seconds,
            marker_style=marker_style,
            follow_view=follow_view,
        )

    def stop_tracking(
        self,
        wait_timeout_seconds: float = 2.0,
    ) -> TrackingStatus:
        return self._call(
            self.tracking_manager.stop,
            wait_timeout_seconds=wait_timeout_seconds,
        )

    def get_tracking_status(self) -> TrackingStatus:
        return self.tracking_manager.get_status()
