# Install, update and remove Project Hub on Windows

The installer includes a private Python runtime. A system Python installation
is not required. Choose Russian or English during installation; that language
becomes the initial interface language. Later installations preserve your
existing interface choice.

The desktop shortcut starts the local server when needed and opens its web
interface. Its icon uses a blue square wave on a dark gray background. The same
icon appears in the notification area while the server runs. A colored marker
shows running, starting or error status. The menu opens Hub and settings, starts,
restarts or stops the server, and opens update/reinstallation. Menu opening uses
cached status; server commands and health checks run asynchronously.

Use **Settings → General → Project Hub server** to see the current address,
program directory, data folder and launch mode. Hub always shows its server icon
while running. Windows can place it in the notification overflow according to
your Windows settings. **Stop server** and **Exit** stop the server gracefully
and close the icon. Open the desktop or Start menu shortcut to start it again.
Updating or uninstalling the program also closes its tray controller.

To connect external agents or configure analysis through a model API, see
[agents and API analysis](agent-analysis.md).

## Where files are stored

Program files normally live in `%LOCALAPPDATA%\Programs\ProjectHub`.
You can choose another dedicated folder, including a folder directly on a drive.
Setup does not require administrator rights; your Windows account must have
write access to the selected location. Drive and network-share roots, system
and profile directories themselves, and paths containing links or junctions
cannot be used as the program folder. Dedicated subfolders remain available
subject to their Windows access permissions.
Installation settings normally live in
`%LOCALAPPDATA%\ProjectHub\installation.json`. This file records the data folder,
optional backup folder, endpoint port and initial language. The Windows registry value
`HKCU\Software\ProjectHub\InstallationConfig` remembers its location across
reinstallation, including after removing the program.

The selected data folder holds the project catalog, tasks, documentation,
architecture and artifacts. Agent connections and encrypted provider keys
remain outside the program directory beside the installation settings.
Use **Projects → Hub data** to see the active data folder. Use
**Projects → Backups** to download a portable archive of all project data.
An archive does not include source repositories or unrelated agent settings.
The default data folder is `%LOCALAPPDATA%\ProjectHub\data`; backups use the
separate `%LOCALAPPDATA%\ProjectHub\data-backups` folder. Change either in
**Settings → General**. Changing the data folder copies the current data to an
empty destination and verifies a server restart; the previous data stay intact.
Changing the backup folder leaves existing archives at their previous location.
Source work mode uses the same settings as the installed application.

## Update or reinstall

Run a newer installer or rerun the same installer. It reuses the application
directory and external settings. Existing projects, data location, language,
port, agent connections and keys remain configured.

Before replacing program files, the installer verifies the running installed
server and asks it to drain accepted work. It does not forcefully kill it.
If stopping cannot be confirmed, replacement does not begin.

The installer saves a verified copy of the previous program under
`updates` beside the installation configuration. It then replaces the program,
starts the new server and checks its identity, data folder and HTTP agent runtime.
If verification fails, it attempts to restore and start the previous program.
The maintenance receipt and `updates\last-error.txt` explain the outcome.
When a folder check or maintenance command fails, setup shows the specific
error and the installer log path. The installer log also records failures to
start the maintenance tool and remains available when the external maintenance
log cannot be written. A folder-check error occurs before program replacement;
review the reported reason rather than assuming administrator rights are needed.
Keep the program copy until you have verified the updated installation.

If a server launched from source already owns the main runtime, the installer
verifies the new program without starting a second main server. Open the
installed shortcut after stopping the source server, or explicitly switch
launchers as described below. The tray maintenance command uses the recorded
installer; if that file was moved or deleted, run the installer manually.

Imports convert supported older schemas on a prepared copy. Restoring an archive
or importing an old folder applies selected projects to the active data folder;
it does not switch the data location to the import source. Review the add or
replace-all summary before confirming. Connections and keys from this installation
are retained. See [backups](backups.md) for conflicts and recovery.

## Recover an interrupted update

Rerunning the installer first recovers an unfinished replacement from its
verified prior program copy, then prepares a new update. If recovery cannot be
verified, replacement stops. Preserve the receipt and previous program copy.
For explicit recovery, use a compatible Python runtime located outside the
application folder being restored, and run
`app\scripts\hub_update.py rollback --app <absolute-program-folder>
--config <absolute-installation-config>` from a compatible installation.
Recovery checks the recorded application path and previous program hashes
before replacing any program files. It preserves user storage and settings.
If program files or the private runtime are missing, use a compatible extracted
installer maintenance runtime or restore the saved program with support.

A failed first installation has no previous program to restore. Its data is
preserved, and rerunning the installer repairs the program.

If the destination contains files that do not belong to a recognized Hub
installation, setup names the nonempty folder and offers **Choose another
folder** or **Cancel installation**. It does not replace those files. Empty
program directories and Python bytecode caches left by an earlier uninstall
do not block reinstallation. Choosing another program folder preserves the
existing external settings and project data.

## Uninstall

Use Windows Installed apps or the registered Project Hub uninstaller. It first
drains the installed server, then removes program files and shortcuts.
It preserves installation settings, project data, downloaded backups, encrypted
keys and agent registrations. Reinstalling reconnects to the saved settings.

Agent registrations use the server's HTTP MCP address and a private Hub
credential. While the program is removed, those registrations cannot connect.
Reinstall to reconnect, or deliberately update/remove the registration in your
agent. Uninstall does not edit unrelated agent configuration.

## Developer source launch

This section is for working with the source repository. Install its pinned
server, image and desktop requirements into your development Python environment.
Run `python scripts/hub_source.py` from the repository to open Hub. This calls
the same Python launcher, supervisor and tray as the installed application. A
source shortcut can point to this script using the chosen Python interpreter;
no scheduled task, PowerShell controller or Windows service is required.

There are two launch modes. The mode is chosen before starting the server;
changing it requires stopping that runtime and launching the other mode.

**Work mode** is the default: `python scripts/hub_source.py --mode work`.
It reads the same `%LOCALAPPDATA%\ProjectHub\installation.json` as the installed
application, including the selected data folder, port and language. Connections,
provider settings, instructions and project data come from that same storage.
Existing preferences are preserved. A source desktop shortcut should use this
mode; `pythonw.exe` avoids opening a console on Windows. Matching source and
installed program files use the same launcher, supervisor, server and tray;
the source Python environment must also contain the pinned dependencies.

On Windows the source launcher delegates supervisor creation to the current
user's Explorer desktop through its documented automation interface. This keeps
the supervisor, server and tray independent of the terminal or application that
requested the launch. The launcher verifies the same Windows user, Explorer
parent PID and the supervisor's lifetime constraints before accepting startup.
The supervisor receives explicit configuration and runtime mode arguments;
credentials and arbitrary caller environment variables are not copied through
the desktop interface. Restricted callers, an unavailable desktop, or an
unverified independent process produce an error rather than a dependent server.
No service, scheduled task, registry change or elevated process is used. The
owned Python installation must include both `python.exe` and `pythonw.exe`.
The entire source start/stop controller runs in that desktop context before
opening lifecycle locks or writing metadata. This avoids mixing a packaged
caller's private AppData overlay with the ordinary desktop's state. A physically
resolved temporary response file carries only the operation result and URL back
to the caller; it does not contain credentials.

For a custom installation configuration, pass the same absolute `--config` path
to both launchers. `--data-home` sets the initial folder only when creating a new
configuration. Stop the verified owner of the selected work configuration with
`python scripts/hub_source.py --stop`, including `--config` when using a custom
configuration. The owner may have started from source or the installed program.

Normal source and installed launches share one main-runtime lease for the
current desktop user. Another shortcut opens that existing server. Use
`--switch` to request a verified graceful stop and explicitly switch to the
other launcher. An older server started without this common launcher must be
stopped gracefully before using the new entry point.

**Development and test mode** starts with
`python scripts/hub_source.py --mode development`. It creates a separate profile
under `%LOCALAPPDATA%\ProjectHub\development\sources\<checkout-id>`: its own
`installation.json` and a new `data` folder. This profile is reused for that
checkout. No working projects are copied automatically. The existing
`--development` option is an alias for this mode. To stop it, run
`python scripts/hub_source.py --mode development --stop`.

Use `--config <absolute-test-config> --data-home <absolute-test-data-folder>` to
select another isolated profile or an inactive copy. A development runtime may
run beside the work runtime and cannot switch or stop the work runtime. The
launcher refuses a working data folder even when its work server is stopped.
Two servers cannot open the same data folder, even on different ports. These
guards protect launcher admission; they do not sandbox arbitrary source code.
Develop and test Hub itself using disposable data. For a restored copy, inspect
its settings and replace provider credentials before issuing test requests.

A free port is chosen on initial launch when the requested port is occupied, and
the runtime is marked as development.
An established endpoint is preserved; an occupied saved port requires resolving
the conflict before reopening. The common desktop code is portable; this release
packages and verifies Windows. Other desktop backends require their own validation.
