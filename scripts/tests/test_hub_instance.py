"""Main runtime admission is independent of TCP ports and data-home leases."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import hub_instance as instance
import hub_launcher as launcher
from hub_lifecycle import home_lease, file_lock


class InstanceTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        environment = patch.dict(os.environ, PROJECT_HUB_INSTANCE_HOME=str(self.root / 'main'),
                                  PROJECT_HUB_RUNTIME_MODE='source', LOCALAPPDATA=str(self.root / 'local'),
                                  XDG_DATA_HOME=str(self.root / 'local'))
        environment.start(); self.addCleanup(environment.stop)

    def desktop_application(self):
        app = self.root / 'program'
        (app / 'scripts').mkdir(parents=True)
        (app / 'scripts/hub_desktop.py').write_text('')
        return app

    def test_one_main_lease_across_independent_configs_and_ports(self):
        with instance.main_lease():
            with self.assertRaises(TimeoutError):
                with instance.main_lease():
                    pass
        with instance.main_lease():
            pass

    def test_stale_record_is_not_a_live_owner_and_health_does_not_override_busy_lease(self):
        home=self.root/'data'; app=self.root/'app'; config=self.root/'config.json'
        with instance.main_lease():
            instance.publish(config,app,home,19281)
            with patch.object(launcher,'health',return_value=dict(service='project-hub',dataHome=str(home),codeRoot=str(app))):
                self.assertEqual(instance.active()['config'],str(config))
            with patch.object(launcher,'health',return_value=None):
                with self.assertRaisesRegex(launcher.LauncherError,'starting or stopping'):
                    instance.active()
        with patch.object(launcher,'health',side_effect=AssertionError('stale metadata must not be consulted')):
            self.assertIsNone(instance.active())

    def test_development_allows_parallel_main_lease_but_not_shared_storage(self):
        home=self.root/'data'
        with instance.main_lease(), home_lease(home):
            with patch.dict(os.environ, PROJECT_HUB_RUNTIME_MODE='development'):
                with instance.main_lease():
                    with self.assertRaises(TimeoutError):
                        with home_lease(home):
                            pass

    def test_development_rejects_installed_home_even_when_primary_is_stopped(self):
        base=launcher.default_base(); base.mkdir(parents=True)
        home=self.root/'primary'
        (base/'installation.json').write_text(json.dumps(dict(dataHome=str(home))))
        with self.assertRaisesRegex(launcher.LauncherError,'installed Hub data folder'):
            instance.check_development_home(home,self.root/'dev/config.json',self.root/'app')
        instance.check_development_home(self.root/'copy',self.root/'dev/config.json',self.root/'app')

    def test_inactive_custom_primary_configuration_is_protected_without_platform_registry(self):
        home=self.root/'custom-production'; config=self.root/'custom-config/settings.json'; app=self.root/'app'
        launcher.configure(config,application_home=app,data_home=home)
        instance.register_primary(config,app)
        with self.assertRaisesRegex(launcher.LauncherError,'primary home'):
            instance.check_development_home(home,self.root/'dev/config.json',app)
        with self.assertRaisesRegex(launcher.LauncherError,'own configuration'):
            instance.check_development_home(self.root/'copy',config,app)

    def test_other_launcher_reopens_verified_main_without_starting_or_stopping(self):
        config=self.root/'selected/config.json'; app=self.desktop_application()
        current=dict(config=str(self.root/'other/config.json'),applicationHome=str(self.root/'other/app'),port=19832,
                     dataHome=str(self.root/'other/data'),pythonExecutable=str(self.root/'owner/python.exe'))
        launcher.configure(config,application_home=app)
        with patch.object(instance,'active',return_value=current), patch('hub_desktop.start_tray',return_value=True) as tray, \
             patch('hub_desktop.tray_supported',return_value=False) as prerequisites, \
             patch.object(launcher.subprocess,'Popen') as start, patch.object(launcher,'stop_hub') as stop, \
             patch.object(launcher.webbrowser,'open') as browser:
            self.assertEqual(launcher.open_hub(config,application_home=app),'http://127.0.0.1:19832')
        start.assert_not_called(); stop.assert_not_called()
        prerequisites.assert_not_called()
        tray.assert_called_once_with(current['config'],application_home=Path(current['applicationHome']),
                                     wait=True,python_executable=current['pythonExecutable'])
        browser.assert_called_once_with('http://127.0.0.1:19832')

    def test_stop_uses_verified_owner_for_shared_work_configuration(self):
        config = self.root / 'selected/config.json'; app = self.root / 'source'
        installed = self.root / 'installed'
        current = dict(config=str(config), applicationHome=str(installed))
        with patch.object(instance, 'active', return_value=current), patch.object(launcher, 'stop_hub') as stop:
            launcher.stop_runtime(config, application_home=app)
        stop.assert_called_once_with(config, application_home=installed, timeout=60)

    def test_stop_refuses_another_main_configuration(self):
        config = self.root / 'selected/config.json'
        current = dict(config=str(self.root / 'other/config.json'), applicationHome=str(self.root / 'installed'))
        with patch.object(instance, 'active', return_value=current), patch.object(launcher, 'stop_hub') as stop:
            with self.assertRaisesRegex(launcher.LauncherError, 'Another main Hub configuration'):
                launcher.stop_runtime(config, application_home=self.root / 'source')
        stop.assert_not_called()

    def test_same_launcher_reuses_owner_python_without_caller_desktop_dependencies(self):
        config=self.root/'selected/config.json'; app=self.desktop_application()
        current=dict(config=str(config),applicationHome=str(app),port=19832,
                     dataHome=str(self.root/'data'),pythonExecutable=str(self.root/'owner/python.exe'))
        launcher.configure(config,application_home=app)
        for switch in (False,True):
            with self.subTest(switch=switch), patch.object(instance,'active',return_value=current), \
                 patch('hub_desktop.start_tray',return_value=True) as tray, \
                 patch('hub_desktop.tray_supported',return_value=False) as prerequisites, \
                 patch.object(launcher.subprocess,'Popen') as start, patch.object(launcher,'stop_hub') as stop, \
                 patch.object(launcher,'health',side_effect=AssertionError('The verified owner already supplied its endpoint')):
                self.assertEqual(launcher.open_hub(config,application_home=app,browser=False,switch=switch,source=True),
                                 'http://127.0.0.1:19832')
            prerequisites.assert_not_called(); start.assert_not_called(); stop.assert_not_called()
            tray.assert_called_once_with(current['config'],application_home=app,
                                         wait=True,python_executable=current['pythonExecutable'])

    def test_unsupported_new_runtime_is_refused_before_process_start(self):
        config=self.root/'selected/config.json'; app=self.desktop_application()
        launcher.configure(config,application_home=app)
        with patch.object(instance,'active',return_value=None) as owner, \
             patch('hub_desktop.tray_supported',return_value=False) as prerequisites, \
             patch.object(launcher.subprocess,'Popen') as start, patch.object(launcher,'stop_hub') as stop:
            with self.assertRaisesRegex(launcher.LauncherError,'Tray dependencies are unavailable'):
                launcher.open_hub(config,application_home=app)
        owner.assert_called_once(); prerequisites.assert_called_once_with(app)
        start.assert_not_called(); stop.assert_not_called()

    def test_unsupported_switch_target_leaves_verified_owner_running(self):
        config=self.root/'selected/config.json'; app=self.desktop_application()
        current=dict(config=str(self.root/'other/config.json'),applicationHome=str(self.root/'other/app'),
                     port=19832,dataHome=str(self.root/'other/data'))
        launcher.configure(config,application_home=app)
        with patch.object(instance,'active',return_value=current) as owner, \
             patch('hub_desktop.tray_supported',return_value=False) as prerequisites, \
             patch.object(launcher.subprocess,'Popen') as start, patch.object(launcher,'stop_hub') as stop:
            with self.assertRaisesRegex(launcher.LauncherError,'Tray dependencies are unavailable'):
                launcher.open_hub(config,application_home=app,switch=True)
        owner.assert_called_once(); prerequisites.assert_called_once_with(app)
        stop.assert_not_called(); start.assert_not_called()

    def test_switch_waits_for_verified_drain_before_new_process(self):
        config=self.root/'selected/config.json'; app=self.desktop_application()
        current=dict(config=str(self.root/'other/config.json'),applicationHome=str(self.root/'other/app'),port=19832,dataHome=str(self.root/'other/data'))
        launcher.configure(config,application_home=app)
        order=[]
        def owner():
            order.append('owner'); return current
        def prerequisites(application_home):
            order.append('preflight'); return True
        def drain(*args,**kwargs):
            order.append('drain'); raise launcher.LauncherError('still draining')
        with patch.object(instance,'active',side_effect=owner), patch('hub_desktop.tray_supported',side_effect=prerequisites), \
             patch.object(launcher,'stop_hub',side_effect=drain) as stop, \
             patch.object(launcher.subprocess,'Popen') as start:
            with self.assertRaisesRegex(launcher.LauncherError,'still draining'):
                launcher.open_hub(config,application_home=app,switch=True)
        self.assertEqual(order,['owner','preflight','drain'])
        stop.assert_called_once_with(current['config'],application_home=Path(current['applicationHome']))
        start.assert_not_called()
