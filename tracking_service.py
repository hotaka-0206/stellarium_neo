from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from threading import Event, RLock, Thread

from app_errors import ApplicationError, ErrorInfo, error_info_from_exception
from orbit_service import (
    DEFAULT_RADEC_TRACK_UPDATE_INTERVAL_SECONDS,
    RaDecSeriesDisplayResult,
    track_jpl_radec_series,
)
from radec_store import RaDecSession, RaDecSessionStore
from stellarium_service import RaDecMarkerStyle


class TrackingState(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


@dataclass(frozen=True)
class TrackingStatus:
    state: TrackingState
    session_id: str | None = None
    update_count: int = 0
    last_datetime_utc: datetime | None = None
    started_at_utc: datetime | None = None
    stopped_at_utc: datetime | None = None
    error: ErrorInfo | None = None

    @property
    def is_active(self) -> bool:
        return self.state in {TrackingState.RUNNING, TrackingState.STOPPING}

    def to_dict(self) -> dict:
        return {
            "state": self.state.value,
            "session_id": self.session_id,
            "update_count": self.update_count,
            "last_datetime_utc": (
                self.last_datetime_utc.isoformat()
                if self.last_datetime_utc is not None
                else None
            ),
            "started_at_utc": (
                self.started_at_utc.isoformat()
                if self.started_at_utc is not None
                else None
            ),
            "stopped_at_utc": (
                self.stopped_at_utc.isoformat()
                if self.stopped_at_utc is not None
                else None
            ),
            "error": self.error.to_dict() if self.error is not None else None,
        }


class RaDecTrackingManager:
    def __init__(self, store: RaDecSessionStore) -> None:
        self._store = store
        self._lock = RLock()
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._status = TrackingStatus(state=TrackingState.IDLE)

    def get_status(self) -> TrackingStatus:
        with self._lock:
            return self._status

    def _resolve_session(self, session_id: str | None) -> RaDecSession:
        session = (
            self._store.get(session_id)
            if session_id is not None
            else self._store.get_current()
        )

        if session is None:
            raise ApplicationError(
                code="radec_session_not_found",
                message="追尾に使用するRA/DEC取得セッションがありません。",
                details={"session_id": session_id},
            )

        return session

    def start(
        self,
        session_id: str | None = None,
        update_interval_seconds: float = DEFAULT_RADEC_TRACK_UPDATE_INTERVAL_SECONDS,
        marker_style: RaDecMarkerStyle | None = None,
        follow_view: bool = False,
    ) -> TrackingStatus:
        if update_interval_seconds <= 0:
            raise ApplicationError(
                code="invalid_tracking_interval",
                message="マーカー更新間隔は0より大きい値にしてください。",
            )

        session = self._resolve_session(session_id)

        with self._lock:
            if self._status.is_active:
                raise ApplicationError(
                    code="tracking_already_running",
                    message="RA/DEC追尾は既に実行中です。",
                    details={"session_id": self._status.session_id},
                )

            self._stop_event = Event()
            self._status = TrackingStatus(
                state=TrackingState.RUNNING,
                session_id=session.session_id,
                started_at_utc=datetime.now(timezone.utc),
            )

            thread = Thread(
                target=self._run,
                args=(
                    session,
                    update_interval_seconds,
                    marker_style,
                    follow_view,
                ),
                name="stellarium-neo-radec-tracking",
                daemon=True,
            )
            self._thread = thread
            thread.start()
            return self._status

    def _record_update(
        self,
        update_count: int,
        last_datetime_utc: datetime | None,
    ) -> None:
        with self._lock:
            if self._status.state is TrackingState.RUNNING:
                self._status = replace(
                    self._status,
                    update_count=update_count,
                    last_datetime_utc=last_datetime_utc,
                )

    def _run(
        self,
        session: RaDecSession,
        update_interval_seconds: float,
        marker_style: RaDecMarkerStyle | None,
        follow_view: bool,
    ) -> None:
        displayed = RaDecSeriesDisplayResult(
            source="jpl_radec_series",
            identity=session.identity,
            series=session.series,
            datetime_utc=session.series.start_datetime_utc,
            observer=session.series.observer,
        )

        try:
            result = track_jpl_radec_series(
                displayed=displayed,
                update_interval_seconds=update_interval_seconds,
                marker_style=marker_style,
                follow_view=follow_view,
                stop_event=self._stop_event,
                clear_marker_on_exit=True,
                on_update=self._record_update,
            )
        except BaseException as error:
            with self._lock:
                self._status = replace(
                    self._status,
                    state=TrackingState.ERROR,
                    stopped_at_utc=datetime.now(timezone.utc),
                    error=error_info_from_exception(error),
                )
            return

        with self._lock:
            self._status = replace(
                self._status,
                state=TrackingState.STOPPED,
                update_count=result.update_count,
                last_datetime_utc=result.last_datetime_utc,
                stopped_at_utc=datetime.now(timezone.utc),
                error=None,
            )

    def stop(self, wait_timeout_seconds: float = 2.0) -> TrackingStatus:
        if wait_timeout_seconds < 0:
            raise ApplicationError(
                code="invalid_stop_timeout",
                message="停止待機時間は0以上で指定してください。",
            )

        with self._lock:
            if not self._status.is_active:
                return self._status

            self._status = replace(
                self._status,
                state=TrackingState.STOPPING,
            )
            self._stop_event.set()
            thread = self._thread

        if thread is not None and wait_timeout_seconds > 0:
            thread.join(wait_timeout_seconds)

        return self.get_status()
