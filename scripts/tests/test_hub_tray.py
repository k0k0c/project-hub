"""Tray commands are asynchronous and stop cannot leave an independent controller."""
import json
import importlib.util
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import hub_tray as tray


class TrayTest(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root=Path(temp.name); self.config=self.root/'settings/config.json'; self.config.parent.mkdir()
        self.app=self.root/'app'; self.app.mkdir()
        self.config.write_text(json.dumps(dict(schemaVersion=1,dataHome=str(self.root/'data'),port=8769,language='en')))
        self.controller=tray.TrayController(self.config,self.app); self.controller.icon=Mock()
        self.addCleanup(lambda:self.controller.executor.shutdown(wait=True,cancel_futures=True))

    def test_menu_callback_returns_while_stop_is_draining_then_closes_icon(self):
        entered=threading.Event(); released=threading.Event()
        def drain(*args,**kwargs):
            entered.set(); released.wait(3)
        with patch.object(tray,'stop_hub',side_effect=drain) as stop:
            before=time.monotonic(); self.assertTrue(self.controller.submit('stop'))
            self.assertLess(time.monotonic()-before,.2); self.assertTrue(entered.wait(1))
            self.controller.icon.stop.assert_not_called(); self.assertFalse(self.controller.submit('restart'))
            released.set(); self.controller.executor.shutdown(wait=True)
        stop.assert_called_once_with(self.config,application_home=self.app,close_desktop=False)
        self.controller.icon.stop.assert_called_once(); self.assertTrue(self.controller.closed.is_set())

    def test_restart_keeps_icon_and_uses_common_launcher(self):
        with patch.object(tray,'stop_hub') as stop,patch.object(tray,'open_hub') as start:
            self.controller._command('restart')
        self.assertFalse(stop.call_args.kwargs['close_desktop'])
        self.assertEqual(start.call_args.args,(self.config,))
        self.controller.icon.stop.assert_not_called(); self.assertFalse(self.controller.closed.is_set())

    def test_health_failure_with_live_supervisor_is_error_without_closing(self):
        from hub_lifecycle import file_lock
        with file_lock(self.config.with_name('supervisor.lock')),patch.object(tray,'health',return_value=None):
            self.assertTrue(self.controller.poll()); self.assertEqual(self.controller.status,'error')
        with patch.object(tray,'health',return_value=None):
            self.assertFalse(self.controller.poll())

    def test_status_overlay_preserves_shared_wave_and_changes_color(self):
        if importlib.util.find_spec('PIL') is None:
            self.skipTest('Pillow is verified with the packaged desktop runtime; the isolated runner uses stdlib only')
        app=Path(__file__).resolve().parents[2]
        running=tray.status_image(app,'running'); error=tray.status_image(app,'error')
        self.assertEqual(running.getpixel((10,10)),(30,30,30,255))
        self.assertEqual(running.crop((0,0,44,44)).tobytes(),error.crop((0,0,44,44)).tobytes())
        self.assertNotEqual(running.getpixel((54,54)),error.getpixel((54,54)))
