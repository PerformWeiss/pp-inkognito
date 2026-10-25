; Inno Setup: Windows-Installer für PP-Inkognito (unsigniert). Wird von packaging/build.py aufgerufen.
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6F1D8B7A-3C52-4B7E-9A64-5D1E0C2B9F47}
AppName=PP-Inkognito
AppVersion={#AppVersion}
AppPublisher=PerformPlus GmbH
AppPublisherURL=https://performplus.de
DefaultDirName={autopf}\PP-Inkognito
DefaultGroupName=PP-Inkognito
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir={#OutDir}
OutputBaseFilename=PP-Inkognito-{#AppVersion}-Windows-Setup
SetupIconFile={#IconFile}
UninstallDisplayIcon={app}\PP-Inkognito.exe
LicenseFile={#SourceDir}\LICENSE.txt
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "german"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "Symbol auf dem Desktop anlegen"; GroupDescription: "Zusätzliche Symbole:"

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\PP-Inkognito"; Filename: "{app}\PP-Inkognito.exe"
Name: "{autodesktop}\PP-Inkognito"; Filename: "{app}\PP-Inkognito.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\PP-Inkognito.exe"; Description: "PP-Inkognito jetzt starten"; Flags: nowait postinstall skipifsilent
