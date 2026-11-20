# Astelock

**Astelock**は、NASA JPL Horizonsから取得した小惑星のデータをStellariumに反映し、天体の表示位置を検証するためのWindows向けアプリケーションです。

卒業研究の成果物として開発しており、特に地球へ接近する小惑星について、Stellarium標準の表示とJPL Horizonsのデータを比較し、表示精度の向上を目指しています。

## ダウンロード・インストール

**[Astelock Windows版をダウンロード](https://github.com/hotaka-0206/stellarium_neo/releases/latest)**

GitHub Releasesの「Assets」から、次のインストーラをダウンロードしてください。

`Astelock-Setup-v0.2.0.exe`

- Windows 10 / 11の64bit環境向け
- Stellarium本体は別途インストールが必要
- インストールには管理者権限が必要
- JPL Horizons等の利用にはインターネット接続が必要
- PythonやFlutterの開発環境は不要

インストーラの案内に従ってセットアップを完了すると、スタートメニューからAstelockを起動できます。インストール時にデスクトップショートカットを作成することもできます。

**詳しい手順：[Windows版 使用手順](docs/WINDOWS_SETUP.md)**

## 主な機能

### 軌道要素方式

指定した日時を基準としてJPL Horizonsから小惑星の軌道要素を取得し、Stellariumへ登録・表示します。

- 基準日時の指定
- JST / UTCの切り替え
- JPL Horizonsからの軌道要素取得
- Stellariumへの小惑星登録・表示

### RA / Dec方式

指定した観測地点と時間範囲について、JPL Horizonsから赤経（RA）・赤緯（Dec）を取得し、Stellarium上にマーカーとして表示します。

取得後はStellariumの時刻に合わせてマーカーを更新し、天体位置を追尾します。

- 観測地点の緯度・経度・標高の指定
- 地図による地点選択
- Windowsの位置情報機能による現在地取得
- 開始日時・終了日時の指定
- JST / UTCへの対応
- 最短0.5秒間隔でのRA / Decデータ取得
- マーカー表示および追尾

RA / Decの取得範囲は最大12時間です。

なお、データの取得間隔とStellarium画面上の更新間隔が常に一致するわけではありません。

## 天体の検索

1つの入力欄から、複数の形式で小惑星を指定できます。

| 入力形式 | 例 |
|---|---|
| 天体名 | `Apophis` |
| 小惑星番号 | `99942` |
| 仮符号 | `2004 MN4` |
| SPK-ID | `2099942` |
| 日本語名 | `アポフィス` |

入力された識別子をJPLの天体情報と照合し、主識別子、小惑星番号、仮符号、SPK-ID等をGUI上で確認できます。

## Stellariumとの連携

AstelockはStellariumのRemote Control機能を使用します。

初期設定の一部は自動化されており、AstelockからStellariumを起動する際に、必要に応じて以下の設定を適用します。

- Remote Controlプラグインの有効化
- Remote Controlの自動起動
- 通信ポート8090の設定
- フルスクリーン表示の無効化

また、インストール時にはStellarium Remote Controlへの外部からの受信通信を制限するファイアウォール規則を設定します。

これらの処理により、Stellariumの設定ファイルやWindowsのファイアウォール設定が変更される場合があります。

## システム構成

GUIにFlutter、バックエンドにPython / FastAPIを使用しています。

```text
Flutter GUI
    |
    | ローカルHTTP API
    v
Python / FastAPI
    |
    +-- JPL Horizons / SBDB
    |     +-- 天体検索
    |     +-- 軌道要素取得
    |     +-- RA / Dec取得
    |
    +-- Stellarium Remote Control
          +-- 時刻・観測地点設定
          +-- 天体登録・表示
          +-- RA / Decマーカー表示・追尾
```

GUIと実処理を分離し、Pythonバックエンドの処理をローカルAPI経由で呼び出す構成です。

Windows配布版では、PythonバックエンドをPyInstallerで実行ファイル化し、Flutter GUIとともにインストーラに組み込んでいます。

## 利用規約・プライバシーポリシー

本ソフトウェアは卒業研究の成果物として無償で公開しています。

動作保証や継続的な保守・サポートを約束するものではありません。

利用前に以下の文書を確認してください。

- [利用規約](docs/TERMS_OF_USE.md)
- [プライバシーポリシー](docs/PRIVACY_POLICY.md)
- [第三者ソフトウェア・サービスに関する通知](docs/THIRD_PARTY_NOTICES.md)

インストーラにも利用規約、プライバシーポリシーおよび第三者ライセンスの通知を同梱しています。

AstelockはNASA/JPLおよびStellariumの公式製品ではありません。

## 主な使用技術

- Python / FastAPI
- Flutter / Dart
- JPL Horizons
- JPL Small-Body Database
- Stellarium
- Stellarium Remote Control API
- PyInstaller
- Inno Setup
- OpenStreetMap
- OpenTopoData

## 主なファイル・ディレクトリ

```text
stellarium_neo/
├── api/
│   └── server.py
├── stellarium_neo_gui/
├── installer/
├── docs/
│   └── WINDOWS_SETUP.md
├── app_service.py
├── backend_main.py
├── get_orbit.py
├── jpl_to_stel.py
├── main.py
├── observer.py
├── orbit_service.py
├── radec_store.py
├── stellarium_service.py
└── tracking_service.py
```

### GUI・API

- `stellarium_neo_gui/`：FlutterによるGUI
- `api/server.py`：GUIから呼び出すFastAPIサーバー
- `app_service.py`：GUIやAPIから利用する処理の統合

### JPL・Stellarium連携

- `get_orbit.py`：JPL Horizonsとの通信
- `orbit_service.py`：軌道要素方式・RA / Dec方式
- `stellarium_service.py`：Stellarium操作
- `tracking_service.py`：RA / Dec追尾処理

### 起動・配布

- `backend_main.py`：配布版バックエンドの起動
- `main.py`：CLI動作確認用
- `installer/`：Windowsインストーラ関連ファイル

## 研究目的

Stellariumでは小惑星を軌道要素から計算して表示できますが、地球へ非常に接近する天体では、小さな軌道誤差が天球上の位置誤差として大きく表れる可能性があります。

本研究では、JPL Horizonsのデータを利用した表示方法を実装し、次の3種類の表示位置を比較・検証します。

1. Stellarium標準表示
2. JPLの軌道要素を使用した表示
3. JPLのRA / Decを直接使用した表示

特にApophisなどの地球接近天体を対象とし、接近時に適した表示方法を検討します。

## 開発状況

Windows版のFlutter GUI、Pythonバックエンド、Stellarium連携およびインストーラ配布を実装しています。

今後は表示精度の定量的な比較・検証や、他OSへの対応などを検討します。
