import requests
import subprocess
import time
from datetime import datetime, timezone, timedelta
from get_orbit import fetch_orbital_elements_from_jpl
from jpl_to_stel import (
    make_stellarium_section,
    save_to_stellarium,
    make_section_id,
    find_object_by_minor_planet_number,
)

BASE_URL = "http://localhost:8090/api"
STELLARIUM_PATH = r"C:\Program Files\Stellarium\stellarium.exe"
TARGET_ALIASES = {
    "Ceres": "(1) Ceres",
    "Apophis": "(99942) Apophis",
}


def to_julian_day(dt):
    dt = dt.astimezone(timezone.utc)

    y = dt.year
    m = dt.month
    d = dt.day
    h = dt.hour + dt.minute / 60 + dt.second / 3600

    #3月を年の始まりっぽく扱うとうるう年の処理が楽になるらしい
    if m <= 2:
        y -= 1
        m += 12
    
    a = y // 100    #世紀　//で割り算の整数部分
    b = 2 - a + a // 4  #グレゴリオ暦の補正

    return int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + d + h / 24 + b - 1524.5

def to_horizons_time(dt):
    dt_utc = dt.astimezone(timezone.utc)
    return dt_utc.strftime("%Y-%b-%d %H:%M")

def is_stellarium_running():
    try:
        response = requests.get(f"{BASE_URL}/main/status", timeout=2)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False


def start_stellarium():
    if is_stellarium_running():
        return
    
    subprocess.Popen([STELLARIUM_PATH])
    time.sleep(8)


def set_time(dt, retry=20, interval=1.0):
    jd = to_julian_day(dt)
    for i in range(retry):
        response = requests.post(
            f"{BASE_URL}/main/time",
            data={
                "time": jd,
                "timerate": 0
            }
        )

        print(f"time attempt {i + 1}")
        print("time status:", response.status_code)
        print("time response:", response.text)

        if response.status_code == 200:
            return True

        time.sleep(interval)

    return False


def focus_object(target, retry=20, interval=1.0):
    url = f"{BASE_URL}/main/focus"

    for i in range(retry):
        response = requests.post(url, data={
            "target": target,
            "mode": "zoom"
        })

        print(f"focus attempt {i + 1}")
        print("focus status:", response.status_code)
        print("focus response:", response.text)

        if response.status_code == 200:
            return True

        time.sleep(interval)

    return False


def normalize_target(target):
    target = target.strip()
    return TARGET_ALIASES.get(target, target)   #(探すキー，無い場合に返す値)


def main():

    target_id = input("JPL Horizonsの天体IDを入力してください > ").strip()

    if target_id.isdigit():
        target_id = target_id + ";"

    minor_number = target_id.replace(";", "")

    # 天体番号で既に登録されているか確認する
    existing_object = find_object_by_minor_planet_number(minor_number)

    should_fetch_jpl = True
    should_save = True
    section_id = None

    minor_number = target_id.replace(";", "")

    existing_object = find_object_by_minor_planet_number(minor_number)

    should_fetch_jpl = True
    should_save = True
    section_id = None
    display_name = None

    if existing_object is not None:
        section_id = existing_object["section_id"]
        display_name = existing_object["name"]

        print(f"天体番号 {minor_number} は既に [{section_id}] として登録されています。")
        print(f"表示名: {display_name}")

        answer = input("JPLの最新データで更新しますか？ y/n > ").strip().lower()

        if answer == "y":
            print("JPLから最新データを取得して更新します。")
            should_fetch_jpl = True
            should_save = True
        else:
            print("更新せず、既存データのまま表示します。")
            should_fetch_jpl = False
            should_save = False

    else:
        print(f"天体番号 {minor_number} はまだ登録されていません。")
        answer = input("新しく追加しますか？ y/n > ").strip().lower()

        if answer != "y":
            print("追加せずに中止しました。")
            return

        should_fetch_jpl = True
        should_save = True

    date_text = input("日時 形式：yyyymmddHHMMSS > ")

    print("時間系の番号を入力してください")
    print("1: UTC")
    print("2: JST")
    time_type = input("番号 > ")

    dt = datetime.strptime(date_text, "%Y%m%d%H%M%S")

    if time_type == "2":
        dt = dt.replace(tzinfo=timezone(timedelta(hours=9)))
    else:
        dt = dt.replace(tzinfo=timezone.utc)

    if should_fetch_jpl:
        dt_utc = dt.astimezone(timezone.utc)

        start_time = to_horizons_time(dt_utc)
        stop_time = to_horizons_time(dt_utc + timedelta(minutes=1))

        print("JPL取得開始時刻:", start_time)
        print("JPL取得終了時刻:", stop_time)

        elements = fetch_orbital_elements_from_jpl(
            target_id=target_id,
            start_time=start_time,
            stop_time=stop_time,
            step_size="1 m",
        )

        print("JPL Horizonsから取得した太陽中心の軌道要素")
        print("----------------------------------------")
        for key, value in elements.items():
            print(f"{key}: {value}")

        # Stellariumで表示する名前を決める
        display_name = input("Stellariumでの表示名 例: JPL_Apophis > ").strip()
        if display_name == "":
            display_name = f"JPL_{minor_number}"

        if section_id is None:
            section_id = make_section_id(display_name)

        # JPLの軌道要素をStellarium用の形式に変換
        section_text = make_stellarium_section(
            section_id=section_id,
            display_name=display_name,
            elements=elements,
            minor_planet_number=minor_number,
        )

        print()
        print("Stellariumに書き込む内容")
        print("----------------------------------------")
        print(section_text)
        print("----------------------------------------")

        if should_save:
            save_to_stellarium(section_id, section_text)

    start_stellarium()
    set_time(dt)
    time.sleep(1)

    focus_object(f"({minor_number}) {display_name}")


if __name__ == "__main__":
    main()