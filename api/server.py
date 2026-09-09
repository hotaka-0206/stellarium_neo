from datetime import datetime

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app_errors import ApplicationError
from app_service import StellariumNeoService
from observer import ObserverLocation
from orbit_service import DEFAULT_RADEC_TRACK_UPDATE_INTERVAL_SECONDS
# ============================================================
# FastAPI Application
# ============================================================

app = FastAPI(
    title="Stellarium Neo API",
    version="0.1.0",
)
# ============================================================
# Application Service
#
# APIサーバー起動中は同じServiceインスタンスを使用する。
#
# RA/DEC取得セッションや追尾状態をリクエスト間で保持するため、
# 各エンドポイント内で StellariumNeoService() を
# 作り直してはいけない。
# ============================================================

app_service = StellariumNeoService()
# ============================================================
# Request Models
# ============================================================

class TargetInspectRequest(BaseModel):
    """天体識別用リクエスト。"""

    identifier: str


class ObserverRequest(BaseModel):
    """観測地点。"""

    latitude_deg: float
    longitude_deg: float
    altitude_m: float = 0.0
    name: str = "Custom observer"


class OrbitShowRequest(BaseModel):
    """JPL軌道要素によるStellarium表示用リクエスト。"""

    identifier: str
    reference_datetime: datetime
    fetch_mode: str = "auto"
    display_name: str | None = None
    fov_deg: float = 30.0


class RaDecFetchRequest(BaseModel):
    """RA/DEC系列取得用リクエスト。"""

    identifier: str
    start_datetime: datetime
    end_datetime: datetime
    observer: ObserverRequest


class TrackingStartRequest(BaseModel):
    """RA/DEC追尾開始用リクエスト。"""

    session_id: str | None = None
    update_interval_seconds: float = (
        DEFAULT_RADEC_TRACK_UPDATE_INTERVAL_SECONDS
    )
    follow_view: bool = False
# ============================================================
# Error Handler
# ============================================================

@app.exception_handler(ApplicationError)
async def application_error_handler(
    request: Request,
    error: ApplicationError,
):
    """
    アプリケーション内部のエラーを
    Flutterから扱いやすいJSON形式へ変換する。
    """

    return JSONResponse(
        status_code=400,
        content={
            "success": False,
            "error": error.to_dict(),
        },
    )
# ============================================================
# API Status
# ============================================================

@app.get("/api/status")
def get_api_status():
    """
    Pythonバックエンドが起動しているか確認する。
    """

    return {
        "success": True,
        "message": "Stellarium Neo backend is running",
    }
# ============================================================
# Target
# ============================================================

@app.post("/api/target/inspect")
def inspect_target(request: TargetInspectRequest):
    """
    入力された識別子をJPL上の天体へ解決する。

    対応例:
    - Apophis
    - 99942
    - 2004 MN4
    - 2099942
    - アポフィス
    """

    status = app_service.inspect_target(
        identifier=request.identifier,
    )
    return {
        "success": True,
        "data": jsonable_encoder(status),
    }
# ============================================================
# Orbit
# ============================================================

@app.post("/api/orbit/show")
def show_orbit(request: OrbitShowRequest):
    """
    JPL軌道要素を使って対象天体をStellariumへ表示する。

    fetch_mode:
    - auto: 未登録の場合だけJPLから取得する
    - force: JPLから軌道要素を再取得して登録・表示する
    - never: 既に登録済みのJPL版を再取得せず表示する
    """

    result = app_service.show_jpl_orbit_target(
        identifier=request.identifier,
        dt=request.reference_datetime,
        fetch_mode=request.fetch_mode,
        display_name=request.display_name,
        fov_deg=request.fov_deg,
    )

    return {
        "success": True,
        "data": jsonable_encoder(result),
    }
# ============================================================
# RA/DEC
# ============================================================

@app.post("/api/radec/fetch")
def fetch_radec(request: RaDecFetchRequest):
    """
    指定した天体についてJPL Horizonsから
    観測地点別RA/DEC系列を取得する。

    取得した系列はメモリ上のRA/DECセッションとして保存する。

    display_start=True のため、
    取得完了後にStellariumへ以下を反映する。

    - 観測地点
    - 取得開始日時
    - 開始時点のRA/DEC
    - RA/DECマーカー
    """
    observer = ObserverLocation(
        latitude_deg=request.observer.latitude_deg,
        longitude_deg=request.observer.longitude_deg,
        altitude_m=request.observer.altitude_m,
        name=request.observer.name,
    )

    session = app_service.fetch_radec_session(
        identifier=request.identifier,
        start_dt=request.start_datetime,
        end_dt=request.end_datetime,
        observer=observer,
        display_start=True,
    )
    return {
        "success": True,
        "data": session.to_dict(),
    }


@app.get("/api/radec/session")
def get_current_radec_session():
    """
    現在保存されているRA/DEC取得セッションを取得する。

    セッションが存在しない場合:
        data = null
    """

    session = app_service.get_current_radec_session()

    return {
        "success": True,
        "data": (
            session.to_dict()
            if session is not None
            else None
        ),
    }

@app.delete("/api/radec/session")
def clear_current_radec_session():
    """
    現在のRA/DEC取得セッションを削除する。

    Stellarium Neoが管理しているRA/DECマーカーも削除する。

    RA/DEC追尾中は削除できない。
    """

    app_service.clear_current_radec_session()

    return {
        "success": True,
        "message": "RA/DEC session cleared",
    }
# ============================================================
# Tracking
# ============================================================

@app.post("/api/tracking/start")
def start_tracking(request: TrackingStartRequest):
    """
    保存済みRA/DEC系列を使用して追尾を開始する。

    session_id:
        nullの場合は現在保存されているセッションを使用する。

    update_interval_seconds:
        Stellariumの時刻を確認し、
        マーカー位置を更新する間隔。

        JPLのRA/DEC取得間隔0.5秒とは別。

    follow_view:
        trueの場合、マーカーだけでなく
        Stellariumの視点もRA/DEC位置へ追従させる。
    """

    status = app_service.start_tracking(
        session_id=request.session_id,
        update_interval_seconds=request.update_interval_seconds,
        follow_view=request.follow_view,
    )

    return {
        "success": True,
        "data": status.to_dict(),
    }


@app.post("/api/tracking/stop")
def stop_tracking():
    """
    現在実行中のRA/DEC追尾を停止する。

    既に停止している場合も現在の状態を返す。
    """
    status = app_service.stop_tracking()

    return {
        "success": True,
        "data": status.to_dict(),
    }


@app.get("/api/tracking/status")
def get_tracking_status():
    """
    現在のRA/DEC追尾状態を取得する。

    主なstate:
    - idle
    - running
    - stopping
    - stopped
    - error
    """

    status = app_service.get_tracking_status()

    return {
        "success": True,
        "data": status.to_dict(),
    }
