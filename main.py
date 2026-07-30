from datetime import datetime, timedelta, timezone

from get_orbit import AmbiguousTargetError, JplApiError, TargetResolutionError
from orbit_service import (
    FetchMode,
    OrbitServiceError,
    inspect_jpl_target,
    show_jpl_target,
    show_standard_target,
)
from stellarium_service import StellariumError


def input_datetime() -> datetime:
    date_text = input("日時 形式：yyyymmddHHMMSS > ").strip()

    print("時間系の番号を入力してください")
    print("1: UTC")
    print("2: JST")
    time_type = input("番号 > ").strip()

    dt = datetime.strptime(date_text, "%Y%m%d%H%M%S")

    if time_type == "2":
        return dt.replace(tzinfo=timezone(timedelta(hours=9)))

    return dt.replace(tzinfo=timezone.utc)


def input_jpl_settings() -> tuple[str, FetchMode, str | None]:
    identifier = input(
        "天体名・小惑星番号・仮符号・SPK-IDを入力してください > "
    ).strip()
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
    print("表示する天体データを選択してください")
    print("1: JPL")
    print("2: Stellarium標準")
    source_type = input("番号 > ").strip()

    if source_type not in {"1", "2"}:
        print("1または2を入力してください。")
        return

    try:
        dt = input_datetime()

        if source_type == "1":
            identifier, fetch_mode, display_name = input_jpl_settings()
            result = show_jpl_target(
                identifier=identifier,
                dt=dt,
                fetch_mode=fetch_mode,
                display_name=display_name,
            )
        else:
            target = input(
                "Stellarium標準の天体名または天体番号を入力してください > "
            ).strip()
            result = show_standard_target(target=target, dt=dt)

        print(f"表示完了: {result.focus_target}")
        print(f"UTC: {result.datetime_utc.strftime('%Y-%m-%d %H:%M:%S')}")

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
