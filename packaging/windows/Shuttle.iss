#ifndef SourceDir
  #error SourceDir must be supplied by the packaging script
#endif
#ifndef OutputDir
  #error OutputDir must be supplied by the packaging script
#endif
#ifndef OutputBaseFilename
  #error OutputBaseFilename must be supplied by the packaging script
#endif
#ifndef AppVersion
  #error AppVersion must be supplied by the packaging script
#endif

[Setup]
AppId={{5E995F77-24C7-4D9E-9659-9E3895E9ED66}
AppName=Shuttle
AppVersion={#AppVersion}
AppPublisher=Shuttle
AppPublisherURL=https://github.com/aldi-f/shuttle
AppSupportURL=https://github.com/aldi-f/shuttle/issues
AppUpdatesURL=https://github.com/aldi-f/shuttle/releases
DefaultDirName={localappdata}\Programs\Shuttle
DefaultGroupName=Shuttle
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#OutputDir}
OutputBaseFilename={#OutputBaseFilename}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
UninstallDisplayIcon={app}\Shuttle.exe

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Shuttle"; Filename: "{app}\Shuttle.exe"
Name: "{userdesktop}\Shuttle"; Filename: "{app}\Shuttle.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Run]
Filename: "{app}\Shuttle.exe"; Description: "Launch Shuttle"; Flags: nowait postinstall skipifsilent
