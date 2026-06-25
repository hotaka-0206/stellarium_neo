import requests
import subprocess
import time
from datetime import datetime, timezone, timedelta
from get_orbit import fetch_orbital_elements_from_jpl
from jpl_to_stel import make_stellarium_section, save_to_stellarium, make_section_id

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


def set_time(dt):
    jd = to_julian_day(dt)
    response = requests.post(f"{BASE_URL}/main/time", data={"time": jd, "timerate": 0})
    print("time status:", response.status_code)
    print("time response:", response.text)


# def focus_object(target):
#     response = requests.post(
#         f"{BASE_URL}/main/focus",
#         data={"target": target, "mode": "zoom"}
#     )
#     print("focus status:", response.status_code)
#     print("focus response:", response.text)


def focus_object(target, retry=20, interval=1.0):
    url = "http://localhost:8090/api/main/focus"

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

    elements = fetch_orbital_elements_from_jpl(target_id)

    print("JPL Horizonsから取得した太陽中心の軌道要素")
    print("----------------------------------------")
    for key, value in elements.items():
        print(f"{key}: {value}")
    
        # Stellariumで表示する名前を決める
    display_name = input("Stellariumでの表示名 例: JPL_Apophis > ").strip()
    if display_name == "":
        display_name = f"JPL_{target_id.replace(';', '')}"

    # ssystem_minor.ini のセクション名を作る
    section_id = make_section_id(display_name)

    # JPLの軌道要素をStellarium用の形式に変換
    section_text = make_stellarium_section(
        section_id=section_id,
        display_name=display_name,
        elements=elements,
        minor_planet_number=target_id.replace(";", ""),
    )

    print()
    print("Stellariumに追加する内容")
    print("----------------------------------------")
    print(section_text)
    print("----------------------------------------")

    answer = input("この内容をStellariumに反映しますか？ y/n > ").strip().lower()

    if answer != "y":
        print("中止しました。")
        return

    # ssystem_minor.ini に書き込む
    save_to_stellarium(section_id, section_text)


    ##手動フォーカス------------------------------------------------------
    # target = input("対象天体 形式：天体名 または (小惑星番号)␣ 名前 > ")
    # target = normalize_target(target)

    # date_text = input("日時 形式：yyyymmddHHMMSS > ")
    
    # print("時間系の番号を入力してください")
    # print("1: UTC")
    # print("2: JST")
    # time_type = input("番号 > ")

    # dt = datetime.strptime(date_text, "%Y%m%d%H%M%S")

    # if time_type == "2":
    #     dt = dt.replace(tzinfo=timezone(timedelta(hours=9)))
    # else:
    #     dt = dt.replace(tzinfo=timezone.utc)
    ##-------------------------------------------------------------------


    start_stellarium()

    #set_time(dt)
    time.sleep(1)
    #focus_object(target)

    minor_number = target_id.replace(";", "")

    focus_object(f"({minor_number}) {display_name}")


if __name__ == "__main__":
    main()