"""Focused offline Windows installer builder checks."""
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import unittest
import uuid
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'scripts'))
SPEC = importlib.util.spec_from_file_location("windows_installer", ROOT / "scripts" / "build_windows_installer.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class WindowsInstallerTests(unittest.TestCase):
    def setUp(self):
        self.root = ROOT / '.tmp' / 'installer-tests' / uuid.uuid4().hex
        self.root.mkdir(parents=True)
        self.payload = self.root / "payload"
        self.payload.mkdir()

    def tearDown(self):
        assert self.root.resolve().is_relative_to((ROOT/'.tmp'/'installer-tests').resolve())
        shutil.rmtree(self.root)

    def test_extract_archive_rejects_escape_and_symlink_members(self):
        archive = self.root / "bad.zip"
        with zipfile.ZipFile(archive, "w") as output:
            output.writestr("bundle/../escape.txt", "bad")
        with self.assertRaises(ValueError):
            MODULE.extract_archive(archive, self.payload)
        archive = self.root / "link.zip"
        with zipfile.ZipFile(archive, "w") as output:
            info = zipfile.ZipInfo("bundle/link")
            info.external_attr = (0o120777 << 16) | 0xA0000000
            output.writestr(info, "target")
        with self.assertRaises(ValueError):
            MODULE.extract_archive(archive, self.payload)

    def test_build_uses_offline_binary_dependency_install_and_writes_manifest(self):
        source = self.root / "source"
        (source / "scripts").mkdir(parents=True)
        (source / "tools").mkdir()
        for name in ("requirements-server.txt", "requirements-images.txt", "requirements-desktop.txt"):
            (source / name).write_text("fixture==1\n", encoding="utf-8")
        wheelhouse = self.root / "wheelhouse"
        wheelhouse.mkdir()
        installer = self.root / "installer"
        installer.mkdir()
        for name in ("brand.ico", "wizard.bmp", "wizard-small.bmp"):
            (installer / name).write_bytes(b"asset")
        (installer / "project-hub.iss").write_text("[Setup]\n", encoding="utf-8")
        embed = self.root / "python.zip"
        with zipfile.ZipFile(embed, "w") as archive:
            archive.writestr("python.exe", b"python")
            archive.writestr("python313.zip", b"stdlib")
        compiler = self.root / "ISCC.exe"
        compiler.write_bytes(b"compiler")
        output = self.root / "dist"
        output.mkdir()

        def fake_distribution(path, root, *, standalone=False):
            self.assertTrue(standalone)
            with zipfile.ZipFile(path, "w") as archive:
                archive.writestr("project-hub-0.3.0/app.py", "print('ok')")
            return {"sourceTreeSha256": "source-tree"}

        commands = []
        def fake_run(command, **_kwargs):
            commands.append(command)
            if command[0] == str(compiler):
                (output / "ProjectHub-0.3.2.exe").write_bytes(b"exe")

        import build_project_hub_distribution as distribution
        scratch = self.root / "scratch"
        scratch.mkdir()
        class FixedTemporaryDirectory:
            def __init__(self, *args, **kwargs):
                pass
            def __enter__(self):
                self.name = str(scratch)
                return self.name
            def __exit__(self, *_args):
                return False
        with patch.object(distribution, "build", side_effect=fake_distribution), \
             patch.object(MODULE, "_run", side_effect=fake_run), \
             patch.object(MODULE.tempfile, "TemporaryDirectory", FixedTemporaryDirectory):
            result = MODULE.build(compiler=compiler, python_embed=embed, output=output,
                                  source_root=source, wheelhouse=wheelhouse,
                                  installer_source=installer, python_embed_sha256=MODULE.sha256(embed))
        pip_commands = [command for command in commands if "pip" in command]
        self.assertEqual(len(pip_commands), 3)
        for command in pip_commands:
            self.assertIn("--no-index", command)
            self.assertIn("--only-binary", command)
            self.assertIn(str(wheelhouse), command)
            self.assertEqual(command[0],sys.executable)
            self.assertIn('--no-compile',command)
        compiler_command=next(command for command in commands if command[0]==str(compiler))
        self.assertIn('/DOutputDir='+str(output.resolve()),compiler_command)
        self.assertTrue((output / "ProjectHub-0.3.2.manifest.json").is_file())
        self.assertEqual(result["sha256"], MODULE.sha256(output / "ProjectHub-0.3.2.exe"))
        self.assertIn("../app/scripts", MODULE.PTH)
        installed_manifest = json.loads((scratch / 'payload/distribution.json').read_text())
        self.assertEqual(1, installed_manifest['schemaVersion'])
        self.assertEqual(MODULE.sha256(scratch / 'payload/runtime/python.exe'), installed_manifest['files']['runtime/python.exe'])

    def test_inno_uses_temporary_updater_and_preserves_external_configuration(self):
        source = (ROOT / 'installer/project-hub.iss').read_text(encoding='utf-8')
        self.assertIn('UsePreviousAppDir=yes', source)
        self.assertIn('CloseApplications=no', source)
        self.assertIn('function PrepareToInstall', source)
        self.assertIn("ExtractTemporaryFiles('{tmp}\\maintenance\\*')", source)
        self.assertIn("Maintenance('prepare')", source)
        self.assertIn("Maintenance('finish')", source)
        self.assertIn("Maintenance('rollback')", source)
        self.assertIn('function InitializeUninstall', source)
        pointer = next(line for line in source.splitlines() if line.startswith('Root: HKCU;'))
        self.assertIn('InstallationConfig', pointer)
        self.assertNotIn('uninsdelete', pointer)
        self.assertNotIn('[UninstallDelete]', source)

    def test_installer_retries_another_folder_only_for_a_destination_conflict(self):
        source = (ROOT / 'installer/project-hub.iss').read_text(encoding='utf-8')
        directory = source.split('function NextButtonClick', 1)[1].split('function NeedsRuntimeFile', 1)[0]
        self.assertIn('DisableDirPage=no', source)
        self.assertIn('CurPageID <> wpSelectDir', directory)
        self.assertIn("MaintenanceAt('check-destination', WizardDirValue)", directory)
        self.assertNotIn("ExpandConstant('{app}')", directory)
        self.assertIn('MaintenanceExitCode <> DestinationNotEmptyExitCode', directory)
        self.assertIn("CustomMessage('DestinationNotEmpty')", directory)
        self.assertIn('if WizardSilent then exit', directory)
        self.assertIn('MB_RETRYCANCEL', directory)
        self.assertIn("CustomMessage('ChooseAnotherFolder')", directory)
        self.assertIn("CustomMessage('CancelInstallation')", directory)
        self.assertIn('BrowseForFolder', directory)
        self.assertIn('WizardForm.DirEdit.Text := Directory', directory)
        self.assertNotIn('IDIGNORE', directory)
        self.assertNotIn('MB_ABORTRETRYIGNORE', directory)

    def test_installer_and_installed_shortcuts_do_not_write_bytecode(self):
        source = (ROOT / 'installer/project-hub.iss').read_text(encoding='utf-8')
        launcher = source.split('function LauncherArguments', 1)[1].split('function Maintenance', 1)[0]
        maintenance = source.split('function MaintenanceAt', 1)[1].split('function Maintenance(', 1)[0]
        uninstall = source.split('function InitializeUninstall', 1)[1]
        for section in (launcher, maintenance, uninstall):
            self.assertIn("'-B \"'", section)

    def test_maintenance_failures_show_captured_reason_and_installer_log_without_elevation(self):
        source = (ROOT / 'installer/project-hub.iss').read_text(encoding='utf-8')
        self.assertIn('PrivilegesRequired=lowest', source)
        self.assertIn('SetupLogging=yes', source)
        maintenance = source.split('function MaintenanceAt', 1)[1].split('function Maintenance(', 1)[0]
        self.assertIn('ExecAndCaptureOutput(', maintenance)
        self.assertIn('Log(Output.StdOut[I])', maintenance)
        self.assertIn('Log(Output.StdErr[I])', maintenance)
        self.assertIn('SysErrorMessage(MaintenanceExitCode)', maintenance)
        self.assertIn('MaintenanceDetails := GetExceptionMessage', maintenance)
        self.assertIn("ExpandConstant('{log}')", maintenance)
        self.assertIn("MaintenanceFailure('DirectoryCheckFailed')", source)
        self.assertIn("MaintenanceFailure('PrepareFailed')", source)
        self.assertIn("MaintenanceFailure('UpdateFailed')", source)
        for language in ('ru', 'en'):
            for message in ('DirectoryCheckFailed', 'MaintenanceLaunchFailed', 'MaintenanceExitFailed',
                            'MaintenanceMissing', 'TechnicalDetails', 'SetupLog'):
                self.assertIn(language + '.' + message + '=', source)


if __name__ == "__main__":
    unittest.main()
