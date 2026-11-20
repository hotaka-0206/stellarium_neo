
#define MyAppName "Astelock"
#define MyAppVersion "0.2.0"
#define MyAppExeName "stellarium_neo_gui.exe"

[Setup]
AppId=StellariumNeo
AppName={#MyAppName}
AppVersion={#MyAppVersion}

DefaultDirName={autopf}\Astelock
DefaultGroupName=Astelock

UninstallDisplayIcon={app}\{#MyAppExeName}

OutputDir=Output
OutputBaseFilename=Astelock-Setup-v0.2.0-test

Compression=lzma2
SolidCompression=yes
WizardStyle=modern

PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible

SetupIconFile=assets\astelock.ico

LicenseFile=legal\TERMS.txt
InfoBeforeFile=legal\PRIVACY.txt

[Languages]
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"

[Tasks]
Name: "desktopicon"; Description: "デスクトップにショートカットを作成"

[Files]
; Firewall setup script (embedded in installer)
Source: "setup-firewall.ps1"; Flags: dontcopy noencryption

; Flutter GUI and Python backend
Source: "..\release_package\StellariumNeo\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

; Legal documents and third-party licenses
Source: "legal\TERMS.txt"; DestDir: "{app}\legal"; Flags: ignoreversion
Source: "legal\PRIVACY.txt"; DestDir: "{app}\legal"; Flags: ignoreversion
Source: "legal\THIRD_PARTY_NOTICES.txt"; DestDir: "{app}\legal"; Flags: ignoreversion
Source: "legal\FLUTTER_NOTICES.txt"; DestDir: "{app}\legal"; Flags: ignoreversion
Source: "legal\PYTHON_NOTICES.txt"; DestDir: "{app}\legal"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Astelock"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\Astelock"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

Name: "{autoprograms}\Astelock - 利用規約"; Filename: "{sys}\notepad.exe"; Parameters: """{app}\legal\TERMS.txt"""
Name: "{autoprograms}\Astelock - プライバシーポリシー"; Filename: "{sys}\notepad.exe"; Parameters: """{app}\legal\PRIVACY.txt"""
Name: "{autoprograms}\Astelock - 第三者ライセンス"; Filename: "{sys}\notepad.exe"; Parameters: """{app}\legal\THIRD_PARTY_NOTICES.txt"""

[Code]
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
  PowerShellExe: String;
  Params: String;
  Output: TExecOutput;
  I: Integer;
begin
  Result := '';
  NeedsRestart := False;

  ExtractTemporaryFile('setup-firewall.ps1');

  PowerShellExe := ExpandConstant(
    '{sys}\WindowsPowerShell\v1.0\powershell.exe'
  );

  Params := '-NoProfile -NonInteractive -ExecutionPolicy Bypass -File "' +
    ExpandConstant('{tmp}\setup-firewall.ps1') + '"';

  try
    if not ExecAndCaptureOutputWithNativeSysDir(
      PowerShellExe,
      Params,
      '',
      SW_HIDE,
      ewWaitUntilTerminated,
      ResultCode,
      Output
    ) then
    begin
      Result := 'ファイアウォール設定を起動できませんでした。';
    end
    else if ResultCode <> 0 then
    begin
      Result := 'ファイアウォール設定に失敗しました。' + #13#10 +
        '終了コード: ' + IntToStr(ResultCode);

      for I := 0 to GetArrayLength(Output.StdErr) - 1 do
      begin
        Result := Result + #13#10 + Output.StdErr[I];
      end;
    end;
  except
    Result := 'PowerShell実行エラー: ' + GetExceptionMessage;
  end;
end;
