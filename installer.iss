#define MyAppName "Enki Agency Uniq"
#define MyAppVersion "2.5.1"
#define MyAppPublisher "Enki Agency"
#define MyAppExeName "Enki Agency Uniq.exe"

[Setup]
AppId={{A8F7E919-927B-4C51-8CDA-ENKI2501}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\Enki Agency Uniq
DefaultGroupName=Enki Agency Uniq
OutputDir=installer
OutputBaseFilename=Enki_Agency_Uniq_2.5.1_Setup
SetupIconFile=EnkiAgencyUniq.ico
Compression=lzma2/ultra64
SolidCompression=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
WizardStyle=modern
UninstallDisplayIcon={app}\Enki Agency Uniq.exe
CloseApplications=yes
RestartApplications=yes
DisableProgramGroupPage=yes

[Files]
Source: "dist\Enki Agency Uniq\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Enki Agency Uniq"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Enki Agency Uniq"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Ярлыки:"; Flags: checkedonce

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Запустить Enki Agency Uniq"; Flags: nowait postinstall skipifsilent
