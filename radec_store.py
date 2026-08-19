from dataclasses import dataclass
from datetime import datetime, timezone
from threading import RLock
from typing import Protocol
from uuid import uuid4

from get_orbit import TargetIdentity, TopocentricRaDecSeries


@dataclass(frozen=True)
class RaDecSession:
    session_id: str
    identity: TargetIdentity
    series: TopocentricRaDecSeries
    created_at_utc: datetime

    @property
    def point_count(self) -> int:
        return self.series.point_count


class RaDecSessionStore(Protocol):
    def save(
        self,
        identity: TargetIdentity,
        series: TopocentricRaDecSeries,
    ) -> RaDecSession:
        ...

    def get(self, session_id: str) -> RaDecSession | None:
        ...

    def get_current(self) -> RaDecSession | None:
        ...

    def clear(self) -> None:
        ...


class MemoryRaDecSessionStore:
    """現在のRA/DEC取得セッションをメモリ上に1件保持するStore。

    GUI/API層はこのインターフェースだけを使う。将来SQLiteなどへ
    保存先を変更しても、呼び出し側を変更しなくて済むようにする。
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._current: RaDecSession | None = None

    def save(
        self,
        identity: TargetIdentity,
        series: TopocentricRaDecSeries,
    ) -> RaDecSession:
        session = RaDecSession(
            session_id=uuid4().hex,
            identity=identity,
            series=series,
            created_at_utc=datetime.now(timezone.utc),
        )

        with self._lock:
            self._current = session

        return session

    def get(self, session_id: str) -> RaDecSession | None:
        value = session_id.strip()

        if not value:
            return None

        with self._lock:
            if self._current is None:
                return None

            if self._current.session_id != value:
                return None

            return self._current

    def get_current(self) -> RaDecSession | None:
        with self._lock:
            return self._current

    def clear(self) -> None:
        with self._lock:
            self._current = None
