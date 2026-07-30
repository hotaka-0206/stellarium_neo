import platform
import subprocess
import time
from datetime import datetime, timezone

import requests

BASE_URL = "http://localhost:8090/api"


class StellariumError(RuntimeError):
    pass


class StellariumApiError(StellariumError):
    pass


def get_stellarium_exe_path() -> str:
    if platform.system() == "Windows":
        return r"C:\Program Files\Stellarium\stellarium.exe"
    if platform.system() == "Darwin":
        return "/Applications/Stellarium.app/Contents/MacOS/Stellarium"
    return "stellarium"


STELLARIUM_PATH = get_stellarium_exe_path()


def to_julian_day(dt: datetime) -> float:
    if dt.tzinfo is None:
        raise ValueError("日時にはUTCまたはJSTのタイムゾーンが必要です。")

    dt = dt.astimezone(timezone.utc)
    y = dt.year
    m = dt.month
    d = dt.day
    h = dt.hour + dt.minute / 60 + dt.second / 3600

    if m <= 2:
        y -= 1
        m += 12

    a = y // 100
    b = 2 - a + a // 4

    return (
        int(365.25 * (y + 4716))
        + int(30.6001 * (m + 1))
        + d
        + h / 24
        + b
        - 1524.5
    )


def is_stellarium_running() -> bool:
    try:
        response = requests.get(f"{BASE_URL}/main/status", timeout=2)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False


def stop_stellarium() -> None:
    if not is_stellarium_running():
        return

    if platform.system() == "Windows":
        subprocess.run(
            ["taskkill", "/IM", "stellarium.exe", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    else:
        subprocess.run(
            ["pkill", "-f", STELLARIUM_PATH],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )

    for _ in range(20):
        if not is_stellarium_running():
            return
        time.sleep(0.5)

    raise StellariumError("Stellariumを終了できませんでした。")


def start_stellarium() -> None:
    if is_stellarium_running():
        return

    try:
        subprocess.Popen([STELLARIUM_PATH])
    except OSError as error:
        raise StellariumError(
            f"Stellariumを起動できませんでした: {STELLARIUM_PATH}"
        ) from error

    for _ in range(40):
        if is_stellarium_running():
            return
        time.sleep(0.5)

    raise StellariumError(
        "StellariumのRemote Control APIに接続できませんでした。"
    )


def restart_stellarium() -> None:
    stop_stellarium()
    start_stellarium()


def _post_with_retry(
    endpoint: str,
    data: dict,
    retry: int,
    interval: float,
) -> None:
    last_detail = "応答なし"

    for _ in range(retry):
        try:
            response = requests.post(
                f"{BASE_URL}{endpoint}",
                data=data,
                timeout=5,
            )
            last_detail = f"status={response.status_code}, body={response.text}"

            if (
                response.status_code == 200
                and response.text.strip().lower() != "false"
            ):
                return
        except requests.exceptions.RequestException as error:
            last_detail = str(error)

        time.sleep(interval)

    raise StellariumApiError(
        f"Stellarium API {endpoint} の実行に失敗しました: {last_detail}"
    )


def set_time(dt: datetime, retry: int = 20, interval: float = 1.0) -> None:
    _post_with_retry(
        endpoint="/main/time",
        data={"time": to_julian_day(dt), "timerate": 0},
        retry=retry,
        interval=interval,
    )


def focus_object(
    target: str,
    retry: int = 20,
    interval: float = 1.0,
) -> None:
    _post_with_retry(
        endpoint="/main/focus",
        data={"target": target, "mode": "zoom"},
        retry=retry,
        interval=interval,
    )


def set_fov_deg(
    fov_deg: float,
    retry: int = 10,
    interval: float = 0.5,
) -> None:
    _post_with_retry(
        endpoint="/main/fov",
        data={"fov": fov_deg},
        retry=retry,
        interval=interval,
    )
