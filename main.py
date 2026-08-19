from datetime import datetime, timedelta, timezone

from get_orbit import AmbiguousTargetError, JplApiError, TargetResolutionError
from observer import ObserverLocation
from orbit_service import (
    DEFAULT_RADEC_TRACK_UPDATE_INTERVAL_SECONDS,
    FetchMode,
    OrbitServiceError,
    TrackingEndReason,
    get_radec_request_summary,
    inspect_jpl_target,
    show_jpl_radec_series,
    show_jpl_target,
    show_standard_target,
    track_jpl_radec_series,
)
from stellarium_service import StellariumError

DEFAULT_OBSERVER = ObserverLocation(
    latitude_deg=35.4978,
    longitude_deg=133.025,
    altitude_m=0,
    name="MatsueKosen",
)


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
    start_text = input(
        "取得開始日時 形式：yyyymmddHHMMSS > "
    ).strip()
    end_text = input(
        "取得終了日時 形式：yyyymmddHHMMSS > "
    ).strip()

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
    name = input(
        f"地点名 Enter={DEFAULT_OBSERVER.name} > "
    ).strip()

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


def input_jpl_settings() -> tuple[str, FetchMode, str | None]:
    identifier = input_identifier()
    status = inspect_jpl_target(identifier)
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
        return identifier, mode, None

    print(f"[{identity.section_id}] はまだ登録されていません。")
    answer = input("JPLデータを新しく追加しますか? y/n > ").strip().lower()

    if answer != "y":
        raise KeyboardInterrupt

    display_name = input(
        f"Stellariumでの表示名 Enterで {identity.default_display_name} > "
    ).strip()

    return identifier, FetchMode.AUTO, display_name or None


def main() -> None:
    print("表示方法を選択してください")
    print("1: JPL軌道要素をStellariumへ登録して表示")
    print("2: Stellarium標準天体を表示")
    print("3: JPLの観測地点別RA/DECを表示")
    source_type = input("番号 > ").strip()

    if source_type not in {"1", "2", "3"}:
        print("1、2、3のいずれかを入力してください。")
        return

    try:
        if source_type == "1":
            dt = input_datetime()
            identifier, fetch_mode, display_name = input_jpl_settings()
            result = show_jpl_target(
                identifier=identifier,
                dt=dt,
                fetch_mode=fetch_mode,
                display_name=display_name,
            )
            print(f"表示完了: {result.focus_target}")
            print(f"UTC: {result.datetime_utc.strftime('%Y-%m-%d %H:%M:%S')}")

        elif source_type == "2":
            dt = input_datetime()
            target = input(
                "Stellarium標準の天体名または天体番号を入力してください > "
            ).strip()
            result = show_standard_target(target=target, dt=dt)
            print(f"表示完了: {result.focus_target}")
            print(f"UTC: {result.datetime_utc.strftime('%Y-%m-%d %H:%M:%S')}")

        else:
            start_dt, end_dt = input_datetime_range()
            summary = get_radec_request_summary(start_dt, end_dt)
            identifier = input_identifier()
            observer = input_observer_location()

            print(f"取得間隔: {summary.step_seconds}秒（固定）")
            print(f"取得時間: {summary.duration_seconds / 3600:.3f}時間")
            print(f"取得予定点数: {summary.point_count:,}点")

            result = show_jpl_radec_series(
                identifier=identifier,
                start_dt=start_dt,
                end_dt=end_dt,
                observer=observer,
            )
            first = result.series.points[0]
            last = result.series.points[-1]

            print(f"取得完了: {result.identity.full_name}")
            print(f"取得点数: {result.series.point_count:,}点")
            print(
                "取得範囲[UTC]: "
                f"{result.series.start_datetime_utc.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]} ～ "
                f"{result.series.end_datetime_utc.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}"
            )
            print(
                "開始位置: "
                f"RA={first.ra_deg:.10f} deg, "
                f"DEC={first.dec_deg:.10f} deg"
            )
            print(
                "終了位置: "
                f"RA={last.ra_deg:.10f} deg, "
                f"DEC={last.dec_deg:.10f} deg"
            )
            print(
                "観測地点: "
                f"{result.observer.name} "
                f"({result.observer.latitude_deg}, "
                f"{result.observer.longitude_deg}, "
                f"{result.observer.altitude_m} m)"
            )
            print("Stellariumには取得範囲の開始位置を表示しました。")
            print(
                "マーカー更新間隔: "
                f"{DEFAULT_RADEC_TRACK_UPDATE_INTERVAL_SECONDS}秒"
            )
            print(
                "追尾を開始します。Stellarium側で時間を進めると、"
                "現在時刻に対応したRA/DECへマーカーが移動します。"
            )
            print("Ctrl+Cで追尾を終了")

            tracking = track_jpl_radec_series(
                displayed=result,
                update_interval_seconds=(
                    DEFAULT_RADEC_TRACK_UPDATE_INTERVAL_SECONDS
                ),
            )

            if tracking.reason is TrackingEndReason.RANGE_END:
                print("取得範囲の終了時刻を超えたため追尾を終了しました。")
            else:
                print("追尾を終了しました。")

            print(f"マーカー更新回数: {tracking.update_count:,}回")

    except KeyboardInterrupt:
        print("処理を中止しました。")
    except AmbiguousTargetError as error:
        print(str(error))
        print("候補:")
        for candidate in error.candidates:
            print(f"- {candidate.get('pdes', '')}: {candidate.get('name', '')}")
    except (
        TargetResolutionError,
        JplApiError,
        OrbitServiceError,
        StellariumError,
        ValueError,
    ) as error:
        print(f"エラー: {error}")


if __name__ == "__main__":
    main()
