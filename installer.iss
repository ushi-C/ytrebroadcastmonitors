#define MyAppName "YVmonitor"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "YVmonitor"
#define MyAppExeName "YVmonitor.exe"
#ifndef MyAppDefaultDir
  #define MyAppDefaultDir "{autopf}\YVmonitor"
#endif

[Setup]
AppId={{A1E9F341-9B59-4A2C-9A84-8B82582D4A60}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={#MyAppDefaultDir}
DefaultGroupName=YVmonitor
DisableProgramGroupPage=yes
DisableDirPage=no
UsePreviousAppDir=no
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=dist
OutputBaseFilename=YVmonitor-Setup
SetupIconFile=icon.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务:";

[Files]
Source: "dist\YVmonitor.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "icon.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "channels.csv"; DestDir: "{app}"; Flags: onlyifdoesntexist skipifsourcedoesntexist

[Icons]
Name: "{autoprograms}\YVmonitor"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icon.ico"
Name: "{autodesktop}\YVmonitor"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icon.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "启动 YVmonitor"; Flags: nowait postinstall skipifsilent
