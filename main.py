import requests
import subprocess
import time
from datetime import datetime, timezone, timedelta

BASE_URL = "http://localhost:8090/api"
STELLARIUM_PATH = r"C:\Program Files\Stellarium\stellarium.exe"


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
    requests.post(f"{BASE_URL}/main/time", data={"time": jd, "timerate": 0})


def focus_object(target):
    requests.post(f"{BASE_URL}/main/focus", data={"target": target, "mode": "zoom"})


def main():
    target = input("対象天体 例 Jupiter > ")

    date_text = input("日時 yyyy-mm-dd HH:MM:SS > ")

    print("時間系を選んでください")
    print("1: UTC")
    print("2: JST")
    time_type = input("番号 > ")

    dt = datetime.strptime(date_text, "%Y-%m-%d %H:%M:%S")

    if time_type == "2":
        dt = dt.replace(tzinfo=timezone(timedelta(hours=9)))
    else:
        dt = dt.replace(tzinfo=timezone.utc)

    start_stellarium()

    set_time(dt)
    focus_object(target)



if __name__ == "__main__":
    main()