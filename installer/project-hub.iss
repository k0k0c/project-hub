#define AppName "Project Hub"
#define AppVersion "0.3.2"
#define AppId "{{8A1A7A0D-8D7A-4F7A-9C5A-5B83D2D0E7A1}"

#ifndef PayloadDir
  #define PayloadDir "..\payload"
#endif
#ifndef OutputDir
  #define OutputDir "output"
#endif
#ifndef BuildVersion
  #define BuildVersion AppVersion
#endif

[Setup]
AppId={#AppId}
AppName={#AppName}
AppVersion={#BuildVersion}
AppPublisher=Project Hub
DefaultDirName={localappdata}\Programs\ProjectHub
PrivilegesRequired=lowest
SetupLogging=yes
UsePreviousAppDir=yes
CloseApplications=no
RestartApplications=no
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
MinVersion=10.0
OutputDir={#OutputDir}
OutputBaseFilename=ProjectHub-{#BuildVersion}
SetupIconFile={#SourcePath}\brand.ico
WizardStyle=modern dark polar includetitlebar
WizardImageFile={#SourcePath}\wizard.bmp
WizardSmallImageFile={#SourcePath}\wizard-small.bmp
DisableProgramGroupPage=yes
DisableDirPage=no
DirExistsWarning=no
Uninstallable=yes
ChangesAssociations=no
Compression=lzma2
SolidCompression=yes
ShowLanguageDialog=yes
; User data is outside {app} and is intentionally never removed by uninstall.

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Private temporary maintenance runtime survives replacement of {app}.
Source: "{#PayloadDir}\runtime\*"; DestDir: "{tmp}\maintenance\runtime"; Flags: dontcopy recursesubdirs createallsubdirs
Source: "{#PayloadDir}\app\scripts\hub_launcher.py"; DestDir: "{tmp}\maintenance\app\scripts"; Flags: dontcopy
Source: "{#PayloadDir}\app\scripts\hub_lifecycle.py"; DestDir: "{tmp}\maintenance\app\scripts"; Flags: dontcopy
Source: "{#PayloadDir}\app\scripts\hub_instance.py"; DestDir: "{tmp}\maintenance\app\scripts"; Flags: dontcopy
Source: "{#PayloadDir}\app\scripts\hub_desktop.py"; DestDir: "{tmp}\maintenance\app\scripts"; Flags: dontcopy
Source: "{#PayloadDir}\app\scripts\hub_update.py"; DestDir: "{tmp}\maintenance\app\scripts"; Flags: dontcopy
Source: "{#PayloadDir}\runtime\*"; DestDir: "{app}\runtime"; Flags: ignoreversion recursesubdirs createallsubdirs; Check: NeedsRuntimeFile
Source: "{#PayloadDir}\*"; DestDir: "{app}"; Excludes: "runtime\*"; Flags: ignoreversion recursesubdirs createallsubdirs

[Registry]
; Keep the external configuration pointer after uninstall for later reinstall.
Root: HKCU; Subkey: "Software\ProjectHub"; ValueType: string; ValueName: "InstallationConfig"; ValueData: "{code:HubConfig|}"

[Icons]
Name: "{autoprograms}\Project Hub"; Filename: "{app}\runtime\pythonw.exe"; Parameters: "{code:LauncherArguments|open}"; WorkingDir: "{app}"; IconFilename: "{app}\brand.ico"
Name: "{autoprograms}\Project Hub CLI"; Filename: "{app}\project-hub.cmd"; WorkingDir: "{app}"
Name: "{autodesktop}\Project Hub"; Filename: "{app}\runtime\pythonw.exe"; Parameters: "{code:LauncherArguments|open}"; WorkingDir: "{app}"; IconFilename: "{app}\brand.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\runtime\pythonw.exe"; Parameters: "{code:LauncherArguments|open}"; WorkingDir: "{app}"; Description: "{cm:LaunchProjectHub}"; Flags: nowait postinstall skipifsilent; Check: UpdateSucceeded

[CustomMessages]
en.LaunchProjectHub=Launch Project Hub
ru.LaunchProjectHub=Запустить Project Hub
en.PrepareFailed=Project Hub could not prepare installation or update. Program files have not been replaced.
ru.PrepareFailed=Не удалось подготовить установку или обновление Project Hub. Файлы программы не заменены.
en.DirectoryCheckFailed=The selected installation folder could not be checked. Program files have not been replaced. Check the details below and choose an accessible, dedicated folder.
ru.DirectoryCheckFailed=Не удалось проверить выбранную папку установки. Файлы программы не заменены. Проверьте подробности ниже и выберите отдельную папку, к которой у вас есть доступ.
en.MaintenanceLaunchFailed=The maintenance tool could not start. Windows error %1: %2
ru.MaintenanceLaunchFailed=Не удалось запустить средство обслуживания. Ошибка Windows %1: %2
en.MaintenanceExitFailed=The maintenance tool returned error code %1.
ru.MaintenanceExitFailed=Средство обслуживания завершилось с кодом ошибки %1.
en.MaintenanceMissing=The temporary maintenance files could not be extracted completely.
ru.MaintenanceMissing=Не удалось полностью извлечь временные файлы обслуживания.
en.TechnicalDetails=Technical details:
ru.TechnicalDetails=Технические подробности:
en.SetupLog=Installer log: %1
ru.SetupLog=Журнал установщика: %1
en.DestinationNotEmptyTitle=The installation folder is not empty
ru.DestinationNotEmptyTitle=Папка установки не пуста
en.DestinationNotEmpty=The folder "%1" contains files that were not identified as an existing Project Hub installation. Installation cannot continue here because those files could be replaced. Choose another folder or cancel installation and move the remaining files yourself. No files have been changed.
ru.DestinationNotEmpty=В папке «%1» есть файлы, которые не распознаны как установленный Project Hub. Продолжить установку здесь невозможно: эти файлы могут быть перезаписаны. Выберите другую папку или отмените установку и перенесите оставшиеся файлы самостоятельно. Файлы не изменены.
en.ChooseAnotherFolder=Choose another folder
ru.ChooseAnotherFolder=Выбрать другую папку
en.CancelInstallation=Cancel installation
ru.CancelInstallation=Отменить установку
en.SelectInstallationFolder=Select a folder for Project Hub
ru.SelectInstallationFolder=Выберите папку для установки Project Hub
en.UpdateFailed=The new Project Hub runtime did not pass verification. Recovery was attempted using the saved program copy. Check the details below before continuing.
ru.UpdateFailed=Новая версия Project Hub не прошла проверку запуска. Выполнена попытка восстановления сохранённой программы. Перед продолжением проверьте подробности ниже.
en.StopFailed=Project Hub is still running or could not be verified. Uninstall was cancelled to preserve accepted work.
ru.StopFailed=Project Hub ещё работает или его состояние не удалось проверить. Удаление отменено, чтобы сохранить принятые операции.
en.DataPreserved=Project Hub program files will be removed. Project data, settings, agent connections and keys will be preserved beside:
ru.DataPreserved=Будут удалены файлы программы Project Hub. Данные проектов, настройки, подключения агентов и ключи сохранятся рядом с файлом:

[Code]
const
  DestinationNotEmptyExitCode = 3;

var
  Prepared, Verified, MaintenanceFailed, MaintenanceExtracted: Boolean;
  MaintenanceExitCode: Integer;
  MaintenanceDetails: String;

function CreateFileForLock(Name: String; Access, Share: LongWord; Security: LongWord;
  Creation, Attributes: LongWord; Template: THandle): THandle;
  external 'CreateFileW@kernel32.dll stdcall';
function CloseLockHandle(Handle: THandle): Boolean;
  external 'CloseHandle@kernel32.dll stdcall';

function HubConfig(Param: String): String;
begin
  Result := ExpandConstant('{param:HUBCONFIG|}');
  if Result = '' then
    RegQueryStringValue(HKCU, 'Software\ProjectHub', 'InstallationConfig', Result);
  if Result = '' then
    Result := ExpandConstant('{localappdata}\ProjectHub\installation.json');
end;

function HubLanguage(Param: String): String;
begin
  if ActiveLanguage = 'ru' then
    Result := 'ru'
  else
    Result := 'en';
end;

function LauncherArguments(Mode: String): String;
var
  ConfigPath: String;
begin
  Result := '-B "' + ExpandConstant('{app}\app\scripts\hub_launcher.py') + '" --' + Mode;
  if Mode = 'configure' then
    Result := Result + ' --language=' + HubLanguage('');
  ConfigPath := HubConfig('');
  if ConfigPath <> '' then
    Result := Result + ' --config="' + ConfigPath + '"';
end;

function MaintenanceAt(Action, Directory: String): Boolean;
var
  Args: String;
  Output: TExecOutput;
  I: Integer;
begin
  Args := '-B "' + ExpandConstant('{tmp}\maintenance\app\scripts\hub_update.py') + '" ' + Action +
    ' --app="' + Directory + '" --config="' + HubConfig('') + '" --language=' + HubLanguage('');
  if Action = 'finish' then
    Args := Args + ' --installer="' + ExpandConstant('{srcexe}') + '"';
  MaintenanceExitCode := -1;
  MaintenanceDetails := '';
  Log('Project Hub maintenance: ' + Action + ' --app="' + Directory + '"');
  try
    Result := ExecAndCaptureOutput(ExpandConstant('{tmp}\maintenance\runtime\python.exe'), Args,
      ExpandConstant('{tmp}\maintenance'), SW_HIDE, ewWaitUntilTerminated, MaintenanceExitCode, Output);
    if not Result then
      MaintenanceDetails := FmtMessage(CustomMessage('MaintenanceLaunchFailed'), [
        IntToStr(MaintenanceExitCode), SysErrorMessage(MaintenanceExitCode)])
    else begin
      for I := 0 to GetArrayLength(Output.StdOut) - 1 do
        Log(Output.StdOut[I]);
      for I := 0 to GetArrayLength(Output.StdErr) - 1 do begin
        Log(Output.StdErr[I]);
        MaintenanceDetails := MaintenanceDetails + Output.StdErr[I] + #13#10;
      end;
      Result := MaintenanceExitCode = 0;
      if not Result then
        MaintenanceDetails := FmtMessage(CustomMessage('MaintenanceExitFailed'), [
          IntToStr(MaintenanceExitCode)]) + #13#10 + MaintenanceDetails;
    end;
  except
    Result := False;
    MaintenanceDetails := GetExceptionMessage;
  end;
  if not Result then Log(MaintenanceDetails);
end;

function MaintenanceFailure(MessageName: String): String;
begin
  Result := CustomMessage(MessageName);
  if MaintenanceDetails <> '' then
    Result := Result + #13#10#13#10 + CustomMessage('TechnicalDetails') + #13#10 +
      Copy(MaintenanceDetails, 1, 2000);
  Result := Result + #13#10#13#10 +
    FmtMessage(CustomMessage('SetupLog'), [ExpandConstant('{log}')]);
end;

function Maintenance(Action: String): Boolean;
begin
  Result := MaintenanceAt(Action, ExpandConstant('{app}'));
end;

function ExtractMaintenance(): Boolean;
begin
  MaintenanceDetails := '';
  Result := False;
  try
    if not MaintenanceExtracted then begin
      ExtractTemporaryFiles('{tmp}\maintenance\*');
      MaintenanceExtracted := True;
    end;
    Result := FileExists(ExpandConstant('{tmp}\maintenance\runtime\python.exe')) and
      FileExists(ExpandConstant('{tmp}\maintenance\app\scripts\hub_update.py'));
    if not Result then MaintenanceDetails := CustomMessage('MaintenanceMissing');
  except
    MaintenanceDetails := GetExceptionMessage;
  end;
  if not Result then Log(MaintenanceDetails);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  Directory, Reason: String;
begin
  Result := True;
  if CurPageID <> wpSelectDir then exit;
  Result := False;
  if not ExtractMaintenance() then begin
    SuppressibleMsgBox(MaintenanceFailure('DirectoryCheckFailed'), mbError, MB_OK, IDOK);
    exit;
  end;
  while not MaintenanceAt('check-destination', WizardDirValue) do begin
    if MaintenanceExitCode <> DestinationNotEmptyExitCode then begin
      SuppressibleMsgBox(MaintenanceFailure('DirectoryCheckFailed'), mbError, MB_OK, IDOK);
      exit;
    end;
    Reason := FmtMessage(CustomMessage('DestinationNotEmpty'), [WizardDirValue]);
    Log(Reason);
    if WizardSilent then exit;
    if SuppressibleTaskDialogMsgBox(CustomMessage('DestinationNotEmptyTitle'), Reason,
      mbError, MB_RETRYCANCEL, [CustomMessage('ChooseAnotherFolder'), CustomMessage('CancelInstallation')],
      0, IDCANCEL) <> IDRETRY then begin
      WizardForm.Close;
      exit;
    end;
    Directory := WizardDirValue;
    if not BrowseForFolder(CustomMessage('SelectInstallationFolder'), Directory, True) then exit;
    WizardForm.DirEdit.Text := Directory;
  end;
  Result := True;
end;

function NeedsRuntimeFile(): Boolean;
var
  Target, Incoming, Prefix: String;
begin
  Target := ExpandConstant(CurrentFilename);
  if Copy(Target, 1, 4) = '\\?\' then Delete(Target, 1, 4);
  Prefix := ExpandConstant('{app}\runtime\');
  if CompareText(Copy(Target, 1, Length(Prefix)), Prefix) <> 0 then
    RaiseException('Unexpected runtime installation path');
  Incoming := ExpandConstant('{tmp}\maintenance\runtime\') + Copy(Target, Length(Prefix) + 1, Length(Target));
  Result := True;
  if FileExists(Target) and FileExists(Incoming) then
    Result := GetSHA256OfFile(Target) <> GetSHA256OfFile(Incoming);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if Prepared then exit;
  if not ExtractMaintenance() then begin
    Result := MaintenanceFailure('PrepareFailed');
    exit;
  end;
  if not Maintenance('prepare') then begin
    if MaintenanceExitCode = DestinationNotEmptyExitCode then
      Result := FmtMessage(CustomMessage('DestinationNotEmpty'), [ExpandConstant('{app}')])
    else
      Result := MaintenanceFailure('PrepareFailed');
    exit;
  end;
  Prepared := True;
  Result := '';
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then begin
    Verified := Maintenance('finish');
    if not Verified then begin
      MaintenanceFailed := True;
      SuppressibleMsgBox(MaintenanceFailure('UpdateFailed'), mbError, MB_OK, IDOK);
    end;
  end;
end;

procedure DeinitializeSetup();
begin
  if Prepared and not Verified then
    Maintenance('rollback');
end;

function UpdateSucceeded(): Boolean;
begin
  Result := Verified;
end;

function GetCustomSetupExitCode(): Integer;
begin
  if MaintenanceFailed then Result := 1 else Result := 0;
end;

function InitializeUninstall(): Boolean;
var
  Code: Integer;
  Args: String;
  LockPath: String;
  Handle: THandle;
begin
  Args := '-B "' + ExpandConstant('{app}\app\scripts\hub_update.py') + '" stop --app="' +
    ExpandConstant('{app}') + '" --config="' + HubConfig('') + '"';
  if FileExists(ExpandConstant('{app}\runtime\python.exe')) and
    FileExists(ExpandConstant('{app}\app\scripts\hub_update.py')) then
    Result := Exec(ExpandConstant('{app}\runtime\python.exe'), Args,
      ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, Code) and (Code = 0)
  else begin
    { A damaged program can still be removed when no supervisor owns it. }
    LockPath := ExtractFilePath(HubConfig('')) + 'supervisor.lock';
    Result := not FileExists(LockPath);
    if not Result then begin
      Handle := CreateFileForLock(LockPath, $C0000000, 0, 0, 3, $80, 0);
      Result := Handle <> THandle(-1);
      if Result then CloseLockHandle(Handle);
    end;
  end;
  if not Result then SuppressibleMsgBox(CustomMessage('StopFailed'), mbError, MB_OK, IDOK)
  else if not UninstallSilent then
    SuppressibleMsgBox(CustomMessage('DataPreserved') + #13#10 + HubConfig(''), mbInformation, MB_OK, IDOK);
end;
