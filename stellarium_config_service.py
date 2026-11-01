
import csv
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path


REQUIRED_SETTINGS = (
    ("plugins_load_at_startup", "RemoteControl", "true"),
    ("RemoteControl", "autostart", "true"),
    ("RemoteControl", "port", "8090"),
    ("video", "fullscreen", "false"),
)


def _section_name(line: str) -> str | None:
    match = re.fullmatch(
        r"[ \t]*\[([^\]\r\n]+)\][ \t]*",
        line.rstrip("\r\n"),
    )
    return match.group(1).lower() if match else None


def _set_option(
    lines: list[str],
    section: str,
    key: str,
    value: str,
    newline: str,
) -> None:
    """対象セクション内の指定キーだけを変更する。"""
    sections = [
        i for i, line in enumerate(lines)
        if _section_name(line) == section.lower()
    ]

    if len(sections) > 1:
        raise ValueError(f"セクションが重複しています: {section}")

    if not sections:
        if lines and not lines[-1].endswith(("\r", "\n")):
            lines[-1] += newline
        lines.extend([
            f"[{section}]{newline}",
            f"{key} = {value}{newline}",
        ])
        return

    start = sections[0] + 1
    end = next(
        (
            i for i in range(start, len(lines))
            if _section_name(lines[i]) is not None
        ),
        len(lines),
    )

    pattern = re.compile(
        rf"^([ \t]*{re.escape(key)}[ \t]*=[ \t]*)"
        r"([^\r\n]*)(\r?\n)?$",
        re.IGNORECASE,
    )

    matches = [
        (i, match)
        for i in range(start, end)
        if (match := pattern.match(lines[i])) is not None
    ]

    if len(matches) > 1:
        raise ValueError(f"設定項目が重複しています: {section}/{key}")

    if matches:
        i, match = matches[0]
        if match.group(2).strip().lower() != value.lower():
            lines[i] = (
                match.group(1)
                + value
                + (match.group(3) or "")
            )
        return

    if end > 0 and not lines[end - 1].endswith(("\r", "\n")):
        lines[end - 1] += newline

    lines.insert(end, f"{key} = {value}{newline}")


def update_stellarium_config_text(text: str) -> str:
    """INI文字列を更新する。ファイル操作は行わない。"""
    newline = "\r\n" if "\r\n" in text else "\n"
    lines = text.splitlines(keepends=True)

    for section, key, value in REQUIRED_SETTINGS:
        _set_option(lines, section, key, value, newline)

    return "".join(lines)


def is_stellarium_process_running() -> bool:
    result = subprocess.run(
        [
            "tasklist",
            "/FI", "IMAGENAME eq stellarium.exe",
            "/FO", "CSV",
            "/NH",
        ],
        capture_output=True,
        text=True,
        errors="replace",
        check=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )

    return any(
        row and row[0].lower() == "stellarium.exe"
        for row in csv.reader(result.stdout.splitlines())
    )


def apply_stellarium_initial_settings(
    config_path: str | Path | None = None,
    stellarium_exe_path: str | Path | None = None,
    default_config_path: str | Path | None = None,
) -> dict:
    """Windowsの既存・初回設定を適用する。GUIから扱える辞書を返す。"""
    if os.name != "nt":
        return {
            "success": False,
            "code": "UNSUPPORTED_OS",
            "message": "現在はWindowsのみ対応しています。",
        }

    if config_path is None:
        appdata = os.environ.get("APPDATA")
        if not appdata:
            return {
                "success": False,
                "code": "APPDATA_NOT_FOUND",
                "message": "Windowsの設定フォルダが見つかりません。",
            }
        path = Path(appdata) / "Stellarium" / "config.ini"
    else:
        path = Path(config_path)

    # 初回起動の場合は、Stellariumの公式ひな形を使用する。
    # 数項目しかない独自のconfig.iniを新規作成しない。
    creating = not path.is_file()
    default_path = None
    if creating:
        if default_config_path is not None:
            default_path = Path(default_config_path)
        else:
            exe = Path(
                stellarium_exe_path
                if stellarium_exe_path is not None
                else r"C:\Program Files\Stellarium\stellarium.exe"
            )
            default_path = exe.parent / "data" / "default_cfg.ini"

        if not default_path.is_file():
            return {
                "success": False,
                "code": "DEFAULT_CONFIG_NOT_FOUND",
                "message": (
                    "Stellariumの初期設定ひな形が見つかりません: "
                    + str(default_path)
                ),
            }

    temp_path = None
    try:
        raw = default_path.read_bytes() if creating else path.read_bytes()
        has_bom = raw.startswith(b"\xef\xbb\xbf")
        original = raw.decode("utf-8-sig")
        updated = update_stellarium_config_text(original)

        if not creating and updated == original:
            return {
                "success": True,
                "changed": False,
                "created": False,
                "restart_required": False,
            }

        # 画面操作中にconfig.iniを編集して設定が上書きされるのを防ぐ。
        if is_stellarium_process_running():
            return {
                "success": False,
                "code": "STELLARIUM_RUNNING",
                "message": "Stellariumを終了してから設定してください。",
            }

        backup_path = None
        if not creating:
            backup = path.with_name("config.ini.bak")
            if not backup.exists():
                shutil.copy2(path, backup)
            backup_path = str(backup)

        path.parent.mkdir(parents=True, exist_ok=True)
        data = (
            (b"\xef\xbb\xbf" if has_bom else b"")
            + updated.encode("utf-8")
        )

        fd, temp_name = tempfile.mkstemp(
            prefix="config_", suffix=".tmp", dir=path.parent
        )
        temp_path = Path(temp_name)

        with os.fdopen(fd, "wb") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())

        # 判定後に別プロセスが生成していた場合は、上書きしない。
        if creating and path.exists():
            raise FileExistsError(
                "設定ファイルが別プロセスによって作成されました。"
            )

        os.replace(temp_path, path)

        result = {
            "success": True,
            "changed": True,
            "created": creating,
            "restart_required": True,
        }
        if backup_path is not None:
            result["backup_path"] = backup_path
        return result

    except (OSError, UnicodeError, ValueError) as error:
        return {
            "success": False,
            "code": "CONFIG_UPDATE_FAILED",
            "message": str(error),
        }
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
