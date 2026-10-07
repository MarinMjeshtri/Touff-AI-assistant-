; Inno Setup 6 script for Touff. Built by packaging\build.ps1, which passes the version:
;   ISCC.exe /DAppVersion=0.1.0 packaging\installer.iss
; Per-user install (no admin) to %LOCALAPPDATA%\Programs\Touff.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef AppDir
  #define AppDir "dist\Touff"
#endif
#ifndef OutputDir
  #define OutputDir "dist"
#endif
#ifndef IconFile
  #define IconFile "build\touff.ico"
#endif

[Setup]
AppId={{1B96F3BB-1915-44FD-A887-A47E0CDA9ECE}
AppName=Touff
AppVersion={#AppVersion}
AppVerName=Touff {#AppVersion}
AppPublisher=Touff
AppPublisherURL=https://github.com/MarinMjeshtri/Touff-AI-assistant-
DefaultDirName={localappdata}\Programs\Touff
DefaultGroupName=Touff
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir={#OutputDir}
OutputBaseFilename=Touff-Setup-{#AppVersion}
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\Touff.exe
UninstallDisplayName=Touff
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Messages]
FinishedLabel=Touff is installed.%n%nThe first launch downloads her speech models once (about 600 MB); she greets you when she's ready.%n%nGot an NVIDIA graphics card? Install the expressive voice pack from Settings: much faster ears and a voice that laughs, sighs and shouts.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "autostart"; Description: "Start Touff with Windows"; GroupDescription: "Startup:"

[Files]
Source: "{#AppDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Touff"; Filename: "{app}\Touff.exe"
Name: "{autodesktop}\Touff"; Filename: "{app}\Touff.exe"; Tasks: desktopicon

[Registry]
; Same value touff\autostart.py writes, so the Settings toggle and this box agree.
; --background: at login she goes straight to the tray (launching Touff.exe by hand opens settings).
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Touff"; ValueData: """{app}\Touff.exe"" --background"; Tasks: autostart

[Run]
Filename: "{app}\Touff.exe"; Description: "{cm:LaunchProgram,Touff}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; She lives in the tray (and may have a GPU voice worker running): stop her first.
Filename: "{sys}\taskkill.exe"; Parameters: "/F /T /IM Touff.exe"; Flags: runhidden; RunOnceId: "StopTouff"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
; Downloaded speech models and the expressive voice pack (re-downloadable, can be GBs).
Type: filesandordirs; Name: "{localappdata}\Touff"

[Code]
const
  RunKey = 'Software\Microsoft\Windows\CurrentVersion\Run';

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  Value: String;
begin
  if CurUninstallStep = usUninstall then
  begin
    { Also catches the entry made by the Settings toggle, but only if it points at this install. }
    if RegQueryStringValue(HKCU, RunKey, 'Touff', Value) and (Pos(Lowercase(ExpandConstant('{app}')), Lowercase(Value)) > 0) then
      RegDeleteValue(HKCU, RunKey, 'Touff');
  end;
  if (CurUninstallStep = usPostUninstall) and not UninstallSilent and DirExists(ExpandConstant('{userappdata}\Touff')) then
  begin
    if MsgBox('Also delete your Touff settings, custom commands, memories and history?' + #13#10 +
              '(Keep them if you plan to install Touff again.)', mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
      DelTree(ExpandConstant('{userappdata}\Touff'), True, True, True);
  end;
end;
