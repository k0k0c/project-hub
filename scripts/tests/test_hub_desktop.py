"""Desktop status shares the portable lifecycle and never hides a live server."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import hub_desktop as desktop

class DesktopTest(unittest.TestCase):
    def setUp(self):
        temporary=tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.base=Path(temporary.name); self.app=self.base/'program/app'; self.app.mkdir(parents=True)
        self.config=self.base/'settings/installation.json'; self.config.parent.mkdir()
        self.config.write_text(json.dumps(dict(schemaVersion=1,dataHome=str(self.base/'data'),port=8769,language='en')))

    def test_hide_preference_is_removed_without_touching_legacy_settings(self):
        old=self.config.with_name('desktop-preferences.json'); old.write_text('{"showTray":false}')
        before=old.read_bytes()
        with self.assertRaises(desktop.DesktopError) as error:
            desktop.update_runtime(object(), {'showTray':False,'expected':'old'})
        self.assertEqual(error.exception.status,410); self.assertEqual(old.read_bytes(),before)
        with patch.object(desktop,'tray_supported',return_value=True), patch.object(desktop.subprocess,'Popen') as start:
            self.assertTrue(desktop.start_tray(self.config,application_home=self.app))
        command=start.call_args.args[0]
        self.assertEqual(Path(command[2]),self.app/'scripts/hub_tray.py')
        self.assertEqual(start.call_args.kwargs['cwd'], str(self.config.parent))
        self.assertNotIn('powershell',' '.join(command).lower())
        self.assertNotIn('schtasks',' '.join(command).lower())

    def test_runtime_uses_actual_port_and_only_recent_owned_heartbeat(self):
        app=Path(desktop.__file__).resolve().parents[1]; control=self.config.parent/'control/server'
        server=type('Server',(),dict(server_port=27706,registry=type('Registry',(),dict(home=self.base/'data'))()))()
        heartbeat=self.config.with_name('desktop-tray-state.json')
        with patch('hub_lifecycle.control_directory',return_value=control), patch.dict(os.environ,PROJECT_HUB_INSTALLATION_CONFIG=str(self.config),PROJECT_HUB_RUNTIME_MODE='source'),patch.object(desktop,'tray_supported',return_value=True):
            heartbeat.write_text(json.dumps(dict(applicationHome=str(app),at=time.time(),visible=True)))
            result=desktop.runtime_status(server)
            self.assertEqual(result['mode'],'source'); self.assertEqual(result['port'],27706)
            self.assertEqual(result['url'],'http://127.0.0.1:27706'); self.assertTrue(result['tray']['visible'])
            self.assertTrue(result['tray']['required']); self.assertNotIn('enabled',result['tray'])
            heartbeat.write_text(json.dumps(dict(applicationHome=str(self.app),at=time.time(),visible=True)))
            self.assertFalse(desktop.runtime_status(server)['tray']['visible'])
            heartbeat.write_text(json.dumps(dict(applicationHome=str(app),at=time.time()-20,visible=True)))
            self.assertFalse(desktop.runtime_status(server)['tray']['visible'])

    def test_repeated_launch_with_recent_owned_icon_does_not_spawn_another(self):
        self.config.with_name('desktop-tray-state.json').write_text(json.dumps(dict(applicationHome=str(self.app.resolve()),at=time.time(),visible=True)))
        with patch.object(desktop,'tray_supported',return_value=False) as prerequisites,patch.object(desktop.subprocess,'Popen') as start:
            self.assertTrue(desktop.start_tray(self.config,application_home=self.app))
        prerequisites.assert_not_called()
        start.assert_not_called()

    def test_foreign_owner_tray_uses_owned_interpreter_and_waits_for_visibility(self):
        executable=self.base/'owner/python.exe'; executable.parent.mkdir(); executable.touch()
        windowed=executable.with_name('pythonw.exe'); windowed.touch()
        with patch.object(desktop,'tray_supported',return_value=False) as prerequisites, \
             patch.object(desktop.subprocess,'Popen') as start, patch.object(desktop,'wait_for_tray',return_value=True) as visible:
            self.assertTrue(desktop.start_tray(self.config,application_home=self.app,
                                              wait=True,python_executable=str(executable)))
        prerequisites.assert_not_called()
        self.assertEqual(start.call_args.args[0][0],str(windowed))
        self.assertEqual(start.call_args.args[0][2],str(self.app/'scripts/hub_tray.py'))
        self.assertEqual(start.call_args.kwargs['cwd'], str(self.config.parent))
        visible.assert_called_once_with(self.config,application_home=self.app)

    def test_owned_interpreter_dependency_error_is_propagated(self):
        executable=self.base/'owner/python.exe'; executable.parent.mkdir(); executable.touch()
        def child_error(*args,**kwargs):
            self.config.with_name('desktop-tray-error.json').write_text(json.dumps({'message':'Owner runtime cannot import pystray'}))
        with patch.object(desktop,'tray_supported',return_value=False) as prerequisites, \
             patch.object(desktop.subprocess,'Popen',side_effect=child_error) as start:
            with self.assertRaisesRegex(desktop.DesktopError,'Owner runtime cannot import pystray'):
                desktop.start_tray(self.config,application_home=self.app,wait=True,python_executable=str(executable))
        prerequisites.assert_not_called(); start.assert_called_once()

    def test_new_tray_requires_caller_desktop_dependencies(self):
        with patch.object(desktop,'tray_supported',return_value=False) as prerequisites, \
             patch.object(desktop.subprocess,'Popen') as start, patch.object(desktop,'wait_for_tray') as visible:
            self.assertFalse(desktop.start_tray(self.config,application_home=self.app,wait=True))
        prerequisites.assert_called_once_with(self.app)
        start.assert_not_called(); visible.assert_not_called()

    def test_exit_marker_is_not_removed_while_previous_controller_owns_lease(self):
        from hub_lifecycle import file_lock
        marker = self.config.with_name('desktop-tray-exit.json')
        marker.write_text('{}')
        with file_lock(self.config.with_name('desktop-tray.lock')), \
             patch.object(desktop,'tray_supported',return_value=True), patch.object(desktop.subprocess,'Popen') as start:
            self.assertFalse(desktop.start_tray(self.config,application_home=self.app))
        start.assert_not_called(); self.assertTrue(marker.exists())
        with patch.object(desktop,'tray_supported',return_value=True), patch.object(desktop.subprocess,'Popen') as start:
            self.assertTrue(desktop.start_tray(self.config,application_home=self.app))
        self.assertFalse(marker.exists()); start.assert_called_once()

    def test_external_stop_waits_for_controller_release_before_switch(self):
        from hub_lifecycle import file_lock
        with file_lock(self.config.with_name('desktop-tray.lock')):
            with self.assertRaisesRegex(desktop.DesktopError,'still closing'):
                desktop.close_tray(self.config,application_home=self.app,timeout=0)
        self.assertTrue(self.config.with_name('desktop-tray-exit.json').exists())
        desktop.close_tray(self.config,application_home=self.app,timeout=0)

    def test_first_visibility_is_acknowledged_and_backend_error_is_propagated(self):
        with patch.object(desktop,'tray_state',return_value={'visible':True}):
            self.assertTrue(desktop.wait_for_tray(self.config,application_home=self.app,timeout=0))
        self.config.with_name('desktop-tray-error.json').write_text('{"message":"Unsupported tray menu"}')
        with patch.object(desktop,'tray_state',return_value=None):
            with self.assertRaisesRegex(desktop.DesktopError,'Unsupported tray menu'):
                desktop.wait_for_tray(self.config,application_home=self.app,timeout=0)
