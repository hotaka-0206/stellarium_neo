import requests

BASE_URL = "http://localhost:8090/api"


def get_status():
    response = requests.get(f"{BASE_URL}/main/status")
    print("status_code:", response.status_code)
    print(response.text)


def focus_jupiter():
    focus_data = {
        "target": "Jupiter",
        "mode": "zoom",
    }

    response = requests.post(f"{BASE_URL}/main/focus", data=focus_data)
    print("status_code:", response.status_code)
    print(response.text)


def main():
    get_status()
    focus_jupiter()


if __name__ == "__main__":
    main()