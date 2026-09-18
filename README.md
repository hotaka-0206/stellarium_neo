# stellarium_neo

JPL Horizonsから取得した小惑星のデータをStellariumへ反映し、天体の表示位置を検証する卒業研究用プロジェクトです。

特に地球へ接近する小惑星について、Stellarium標準の表示とJPL Horizonsのデータを比較し、接近時における表示精度の向上を目的としています。

## 概要

本システムでは、JPL Horizonsから取得したデータを使用して小惑星をStellarium上に表示します。

現在、次の2つの表示方式に対応しています。

### 軌道要素方式

指定した日時を基準としてJPL Horizonsから小惑星の軌道要素を取得し、Stellariumへ登録・表示します。

* 基準日時を指定可能
* JST / UTCに対応
* JPLから軌道要素を取得
* 取得した軌道要素をStellariumへ登録
* 登録した天体をStellarium上に表示

### RA / Dec方式

指定した観測地点・時間範囲について、JPL HorizonsからRA（赤経）/ Dec（赤緯）を取得し、Stellarium上にマーカーとして表示します。

取得後はStellariumの時刻に合わせてマーカーを更新し、天体位置を追尾します。

* 観測地点の緯度・経度・標高を指定可能
* 開始日時・終了日時を指定可能
* JST / UTCに対応
* RA / Decの取得間隔は0.5秒
* 取得した位置をStellarium上に表示
* Stellariumの時刻に合わせたRA / Dec追尾

現在、RA / Decの取得範囲は最大12時間です。

---

## 天体の検索

1つの入力欄から、複数の形式で小惑星を指定できます。

例：

* 天体名：`Apophis`
* 小惑星番号：`99942`
* 仮符号：`2004 MN4`
* SPK-ID：`2099942`
* 日本語名：`アポフィス`

入力された識別子はJPL Horizons上の天体へ解決され、主識別子、小惑星番号、仮符号、SPK-IDなどの情報をGUI上で確認できます。

---

## システム構成

GUIにはFlutter、バックエンドにはPython / FastAPIを使用しています。

```text
Flutter GUI
    │
    │ HTTP
    ▼
Python / FastAPI
    │
    ├── JPL Horizons
    │     ├── 天体検索
    │     ├── 軌道要素取得
    │     └── RA / Dec取得
    │
    └── Stellarium Remote Control
          ├── 時刻・観測地点設定
          ├── 天体表示
          └── RA / Decマーカー表示・追尾
```

GUIとPython側の処理を分離し、FlutterからローカルAPIを経由してJPL HorizonsおよびStellariumを操作する構成になっています。

---

## Windows版を使用する

Windows向けの実行ファイルはGitHubの **Releases** から配布しています。

Windows版のダウンロード、Stellariumのインストール、Remote Controlの設定、プログラムの起動方法については、次の手順書を参照してください。

### [Windows版 使用手順](docs/WINDOWS_SETUP.md)

初期設定完了後は、配布された実行ファイルを起動することで、必要なバックエンドとStellariumも自動的に起動します。

PythonやFlutterの開発環境を別途用意する必要はありません。

---

## 主な使用技術

* Python
* FastAPI
* Flutter / Dart
* JPL Horizons
* Stellarium
* Stellarium Remote Control API
* PyInstaller

---

## 主なファイル・ディレクトリ

```text
stellarium_neo/
├── api/
│   └── server.py
├── stellarium_neo_gui/
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

### `stellarium_neo_gui/`

Flutterで作成したGUIです。

天体検索、表示方式の選択、日時・観測地点の入力、JPLデータの取得、Stellariumへの表示などを行います。

### `api/server.py`

Flutter GUIからPython側の処理を呼び出すためのFastAPIサーバーです。

### `app_service.py`

GUIやAPIから使用する処理をまとめるアプリケーションサービスです。

### `get_orbit.py`

JPL Horizonsとの通信や天体データの取得を担当します。

### `orbit_service.py`

軌道要素方式およびRA / Dec方式に関する処理を担当します。

### `stellarium_service.py`

Stellarium Remote Controlを利用したStellarium操作を担当します。

### `tracking_service.py`

取得したRA / Decデータを使用した追尾処理を担当します。

### `backend_main.py`

配布版で使用するPythonバックエンドの起動処理です。

### `main.py`

CLIでの動作確認用です。

---

## 研究目的

Stellariumでは小惑星を軌道要素から計算して表示できますが、地球へ非常に接近する天体では、小さな軌道誤差が天球上の位置誤差として大きく表れる可能性があります。

本研究では、JPL Horizonsのデータを利用した表示方法を実装し、Stellarium標準の表示位置との比較・検証を行います。

特にApophisなどの地球接近天体を対象として、

* Stellarium標準表示
* JPLの軌道要素を使用した表示
* JPLのRA / Decを直接使用した表示

を比較し、接近時に適した表示方法を検討します。

---

## 開発状況

現在はWindows版を中心に開発・動作確認を行っています。

* Flutter GUIとPythonバックエンドの連携
* JPL Horizonsによる天体検索
* 軌道要素の取得・Stellarium表示
* RA / Decの取得・Stellarium表示
* RA / Decによる追尾
* Windows向け配布用実行ファイル
* GUI起動時のバックエンド・Stellarium自動起動

まで実装しています。

今後、表示精度の比較・検証や他OSへの対応などを進めます。
