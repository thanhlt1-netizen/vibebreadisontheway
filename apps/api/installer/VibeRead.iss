#ifndef AppVersion
  #define AppVersion "0.1.0"
#endif
[Setup]
AppId={{B3F1C7D2-5A1E-4C55-9F0B-7A2D6E8C41AA}
AppName=VibeRead
AppVersion={#AppVersion}
AppPublisher=VibeRead
DefaultDirName={autopf}\VibeRead
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\dist-installer
OutputBaseFilename=VibeRead-Setup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\VibeRead.exe
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
[Tasks]
Name: "desktopicon"; Description: "Tạo biểu tượng VibeRead ngoài màn hình Desktop"; GroupDescription: "Lối tắt:"
[Files]
Source: "..\dist\VibeRead\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion createallsubdirs
Source: "MicrosoftEdgeWebview2Setup.exe"; DestDir: "{tmp}"; Flags: deleteafterinstall skipifsourcedoesntexist; Check: NeedWebView2
[Icons]
Name: "{autoprograms}\VibeRead"; Filename: "{app}\VibeRead.exe"
Name: "{autodesktop}\VibeRead"; Filename: "{app}\VibeRead.exe"; Tasks: desktopicon
[Run]
Filename: "{tmp}\MicrosoftEdgeWebview2Setup.exe"; Parameters: "/silent /install"; StatusMsg: "Đang cài thành phần hiển thị WebView2..."; Flags: waituntilterminated skipifdoesntexist; Check: NeedWebView2
Filename: "{app}\VibeRead.exe"; Description: "Mở VibeRead ngay"; Flags: nowait postinstall skipifsilent
[Code]
function HasWV2(Root: Integer; Key: String): Boolean;
var v: String;
begin
  Result := RegQueryStringValue(Root, Key, 'pv', v) and (v <> '') and (v <> '0.0.0.0');
end;
function NeedWebView2: Boolean;
begin
  Result := not (HasWV2(HKLM, 'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}')
              or HasWV2(HKCU, 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'));
end;
