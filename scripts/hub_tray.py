"""Portable tray view. All server I/O and commands run outside the GUI loop."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import os
from pathlib import Path
import subprocess
import threading
import time
import webbrowser

from hub_launcher import (external_path, read_json, validate_config, remembered_port,
                          state_path, health, matches_home, matches_program, open_hub, stop_hub)
from hub_lifecycle import atomic_json, file_lock


COLORS = {'running':'#44be76', 'starting':'#f5b83d', 'stopped':'#9c9c9c', 'error':'#ef5757'}


def status_image(application_home, status):
    from PIL import Image, ImageDraw
    app = Path(application_home)
    brand = app / 'installer/brand.ico'
    if not brand.is_file():
        brand = app.parent / 'brand.ico'
    with Image.open(brand) as source:
        image = source.convert('RGBA').resize((64, 64))
    draw = ImageDraw.Draw(image)
    draw.ellipse((45, 45, 63, 63), fill=COLORS.get(status, COLORS['error']), outline='#1e1e1e', width=3)
    return image


class TrayController:
    def __init__(self, config_path, application_home):
        self.config_path = external_path(config_path, application_home=application_home)
        self.application_home = Path(application_home).resolve()
        self.config = validate_config(read_json(self.config_path), application_home=self.application_home)
        self.status = 'starting'
        self.port = self.config['port']
        self.busy = False
        self.error = ''
        self.closed = threading.Event()
        self.guard = threading.Lock()
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='hub-tray-command')
        self.icon = None

    def text(self, ru, en):
        return ru if self.config['language'] == 'ru' else en

    @property
    def url(self):
        return f'http://127.0.0.1:{self.port}'

    def label(self, item=None):
        labels = {'running':self.text('Сервер работает', 'Server running'),
                  'starting':self.text('Сервер запускается', 'Server starting'),
                  'stopped':self.text('Сервер остановлен', 'Server stopped'),
                  'error':self.text('Ошибка сервера', 'Server error')}
        test = self.text(' · тестовый', ' · development') if os.environ.get('PROJECT_HUB_RUNTIME_MODE') == 'development' else ''
        return f"Project Hub{test} · {labels[self.status]} · {self.port}"

    def submit(self, operation):
        """Menu callback: enqueue immediately, never perform a request or wait."""
        with self.guard:
            if self.busy or self.closed.is_set():
                return False
            self.busy = True
        self.executor.submit(self._command, operation)
        return True

    def _command(self, operation):
        try:
            self.error = ''
            if operation == 'open':
                webbrowser.open(self.url)
            elif operation == 'settings':
                webbrowser.open(self.url + '/#settings')
            elif operation == 'maintenance':
                self.maintenance()
            elif operation in ('stop', 'exit', 'restart'):
                self.status = 'stopped'
                stop_hub(self.config_path, application_home=self.application_home,
                         close_desktop=False)  # This controller closes itself after drain.
                if operation != 'restart':
                    self.closed.set()
                    self.icon.stop()
                else:
                    self.status = 'starting'
                    self._start()
            elif operation == 'start':
                self.status = 'starting'
                self._start()
        except (ValueError, OSError, subprocess.SubprocessError) as error:
            self.status = 'error'
            self.error = str(error)
            if self.icon and self.icon.HAS_NOTIFICATION:
                self.icon.notify(str(error), 'Project Hub')
        finally:
            self.busy = False
            if self.icon and not self.closed.is_set():
                self.icon.update_menu()

    def _start(self):
        mode = os.environ.get('PROJECT_HUB_RUNTIME_MODE')
        open_hub(self.config_path, application_home=self.application_home, browser=False,
                 source=mode == 'source', development=mode == 'development')

    def maintenance(self):
        from hub_launcher import default_base
        candidates = [self.config_path.with_name('maintenance-installer.json'),
                      default_base() / 'maintenance-installer.json']
        for candidate in candidates:
            try:
                row = read_json(candidate)
                path = external_path(row['path'], application_home=self.application_home)
                if path.is_file():
                    with path.open('rb') as source:
                        digest = hashlib.file_digest(source, 'sha256').hexdigest()
                    if digest != row.get('sha256'):
                        raise ValueError('The saved installer changed. Run a verified installer manually.')
                    subprocess.Popen([str(path)], stdin=subprocess.DEVNULL,
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                     creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0)
                    return
            except (FileNotFoundError, KeyError, TypeError):
                continue
        webbrowser.open(self.url + '/#settings')
        if self.icon.HAS_NOTIFICATION:
            self.icon.notify(self.text('Запустите установщик Project Hub для обновления или переустановки. Данные сохранятся.',
                                       'Run the Project Hub installer to update or reinstall. Your data is preserved.'), 'Project Hub')

    def poll(self):
        self.config = validate_config(read_json(self.config_path), application_home=self.application_home)
        home = Path(self.config['dataHome'])
        self.port = remembered_port(state_path(self.config_path, self.application_home), home) or self.config['port']
        body = health(self.port)
        if matches_home(body, home) and matches_program(body, self.application_home):
            if not self.busy:
                self.status = 'running'
            return True
        if not self.busy:
            self.status = 'error'
        # A lease can stay busy while accepted requests drain or restart. Its
        # release confirms server exit; health failure alone does not.
        try:
            with file_lock(self.config_path.with_name('supervisor.lock'), create=False):
                return False
        except TimeoutError:
            return True
        except FileNotFoundError:
            return False

    def monitor(self):
        try:
            while not self.closed.wait(.75):
                if self.config_path.with_name('desktop-tray-exit.json').is_file():
                    break
                live = self.poll()
                if not live and not self.busy:
                    from runtime_diagnostics import record
                    record('tray.server_unavailable',port=self.port,expected=self.config_path.with_name('desktop-tray-exit.json').is_file())
                    break
                self.icon.title = self.label()
                self.icon.icon = status_image(self.application_home, self.status)
                self.icon.update_menu()
                atomic_json(self.config_path.with_name('desktop-tray-state.json'),
                    dict(applicationHome=str(self.application_home), at=time.time(), visible=True,
                         status=self.status, port=self.port, dataHome=self.config['dataHome']))
        except Exception as error:
            from runtime_diagnostics import exception
            exception('tray.monitor_failed',error,port=self.port)
            self.status = 'error'
        finally:
            self.closed.set()
            self.icon.stop()

    def run(self):
        from hub_desktop import dependencies
        dependencies(self.application_home)
        import pystray
        item = pystray.MenuItem
        def action(name):
            return lambda icon, selected: self.submit(name)
        ready = lambda selected: not self.busy
        menu = pystray.Menu(
            item(self.label, None, enabled=False),
            item(self.text('Открыть Hub', 'Open Hub'), action('open'), default=True, enabled=ready),
            item(self.text('Настройки и сведения о сервере', 'Settings and server details'), action('settings'), enabled=ready),
            pystray.Menu.SEPARATOR,
            item(self.text('Запустить сервер', 'Start server'), action('start'), enabled=lambda selected: not self.busy and self.status != 'running'),
            item(self.text('Перезапустить сервер', 'Restart server'), action('restart'), enabled=ready),
            item(self.text('Остановить сервер', 'Stop server'), action('stop'), enabled=ready),
            item(self.text('Обновить или переустановить', 'Update or reinstall'), action('maintenance'), enabled=ready),
            pystray.Menu.SEPARATOR,
            item(self.text('Выход — остановить сервер', 'Exit and stop server'), action('exit'), enabled=ready))
        self.icon = pystray.Icon('project-hub', status_image(self.application_home, self.status), self.label(), menu)
        if not self.icon.HAS_MENU:
            raise ValueError('This desktop has no supported tray menu. Install the desktop AppIndicator backend.')
        def setup(icon):
            icon.visible = True
            atomic_json(self.config_path.with_name('desktop-tray-state.json'),
                dict(applicationHome=str(self.application_home),at=time.time(),visible=True,
                     status=self.status,port=self.port,dataHome=self.config['dataHome']))
            threading.Thread(target=self.monitor, name='hub-tray-status', daemon=True).start()
        try:
            self.icon.run(setup=setup)  # toolkit main loop stays on the main thread
        finally:
            self.closed.set()
            self.executor.shutdown(wait=False, cancel_futures=True)
            self.config_path.with_name('desktop-tray-state.json').unlink(missing_ok=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--application-home', type=Path, required=True)
    args = parser.parse_args(argv)
    import runtime_diagnostics as diagnostics
    diagnostics.configure('tray',directory=args.config.parent / 'diagnostics',codeRoot=str(args.application_home),config=str(args.config))
    try:
        config = external_path(args.config, application_home=args.application_home)
        with file_lock(config.with_name('desktop-tray.lock')):
            TrayController(config, args.application_home).run()
        return 0
    except TimeoutError:
        return 0
    except (ValueError, OSError, ImportError) as error:
        diagnostics.exception('tray.failed',error)
        atomic_json(args.config.with_name('desktop-tray-error.json'), {'message':str(error), 'at':time.time()})
        return 1
    finally:
        diagnostics.cleanup()


if __name__ == '__main__':
    raise SystemExit(main())
