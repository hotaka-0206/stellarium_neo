from datetime import datetime, timedelta, timezone
import time

from app_errors import ApplicationError
from app_service import StellariumNeoService
from observer import ObserverLocation
from orbit_service import DEFAULT_RADEC_TRACK_UPDATE_INTERVAL_SECONDS, FetchMode
from tracking_service import TrackingState


DEFAULT_OBSERVER = ObserverLocation(
    latitude_deg=35.4978,
    longitude_deg=133.025,
    altitude_m=0,
    name="MatsueKosen",
)

APP_SERVICE = StellariumNeoService()


def _timezone_from_input(time_type: str) -> timezone:
    if time_type == "1":
        return timezone.utc
    if time_type == "2":
        return timezone(timedelta(hours=9))

    raise ValueError("時間系は1または2を入力してください。")


def input_timezone() -> timezone:
    print("時間系の番号を入力してください")
    print("1: UTC")
    print("2: JST")
    return _timezone_from_input(input("番号 > ").strip())


def parse_cli_datetime(date_text: str, tz: timezone) -> datetime:
    dt = datetime.strptime(date_text.strip(), "%Y%m%d%H%M%S")
    return dt.replace(tzinfo=tz)


def input_datetime() -> datetime:
    date_text = input("日時 形式：yyyymmddHHMMSS > ").strip()
    tz = input_timezone()
    return parse_cli_datetime(date_text, tz)


def input_datetime_range() -> tuple[datetime, datetime]:
    print("RA/DEC取得範囲を指定してください。")
    tz = input_timezone()
    start_text = input("取得開始日時 形式：yyyymmddHHMMSS > ").strip()
    end_text = input("取得終了日時 形式：yyyymmddHHMMSS > ").strip()

    return (
        parse_cli_datetime(start_text, tz),
        parse_cli_datetime(end_text, tz),
    )


def input_identifier() -> str:
    return input(
        "天体名・小惑星番号・仮符号・SPK-IDを入力してください > "
    ).strip()


def input_observer_location() -> ObserverLocation:
    print("観測地点を入力してください。Enterで松江の既定値を使用します。")
    latitude_text = input(
        f"緯度[度] Enter={DEFAULT_OBSERVER.latitude_deg} > "
    ).strip()
    longitude_text = input(
        f"経度[度・東経が正] Enter={DEFAULT_OBSERVER.longitude_deg} > "
    ).strip()
    altitude_text = input(
        f"標高[m] Enter={DEFAULT_OBSERVER.altitude_m} > "
    ).strip()
    name = input(f"地点名 Enter={DEFAULT_OBSERVER.name} > ").strip()

    return ObserverLocation(
        latitude_deg=(
            float(latitude_text)
            if latitude_text
            else DEFAULT_OBSERVER.latitude_deg
        ),
        longitude_deg=(
            float(longitude_text)
            if longitude_text
            else DEFAULT_OBSERVER.longitude_deg
        ),
        altitude_m=(
            float(altitude_text)
            if altitude_text
            else DEFAULT_OBSERVER.altitude_m
        ),
        name=name or DEFAULT_OBSERVER.name,
    )


def input_jpl_fetch_settings(status) -> tuple[FetchMode, str | None]:
    identity = status.identity

    print(f"JPLで見つかった天体: {identity.full_name}")
    print(f"Horizons識別子: {identity.horizons_command}")

    if status.is_registered:
        print(
            f"既に [{identity.section_id}] "
            f"{status.existing_object.name} として登録されています。"
        )
        answer = input("JPLの最新データで更新しますか? y/n > ").strip().lower()
        mode = FetchMode.FORCE if answer == "y" else FetchMode.NEVER
        return mode, None

    print(f"[{identity.section_id}] はまだ登録されていません。")
    answer = input("JPLデータを新しく追加しますか? y/n > ").strip().lower()

    if answer != "y":
        raise KeyboardInterrupt

    display_name = input(
        f"Stellariumでの表示名 Enterで {identity.default_display_name} > "
    ).strip()
    return FetchMode.AUTO, display_name or None


def run_jpl_orbit_cli() -> None:
    dt = input_datetime()
    identifier = input_identifier()
    status = APP_SERVICE.inspect_target(identifier)
    fetch_mode, display_name = input_jpl_fetch_settings(status)

    result = APP_SERVICE.show_jpl_orbit_target(
        identifier=identifier,
        dt=dt,
        fetch_mode=fetch_mode,
        display_name=display_name,
    )
    print(f"表示完了: {result.focus_target}")
    print(f"UTC: {result.datetime_utc.strftime('%Y-%m-%d %H:%M:%S')}")


def run_standard_cli() -> None:
    dt = input_datetime()
    target = input(
        "Stellarium標準の天体名または天体番号を入力してください > "
    ).strip()
    result = APP_SERVICE.show_standard_target(target=target, dt=dt)
    print(f"表示完了: {result.focus_target}")
    print(f"UTC: {result.datetime_utc.strftime('%Y-%m-%d %H:%M:%S')}")


def run_radec_tracking_cli() -> None:
    start_dt, end_dt = input_datetime_range()
    summary = APP_SERVICE.get_radec_request_summary(start_dt, end_dt)
    identifier = input_identifier()
    observer = input_observer_location()

    print(f"取得間隔: {summary.step_seconds}秒（固定）")
    print(f"取得時間: {summary.duration_seconds / 3600:.3f}時間")
    print(f"取得予定点数: {summary.point_count:,}点")

    session = APP_SERVICE.fetch_radec_session(
        identifier=identifier,
        start_dt=start_dt,
        end_dt=end_dt,
        observer=observer,
        display_start=True,
    )

    print(f"取得完了: {session.target_full_name}")
    print(f"セッションID: {session.session_id}")
    print(f"取得点数: {session.point_count:,}点")
    print(
        "取得範囲[UTC]: "
        f"{session.start_datetime_utc.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]} ～ "
        f"{session.end_datetime_utc.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}"
    )
    print(
        "観測地点: "
        f"{session.observer.name} "
        f"({session.observer.latitude_deg}, "
        f"{session.observer.longitude_deg}, "
        f"{session.observer.altitude_m} m)"
    )
    print(
        "マーカー更新間隔: "
        f"{DEFAULT_RADEC_TRACK_UPDATE_INTERVAL_SECONDS}秒"
    )
    print(
        "追尾を開始します。取得範囲外ではマーカーのみ非表示になります。"
        "Ctrl+Cで追尾を停止します。"
    )

    APP_SERVICE.start_tracking(
        session_id=session.session_id,
        update_interval_seconds=DEFAULT_RADEC_TRACK_UPDATE_INTERVAL_SECONDS,
    )

    try:
        while True:
            status = APP_SERVICE.get_tracking_status()

            if status.state in {TrackingState.STOPPED, TrackingState.ERROR}:
                break

            time.sleep(0.2)
    except KeyboardInterrupt:
        APP_SERVICE.stop_tracking()
        print("追尾停止を要求しました。")
        return

    status = APP_SERVICE.get_tracking_status()

    if status.state is TrackingState.ERROR:
        error = status.error
        if error is None:
            print("追尾中に不明なエラーが発生しました。")
        else:
            print(f"追尾エラー [{error.code}]: {error.message}")
        return

    print("追尾を終了しました。")
    print(f"マーカー更新回数: {status.update_count:,}回")


def print_application_error(error: ApplicationError) -> None:
    print(f"エラー [{error.code}]: {error.message}")

    candidates = error.details.get("candidates")
    if isinstance(candidates, list) and candidates:
        print("候補:")
        for candidate in candidates:
            if isinstance(candidate, dict):
                print(
                    f"- {candidate.get('pdes', '')}: "
                    f"{candidate.get('name', '')}"
                )


def main() -> None:
    print("表示方法を選択してください")
    print("1: JPL軌道要素をStellariumへ登録して表示")
    print("2: Stellarium標準天体を表示")
    print("3: JPLの観測地点別RA/DECを0.5秒間隔で取得してマーカー追尾")
    source_type = input("番号 > ").strip()

    try:
        if source_type == "1":
            run_jpl_orbit_cli()
        elif source_type == "2":
            run_standard_cli()
        elif source_type == "3":
            run_radec_tracking_cli()
        else:
            print("1、2、3のいずれかを入力してください。")
    except KeyboardInterrupt:
        APP_SERVICE.stop_tracking()
        print("処理を中止しました。")
    except ApplicationError as error:
        print_application_error(error)
    except ValueError as error:
        print(f"入力エラー: {error}")


if __name__ == "__main__":
    main()
