import platform
import subprocess
import time
from datetime import datetime, timedelta, timezone

import requests

from get_orbit import fetch_orbital_elements_from_jpl
from jpl_to_stel import (
    find_jpl_object_by_minor_planet_number,
    find_standard_object_by_minor_planet_number,
    make_stellarium_section,
    save_to_stellarium,
)

BASE_URL = "http://localhost:8090/api"


def get_stellarium_exe_path():
    if platform.system() == "Windows":
        return r"C:\Program Files\Stellarium\stellarium.exe"
    if platform.system() == "Darwin":
        return "/Applications/Stellarium.app/Contents/MacOS/Stellarium"
    return "stellarium"


STELLARIUM_PATH = get_stellarium_exe_path()


def to_julian_day(dt):
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


def to_horizons_time(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%b-%d %H:%M")


def is_stellarium_running():
    try:
        response = requests.get(f"{BASE_URL}/main/status", timeout=2)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False


def stop_stellarium():
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


def start_stellarium():
    if is_stellarium_running():
        return

    subprocess.Popen([STELLARIUM_PATH])

    for _ in range(40):
        if is_stellarium_running():
            return
        time.sleep(0.5)


def restart_stellarium():
    stop_stellarium()
    start_stellarium()


def set_time(dt, retry=20, interval=1.0):
    jd = to_julian_day(dt)

    for i in range(retry):
        response = requests.post(
            f"{BASE_URL}/main/time",
            data={"time": jd, "timerate": 0},
            timeout=5,
        )

        print(f"time attempt {i + 1}")
        print("time status:", response.status_code)
        print("time response:", response.text)

        if response.status_code == 200 and response.text.strip().lower() != "false":
            return True

        time.sleep(interval)

    return False


def focus_object(target, retry=20, interval=1.0):
    for i in range(retry):
        response = requests.post(
            f"{BASE_URL}/main/focus",
            data={"target": target, "mode": "zoom"},
            timeout=5,
        )

        print(f"focus attempt {i + 1}")
        print("focus status:", response.status_code)
        print("focus response:", response.text)

        if response.status_code == 200 and response.text.strip().lower() != "false":
            return True

        time.sleep(interval)

    return False


def set_fov_deg(fov_deg, retry=10, interval=0.5):
    for i in range(retry):
        response = requests.post(
            f"{BASE_URL}/main/fov",
            data={"fov": fov_deg},
            timeout=5,
        )

        print(f"fov attempt {i + 1}")
        print("fov status:", response.status_code)
        print("fov response:", response.text)

        if response.status_code == 200 and response.text.strip().lower() != "false":
            return True

        time.sleep(interval)

    return False


def input_datetime():
    date_text = input("日時 形式：yyyymmddHHMMSS > ").strip()

    print("時間系の番号を入力してください")
    print("1: UTC")
    print("2: JST")
    time_type = input("番号 > ").strip()

    dt = datetime.strptime(date_text, "%Y%m%d%H%M%S")

    if time_type == "2":
        return dt.replace(tzinfo=timezone(timedelta(hours=9)))

    return dt.replace(tzinfo=timezone.utc)


def prepare_jpl_target(dt):
    target_id = input("JPL Horizonsの天体IDを入力してください > ").strip()

    if target_id.isdigit():
        target_id += ";"

    minor_number = target_id.replace(";", "")
    existing_object = find_jpl_object_by_minor_planet_number(minor_number)
    section_id = f"jpl_{minor_number}"
    old_section_id = None
    display_name = None
    should_fetch_jpl = True

    if existing_object is not None:
        old_section_id = existing_object["section_id"]
        display_name = existing_object["name"]

        print(
            f"天体番号 {minor_number} は既に "
            f"[{old_section_id}] として登録されています。"
        )
        print(f"表示名: {display_name}")

        answer = input("JPLの最新データで更新しますか？ y/n > ").strip().lower()

        if answer != "y":
            should_fetch_jpl = False
    else:
        print(f"天体番号 {minor_number} のJPL版はまだ登録されていません。")
        answer = input("JPLデータを新しく追加しますか？ y/n > ").strip().lower()

        if answer != "y":
            return None, False

    catalog_changed = False

    if should_fetch_jpl:
        dt_utc = dt.astimezone(timezone.utc)
        start_time = to_horizons_time(dt_utc)
        stop_time = to_horizons_time(dt_utc + timedelta(minutes=1))

        elements = fetch_orbital_elements_from_jpl(
            target_id=target_id,
            start_time=start_time,
            stop_time=stop_time,
            step_size="1 m",
        )

        if display_name is None:
            display_name = input(
                "Stellariumでの表示名 例: JPL_Apophis > "
            ).strip()

            if display_name == "":
                display_name = f"JPL_{minor_number}"

        section_text = make_stellarium_section(
            section_id=section_id,
            display_name=display_name,
            elements=elements,
            minor_planet_number=minor_number,
        )

        save_to_stellarium(
            section_id=section_id,
            section_text=section_text,
            old_section_id=old_section_id,
        )
        catalog_changed = True

    focus_name = f"({minor_number}) {display_name}"
    print(f"JPLのフォーカス対象: {focus_name}")
    return focus_name, catalog_changed


def prepare_standard_target():
    target = input(
        "Stellarium標準の天体名または天体番号を入力してください > "
    ).strip()

    if not target.isdigit():
        return target

    standard_object = find_standard_object_by_minor_planet_number(target)

    if standard_object is None:
        print(f"天体番号 {target} のStellarium標準版が見つかりません。")
        return None

    focus_name = f"({target}) {standard_object['name']}"
    print(f"Stellarium標準のフォーカス対象: {focus_name}")
    return focus_name


def main():
    print("表示する天体データを選択してください")
    print("1: JPL")
    print("2: Stellarium標準")
    source_type = input("番号 > ").strip()

    if source_type not in {"1", "2"}:
        print("1または2を入力してください。")
        return

    dt = input_datetime()
    catalog_changed = False

    if source_type == "1":
        focus_target, catalog_changed = prepare_jpl_target(dt)
    else:
        focus_target = prepare_standard_target()

    if focus_target is None:
        return

    if catalog_changed:
        restart_stellarium()
    else:
        start_stellarium()

    if not set_time(dt):
        print("時刻設定に失敗しました。")
        return

    time.sleep(1)

    if not focus_object(focus_target):
        print(f"{focus_target} へのフォーカスに失敗しました。")
        return

    time.sleep(1)
    set_fov_deg(30)


if __name__ == "__main__":
    main()